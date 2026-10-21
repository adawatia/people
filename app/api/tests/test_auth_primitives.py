"""Unit-level checks of the authentication security primitives.

These run without a database: the crypto helpers, the TOTP implementation, the
password policy and the throttling policy are all pure functions of their inputs
(plus an injectable store), which is exactly why the policy lives in ``core``.

HTTP-level consequences are covered in ``test_auth_hardening_http.py``.
"""

from __future__ import annotations

import base64
import importlib.util
import os
from datetime import timedelta

import jwt
import pytest

from core.auth_throttle import AuthThrottle, InMemoryThrottleStore, build_store
from core.password_policy import (
    LocalBreachChecker,
    NullBreachChecker,
    PasswordCheckContext,
    PasswordPolicyError,
    RemoteBreachChecker,
    build_breach_checker,
    validate_password_policy,
)
from core.secret_box import (
    SecretBoxError,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
)
from core.settings import Settings
from core.tokens import (
    ACCESS_TOKEN_AUDIENCE,
    MFA_CHALLENGE_AUDIENCE,
    create_access_token,
    create_mfa_challenge_token,
    decode_token,
    generate_refresh_token,
    hash_refresh_token,
    token_fingerprint,
)
from core.totp import (
    generate_secret,
    is_totp_replay,
    match_totp_step,
    totp_at,
    verify_totp,
)
from db.models import User, now_ist
from routers.auth_login import normalize_business_identity
from services.auth_service import AuthService
from tests.auth_helpers import PASSWORD, run_async

# ── tokens ────────────────────────────────────────────────────────────────────


def test_refresh_tokens_are_long_random_and_stored_only_as_hashes():
    first, second = generate_refresh_token(), generate_refresh_token()
    assert first != second
    assert len(first) >= 60  # 384 bits of entropy, URL-safe encoded

    digest = hash_refresh_token(first)
    assert digest != first
    assert len(digest) == 64
    assert hash_refresh_token(first) == digest  # deterministic, index-friendly
    assert token_fingerprint(first) == digest[:12]
    assert first not in token_fingerprint(first)


TEST_SIGNING_SECRET = "test-signing-secret-at-least-32-bytes"
OTHER_SIGNING_SECRET = "other-signing-secret-at-least-32-bytes"


def test_access_token_carries_the_service_audience_and_never_a_challenge_one():
    now = now_ist()
    token = create_access_token(subject=7, secret=TEST_SIGNING_SECRET, ttl_seconds=900, now=now, session_id=3)
    payload = decode_token(token, secret=TEST_SIGNING_SECRET, audience=ACCESS_TOKEN_AUDIENCE)
    assert payload["sub"] == "7"
    assert payload["sid"] == 3
    assert payload["typ"] == "access"

    # An MFA challenge is signed with the same key but a different audience, so
    # presenting it as a bearer token must fail.
    challenge = create_mfa_challenge_token(
        subject=7, secret=TEST_SIGNING_SECRET, ttl_seconds=300, now=now, enrollment_required=True
    )
    with pytest.raises(jwt.InvalidAudienceError):
        decode_token(challenge, secret=TEST_SIGNING_SECRET, audience=ACCESS_TOKEN_AUDIENCE)
    assert decode_token(challenge, secret=TEST_SIGNING_SECRET, audience=MFA_CHALLENGE_AUDIENCE)["enrol"] is True


def test_expired_access_tokens_are_rejected():
    stale = create_access_token(
        subject=1, secret=TEST_SIGNING_SECRET, ttl_seconds=1, now=now_ist() - timedelta(minutes=5)
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(stale, secret=TEST_SIGNING_SECRET)


def test_a_token_signed_with_another_key_is_rejected():
    token = create_access_token(subject=1, secret=TEST_SIGNING_SECRET, ttl_seconds=900, now=now_ist())
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(token, secret=OTHER_SIGNING_SECRET)


def test_business_login_identity_is_mobile_or_username_not_email():
    assert normalize_business_identity("  employee_42 ") == "employee_42"
    assert normalize_business_identity("9876543210") == "+919876543210"
    assert "@" in normalize_business_identity("employee@example.com")


def test_global_mfa_switch_disables_an_existing_factor():
    user = User(mfa_enabled=True, is_superuser=True)
    service = AuthService(None, settings=Settings(mfa_enabled=False))
    assert service.mfa_required(user) is False


# ── TOTP ──────────────────────────────────────────────────────────────────────


def test_totp_accepts_the_current_code_and_tolerates_one_step_of_drift():
    secret = generate_secret()
    now = now_ist()
    assert verify_totp(totp_at(secret, now), secret, now)
    assert verify_totp(totp_at(secret, now - timedelta(seconds=30)), secret, now)
    assert not verify_totp(totp_at(secret, now - timedelta(minutes=5)), secret, now)


def test_totp_rejects_malformed_codes_and_other_secrets():
    secret, other = generate_secret(), generate_secret()
    now = now_ist()
    assert not verify_totp("", secret, now)
    assert not verify_totp("abcdef", secret, now)
    assert not verify_totp("12345", secret, now)  # wrong length
    assert not verify_totp(totp_at(other, now), secret, now)


def test_match_totp_step_reports_the_step_that_matched_not_the_current_one():
    """A drifted code must be attributed to its own step.

    Recording "now" instead would either block a legitimate lagging client or
    leave the window open - which is exactly what made replay possible before.
    """
    secret = generate_secret()
    now = now_ist()
    current = int(now.timestamp()) // 30

    assert match_totp_step(totp_at(secret, now), secret, now) == current
    # A client one step behind still authenticates, and is attributed to its step.
    assert match_totp_step(totp_at(secret, now - timedelta(seconds=30)), secret, now) == current - 1
    assert match_totp_step(totp_at(secret, now - timedelta(seconds=120)), secret, now) is None
    assert match_totp_step("", secret, now) is None


def test_is_totp_replay_only_rejects_a_step_already_spent():
    assert is_totp_replay(None, None), "a submission that matched nothing is never accepted"
    assert is_totp_replay(None, 100), "matching nothing is still nothing"
    assert not is_totp_replay(100, None), "this seed has never consumed a code"
    assert not is_totp_replay(101, 100), "the next step's code is legitimate"
    assert is_totp_replay(100, 100), "the same step is spent"
    assert is_totp_replay(99, 100), "a stale drifted code is spent too"


# ── secret encryption ─────────────────────────────────────────────────────────


def test_secret_box_round_trips_and_never_reuses_a_ciphertext():
    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    secret = generate_secret()
    first = encrypt_secret(secret, key)
    second = encrypt_secret(secret, key)
    assert first != second, "a fresh nonce per call must make ciphertext opaque"
    assert first.startswith("v1:") and secret not in first
    assert decrypt_secret(first, key) == secret
    assert decrypt_secret(second, key) == secret
    assert is_encrypted(first)


def test_secret_box_reads_legacy_plaintext_and_fails_closed_on_a_bad_key():
    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    legacy = generate_secret()
    # A value written before encryption existed is read as-is, so introducing
    # encryption cannot lock existing users out of their authenticator.
    assert not is_encrypted(legacy)
    assert decrypt_secret(legacy, key) == legacy

    other_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    sealed = encrypt_secret(legacy, key)
    with pytest.raises(SecretBoxError):
        decrypt_secret(sealed, other_key)
    # Tampering is detected rather than silently producing a wrong secret.
    with pytest.raises(SecretBoxError):
        decrypt_secret(sealed[:-2] + ("AA" if not sealed.endswith("AA") else "BB"), key)
    with pytest.raises(SecretBoxError):
        encrypt_secret(legacy, "not-a-real-key")
    with pytest.raises(SecretBoxError):
        encrypt_secret(legacy, "")


# ── password policy ───────────────────────────────────────────────────────────


def _check(password: str, *, settings: Settings | None = None, **context: str) -> None:
    run_async(validate_password_policy(password, context=PasswordCheckContext(**context), settings=settings))


@pytest.mark.parametrize(
    "password",
    [
        "Short1!",  # under the minimum length
        "Password@123456",  # on the common-password list
        "Qwerty12345!",  # keyboard run, caught by the local checker
    ],
)
def test_weak_passwords_are_rejected(password):
    with pytest.raises(PasswordPolicyError):
        _check(password)


def test_password_must_not_contain_personal_information():
    with pytest.raises(PasswordPolicyError, match="name, email, or username"):
        _check("Quartz-Warmcomet-9!", username="warmcomet")
    # Separating the user's own name with punctuation is not an escape hatch.
    with pytest.raises(PasswordPolicyError, match="name, email, or username"):
        _check("Warm.Comet-Quartz9!", username="warmcomet")


def test_a_strong_passphrase_is_accepted_and_long_passwords_are_allowed():
    _check(PASSWORD)
    # Composition rules are intentionally absent: long, strong values do not
    # need an uppercase letter, digit, or symbol merely to satisfy a checklist.
    _check("alllowercaseletters")
    _check("NOLOWERCASE123!")
    _check("NoDigitsOrSymbols")
    # Passphrases and password-manager output are welcome: the ceiling is 256.
    _check("gT7#vQ2$mL9!zR4&wK1^")
    with pytest.raises(PasswordPolicyError, match="at most"):
        _check("Quartz-Meadow-9!" + "x" * 300)


def test_configured_eight_character_minimum_keeps_strength_checks():
    relaxed = Settings(password_min_length=8)
    _check("gT7#vQ2$m", settings=relaxed)
    with pytest.raises(PasswordPolicyError, match="at least 8"):
        _check("Short1!", settings=relaxed)
    with pytest.raises(PasswordPolicyError):
        _check("password", settings=relaxed)


def test_breach_checker_selection_and_fail_open_behaviour():
    assert isinstance(build_breach_checker(Settings(password_breach_check="off")), NullBreachChecker)
    assert isinstance(build_breach_checker(Settings(password_breach_check="local")), LocalBreachChecker)
    remote = build_breach_checker(
        Settings(password_breach_check="remote", password_breach_check_url="https://example.invalid/range")
    )
    assert isinstance(remote, RemoteBreachChecker)

    # An unreachable checker must admit the password rather than lock the user out.
    unreachable = RemoteBreachChecker("http://127.0.0.1:9/range", timeout_seconds=0.2)
    assert run_async(unreachable.is_breached("Quartz-Meadow-9!")) is False

    local = LocalBreachChecker()
    assert run_async(local.is_breached("welcome@123")) is True
    assert run_async(local.is_breached("Qwertyuiop")) is True
    assert run_async(local.is_breached("Quartz-Meadow-9!")) is False


# ── throttling policy ─────────────────────────────────────────────────────────

SMALL = Settings(
    auth_throttle_max_failures=3,
    auth_throttle_window_seconds=900,
    auth_throttle_block_seconds=10,
    auth_throttle_max_block_seconds=60,
    auth_refresh_max_failures=4,
)


def _throttle(settings: Settings = SMALL) -> AuthThrottle:
    return AuthThrottle(settings, store=InMemoryThrottleStore())


def test_repeated_failures_from_one_ip_and_account_block_that_pair():
    throttle = _throttle()
    decisions = [run_async(throttle.record_failure(ip="10.0.0.1", account="acct-a", scope="login")) for _ in range(3)]
    assert [decision.allowed for decision in decisions[:2]] == [True, True]
    assert decisions[-1].allowed is False
    assert decisions[-1].retry_after_seconds == 10
    assert decisions[-1].kind == "ip_account"

    # While blocked, even the *correct* password is refused — that is the point
    # of the block — so the caller sees a 429 before any work happens.
    assert run_async(throttle.check(ip="10.0.0.1", account="acct-a", scope="login")).allowed is False


def test_blocks_grow_geometrically_and_are_capped_never_permanent():
    throttle = _throttle()
    block_lengths = []
    for _ in range(6):
        decision = run_async(throttle.record_failure(ip="10.0.0.9", account="acct-b", scope="login"))
        block_lengths.append(decision.retry_after_seconds if not decision.allowed else 0)
    assert block_lengths[2:] == [10, 20, 40, 60]  # doubling, capped at max_block_seconds
    assert max(block_lengths) <= SMALL.auth_throttle_max_block_seconds


def test_a_typo_costs_a_short_delay_not_a_block():
    settings = Settings(
        auth_throttle_max_failures=6,
        auth_throttle_block_seconds=10,
        auth_throttle_max_block_seconds=60,
    )
    throttle = _throttle(settings)
    delays = []
    for _ in range(5):
        decision = run_async(throttle.record_failure(ip="10.0.0.2", account="acct-c", scope="login"))
        assert decision.allowed is True  # below the budget: never blocked
        delays.append(decision.delay_seconds)
    assert delays[0] == 0.0  # first few attempts are free
    assert delays[-1] > 0  # sustained failures slow the attacker down


def test_one_employee_cannot_lock_out_others_behind_a_shared_corporate_ip():
    throttle = _throttle()
    # Five different accounts, one office NAT address: no account is blocked and
    # the shared IP has not reached its (much larger) budget.
    for index in range(5):
        decision = run_async(throttle.record_failure(ip="203.0.113.7", account=f"acct-{index}", scope="login"))
        assert decision.allowed is True
    # The same account attacked from many addresses is still stopped, on the
    # account key, because no single pair counter is high enough on its own.
    for index in range(6):
        run_async(throttle.record_failure(ip=f"198.51.100.{index}", account="target", scope="login"))
    verdict = run_async(throttle.check(ip="192.0.2.55", account="target", scope="login"))
    assert verdict.allowed is False
    assert verdict.kind == "account"
    # ...while an unrelated employee behind that same address is unaffected.
    assert run_async(throttle.check(ip="192.0.2.55", account="bystander", scope="login")).allowed is True


def test_successful_sign_in_clears_every_counter():
    throttle = _throttle()
    for _ in range(2):
        run_async(throttle.record_failure(ip="10.0.0.3", account="acct-d", scope="login"))
    run_async(throttle.record_success(ip="10.0.0.3", account="acct-d", scope="login"))
    verdict = run_async(throttle.check(ip="10.0.0.3", account="acct-d", scope="login"))
    assert verdict.allowed is True
    assert verdict.delay_seconds == 0.0
    assert run_async(throttle.store.count("pair:10.0.0.3:acct-d", window_seconds=900)) == 0


def test_refresh_attempts_get_their_own_budget():
    throttle = _throttle()
    for _ in range(3):
        decision = run_async(throttle.record_failure(ip="10.0.0.4", account="token-fp", scope="refresh"))
        assert decision.allowed is True  # refresh budget is 4, not 3
    assert run_async(throttle.record_failure(ip="10.0.0.4", account="token-fp", scope="refresh")).allowed is False


def test_account_keys_are_normalised_and_never_stored_raw():
    assert AuthThrottle.account_key(" Alice@Example.com ") == AuthThrottle.account_key("alice@example.com")
    assert "alice" not in AuthThrottle.account_key("alice@example.com")


def test_store_backend_selection_fails_loudly_on_misconfiguration():
    assert isinstance(build_store(Settings(auth_throttle_backend="memory")), InMemoryThrottleStore)
    # An unknown value must not silently disable throttling.
    assert build_store(Settings(auth_throttle_backend="carrier-pigeon")).describe() == "memory"

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        build_store(Settings(auth_throttle_backend="redis", redis_url=""))

    if importlib.util.find_spec("redis") is not None:
        assert (
            build_store(Settings(auth_throttle_backend="redis", redis_url="redis://localhost:6379/0")).describe()
            == "redis"
        )
    else:
        # Multi-worker deployments need a shared store; asking for one without
        # the client installed must be an error, not per-worker limits.
        with pytest.raises(RuntimeError, match="redis"):
            build_store(Settings(auth_throttle_backend="redis", redis_url="redis://localhost:6379/0"))


def test_in_memory_store_expires_counters_and_blocks():
    store = InMemoryThrottleStore()
    key = "pair:1.2.3.4:acct"
    assert run_async(store.increment(key, window_seconds=900)) == 1
    assert run_async(store.increment(key, window_seconds=900)) == 2
    assert run_async(store.count(key, window_seconds=900)) == 2

    run_async(store.block(key, seconds=30))
    assert run_async(store.blocked_for(key)) > 0
    assert run_async(store.blocked_for(key)) <= 31

    run_async(store.clear(key))
    assert run_async(store.count(key, window_seconds=900)) == 0
    assert run_async(store.blocked_for(key)) == 0


def test_mobile_normalization_and_identity_resolution():
    from core.mobile import normalize_indian_mobile
    from routers.auth_login import account_key, normalize_business_identity

    # Standard formats
    assert normalize_indian_mobile("9876543210") == "+919876543210"
    assert normalize_indian_mobile("+91 98765 43210") == "+919876543210"
    assert normalize_indian_mobile("09876543210") == "+919876543210"
    assert normalize_indian_mobile("919876543210") == "+919876543210"

    # Usernames with digits are preserved and never raise
    assert normalize_business_identity("emp_1020304050") == "emp_1020304050"
    assert normalize_business_identity("user20261021") == "user20261021"

    # Invalid mobile numbers do not crash account_key
    key = account_key("1234567890")
    assert isinstance(key, str) and len(key) == 32
