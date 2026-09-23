"""TOTP second-factor behaviour: single use, factor replacement, storage.

These are the properties that make the authenticator trustworthy rather than
merely present:

* a code authenticates **once**, so one observed at a shoulder or phished is not
  reusable for the rest of its (and its drift window's) validity;
* a replacement factor is proven before it replaces anything, so an abandoned
  setup can neither disable the second factor nor invalidate the authenticator in
  the user's hand;
* the seed is encrypted at rest and never appears in a response after enrolment.

The verification window is ±1 step, so the codes available at one moment are the
current step and its two neighbours. Tests therefore assert one *successful*
verification per account where possible, and read the stored seed to prove that a
swap happened rather than spending more codes than a real user could.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import select

from core.database import async_session_maker
from core.secret_box import decrypt_secret, is_encrypted
from core.settings import get_settings
from core.totp import totp_at
from db.models import User, now_ist
from tests.auth_helpers import (
    API,
    PASSWORD,
    bearer,
    client,
    create_account,
    login,
    run_async,
)


@pytest.fixture
def unique_suffix() -> Iterator[str]:
    """Unique label per test so seeded rows never collide."""
    yield uuid.uuid4().hex[:6]


def _seed(suffix: str, *, label: str = "emp", is_superuser: bool = False) -> int:
    """Create a login account and return its user id."""

    async def _create() -> int:
        async with async_session_maker() as session:
            user, _employee = await create_account(
                session, suffix=suffix, label=label, is_superuser=is_superuser
            )
            return user.id

    return run_async(_create())


def _row(user_id: int) -> tuple[str | None, str | None, int | None]:
    """The raw columns: active ciphertext, pending ciphertext, replay step."""

    async def _read() -> tuple[str | None, str | None, int | None]:
        async with async_session_maker() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            assert user is not None
            return user.mfa_secret, user.mfa_pending_secret, user.mfa_last_used_step

    return run_async(_read())


def _active_seed(user_id: int) -> str:
    """Decrypt the stored seed the way the service does (public API only)."""
    stored = _row(user_id)[0]
    assert stored, "account has no active seed"
    assert is_encrypted(stored), "the seed must be stored as ciphertext"
    return decrypt_secret(stored, get_settings().mfa_secret_key())


def _expire_pending_enrolment(user_id: int) -> None:
    """Move a pending replacement into the past without waiting in a test."""

    async def _expire() -> None:
        async with async_session_maker() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            assert user is not None
            user.mfa_pending_expires_at = now_ist() - timedelta(seconds=1)
            await session.commit()

    run_async(_expire())


def _store_legacy_plaintext_seed(user_id: int, secret: str) -> None:
    """Simulate a pre-encryption row so verification can migrate it in place."""

    async def _store() -> None:
        async with async_session_maker() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            assert user is not None
            user.mfa_secret = secret
            await session.commit()

    run_async(_store())


def _begin_enrolment(instance, identity: str, *, super_admin: bool = False) -> dict:
    """Obtain a pending secret without confirming it.

    The two enrolment doors differ by design: a privileged account is challenged
    at sign-in (set ``MFA_REQUIRED_FOR_SUPER_ADMIN``) and enrols with the challenge
    token, whereas a business account opts in from an authenticated session, where
    the password is re-verified instead.  Both are exercised here.
    """
    if super_admin:
        challenge = login(instance, identity, super_admin=True).json()
        assert challenge.get("mfa_token"), challenge
        issued = instance.post(f"{API}/auth/mfa/enroll", json={"mfa_token": challenge["mfa_token"]})
        assert issued.status_code == 200, issued.text
        return {"super_admin": True, "mfa_token": challenge["mfa_token"], **issued.json()}

    session = login(instance, identity).json()
    assert session.get("access_token"), session
    issued = instance.post(
        f"{API}/auth/mfa/reset", json={"current_password": PASSWORD}, headers=bearer(session["access_token"])
    )
    assert issued.status_code == 200, issued.text
    return {"super_admin": False, "access_token": session["access_token"], **issued.json()}


def _confirm_enrolment(instance, pending: dict, code: str):
    """Prove possession of the pending secret through the matching door."""
    if pending["super_admin"]:
        return instance.post(f"{API}/auth/mfa/activate", json={"mfa_token": pending["mfa_token"], "code": code})
    return instance.post(
        f"{API}/auth/mfa/confirm",
        json={"current_password": PASSWORD, "code": code},
        headers=bearer(pending["access_token"]),
    )


def _enrol(instance, identity: str, *, super_admin: bool = False) -> dict:
    """Complete first-time enrolment; returns the secret, codes and a session token."""
    pending = _begin_enrolment(instance, identity, super_admin=super_admin)
    response = _confirm_enrolment(instance, pending, totp_at(pending["secret"], now_ist()))
    assert response.status_code == 200, response.text
    return {
        **response.json(),
        "secret": pending["secret"],
        "recovery_codes": pending["recovery_codes"],
        # Privileged activation issues the session; a business account already had one.
        "access_token": response.json().get("access_token") or pending["access_token"],
    }


def _verify(instance, identity: str, code: str, *, super_admin: bool = False):
    challenge = login(instance, identity, super_admin=super_admin).json()
    return instance.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": code})


def _later(secret: str, *, steps: int = 1) -> str:
    """The next code an authenticator would show (still inside the drift window)."""
    return totp_at(secret, now_ist() + timedelta(seconds=30 * steps))


# ── single use ────────────────────────────────────────────────────────────────


def test_a_code_authenticates_exactly_once(unique_suffix):
    """Replaying a spent code fails, and says why."""
    _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity)
        code = _later(session["secret"])

        first = _verify(instance, identity, code)
        assert first.status_code == 200, first.text

        # A brand-new challenge, so the failure is the code being spent rather
        # than the challenge token being stale.
        replayed = _verify(instance, identity, code)
        assert replayed.status_code == 401
        # The message separates a spent code from a wrong one: the user is told to
        # wait for the next code, not to hunt for a typo that is not there.
        assert "already been used" in replayed.json()["detail"]


def test_a_drifted_code_is_accepted_once_and_then_spent(unique_suffix):
    """One step of drift is tolerated - for a single use only."""
    user_id = _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        pending = _begin_enrolment(instance, identity)
        secret = pending["secret"]
        # Confirm with a code one step behind the server clock: a lagging client.
        lagging = totp_at(secret, now_ist() - timedelta(seconds=30))
        assert _confirm_enrolment(instance, pending, lagging).status_code == 200
        assert _row(user_id)[2] is not None, "the consumed step must be recorded"

        # The same lagging code is spent, even though it still validates.
        assert _verify(instance, identity, lagging).status_code == 401
        # The current code signs in.
        assert _verify(instance, identity, totp_at(secret, now_ist())).status_code == 200


def test_recovery_codes_survive_totp_single_use(unique_suffix):
    _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity)
        codes = session["recovery_codes"]
        assert len(codes) == 10

        for code in codes[:3]:
            assert _verify(instance, identity, code).status_code == 200

        # A consumed recovery code is refused; the remaining ones still work.
        assert _verify(instance, identity, codes[0]).status_code == 401
        assert _verify(instance, identity, codes[3]).status_code == 200


# ── pending vs active factor ──────────────────────────────────────────────────


def test_an_abandoned_replacement_keeps_the_existing_factor_working(unique_suffix):
    """The regression: a half-finished reset used to turn MFA off entirely."""
    user_id = _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity)
        old_secret = session["secret"]

        # Ask for a replacement, then walk away without confirming it.
        issued = instance.post(
            f"{API}/auth/mfa/reset", json={"current_password": PASSWORD}, headers=bearer(session["access_token"])
        )
        assert issued.status_code == 200, issued.text
        body = issued.json()
        assert body["replacing_existing"] is True
        # Existing codes are kept: replacing a factor must not invalidate codes the
        # user wrote down and may need tomorrow.
        assert body["recovery_codes"] == []

        stored, pending, _step = _row(user_id)
        assert stored and pending and stored != pending, "the live seed must be untouched"
        assert _active_seed(user_id) == old_secret

        # MFA is still required and the existing authenticator still works...
        challenge = login(instance, identity).json()
        assert challenge["mfa_required"] is True
        assert challenge["mfa_enrollment_required"] is False, "an enrollee must not be forced to re-enrol"
        assert _verify(instance, identity, _later(old_secret)).status_code == 200

        # ...while the unconfirmed secret is not yet usable.
        assert _verify(instance, identity, _later(body["secret"])).status_code == 401


def test_confirming_a_replacement_promotes_it_and_retires_the_old_secret(unique_suffix):
    user_id = _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity)
        old_secret = session["secret"]
        headers = bearer(session["access_token"])

        issued = instance.post(f"{API}/auth/mfa/reset", json={"current_password": PASSWORD}, headers=headers).json()
        new_secret = issued["secret"]

        status = instance.get(f"{API}/auth/mfa/status", headers=headers).json()
        assert status["replacement_pending"] is True
        assert status["recovery_codes_remaining"] == 10, "codes are preserved across a replacement"

        confirmed = instance.post(
            f"{API}/auth/mfa/confirm",
            json={"current_password": PASSWORD, "code": _later(new_secret)},
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["enabled"] is True
        assert confirmed.json()["replacement_pending"] is False

        stored, pending, step = _row(user_id)
        assert pending is None, "the pending seed must not linger once promoted"
        assert _active_seed(user_id) == new_secret, "the promoted seed is the one that was confirmed"
        assert stored != old_secret and step is not None

        # The replaced authenticator no longer authenticates.
        assert _verify(instance, identity, _later(old_secret)).status_code == 401
        assert _row(user_id)[0] == stored


def test_an_expired_replacement_is_rejected_and_hidden_from_status(unique_suffix):
    user_id = _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity)
        headers = bearer(session["access_token"])
        issued = instance.post(f"{API}/auth/mfa/reset", json={"current_password": PASSWORD}, headers=headers)
        assert issued.status_code == 200, issued.text
        pending_secret = issued.json()["secret"]

        _expire_pending_enrolment(user_id)

        expired = instance.post(
            f"{API}/auth/mfa/confirm",
            json={"current_password": PASSWORD, "code": _later(pending_secret)},
            headers=headers,
        )
        assert expired.status_code == 400
        assert "expired" in expired.json()["detail"].lower()
        assert instance.get(f"{API}/auth/mfa/status", headers=headers).json()["replacement_pending"] is False
        assert _active_seed(user_id) == session["secret"]


def test_legacy_plaintext_seed_is_reencrypted_on_successful_verification(unique_suffix):
    user_id = _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        enrolled = _enrol(instance, identity)
        secret = enrolled["secret"]
        _store_legacy_plaintext_seed(user_id, secret)
        assert _row(user_id)[0] == secret

        verified = _verify(instance, identity, _later(secret))
        assert verified.status_code == 200, verified.text
        stored = _row(user_id)[0]
        assert stored and is_encrypted(stored)
        assert secret not in stored
        assert _active_seed(user_id) == secret


def test_super_admin_is_not_forced_to_re_enrol_after_an_abandoned_reset(unique_suffix, monkeypatch):
    """The break-glass account keeps requiring the factor it already holds."""
    monkeypatch.setattr(get_settings(), "mfa_required_for_super_admin", True)
    _seed(unique_suffix, label="root", is_superuser=True)
    identity = f"root.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity, super_admin=True)
        assert instance.post(
            f"{API}/auth/mfa/reset",
            json={"current_password": PASSWORD},
            headers=bearer(session["access_token"]),
        ).status_code == 200

        challenge = login(instance, identity, super_admin=True).json()
        assert challenge["mfa_required"] is True
        assert challenge["mfa_enrollment_required"] is False
        assert _verify(instance, identity, _later(session["secret"]), super_admin=True).status_code == 200


# ── storage ───────────────────────────────────────────────────────────────────


def test_the_seed_is_encrypted_at_rest_and_absent_from_every_response(unique_suffix):
    user_id = _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        pending = _begin_enrolment(instance, identity)
        plaintext = pending["secret"]

        # Even the unconfirmed value is stored as ciphertext, and the plaintext
        # secret never appears in the row.
        stored_pending = _row(user_id)[1]
        assert stored_pending and is_encrypted(stored_pending) and plaintext not in stored_pending

        session = _confirm_enrolment(instance, pending, totp_at(plaintext, now_ist()))
        assert session.status_code == 200, session.text

        stored, _pending, step = _row(user_id)
        assert stored and is_encrypted(stored) and plaintext not in stored
        assert step is not None, "a spent code records its step"
        assert _active_seed(user_id) == plaintext

        # The status endpoint describes state without ever returning the seed or
        # its provisioning URI again.
        status = instance.get(f"{API}/auth/mfa/status", headers=bearer(pending["access_token"])).json()
        assert status["enabled"] is True
        assert status["recovery_codes_remaining"] == 10
        assert plaintext not in str(status)
        assert "otpauth" not in str(status)


# ── recovery-code lifecycle ───────────────────────────────────────────────────


def test_regenerating_recovery_codes_invalidates_the_previous_set(unique_suffix):
    _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        session = _enrol(instance, identity)
        original = session["recovery_codes"]
        headers = bearer(session["access_token"])

        regenerated = instance.post(
            f"{API}/auth/mfa/recovery/regenerate", json={"current_password": PASSWORD}, headers=headers
        )
        assert regenerated.status_code == 200, regenerated.text
        fresh = regenerated.json()["recovery_codes"]
        assert len(fresh) == 10
        assert regenerated.json()["recovery_codes_remaining"] == 10
        assert set(fresh).isdisjoint(original)

        # The previous set is dead; the new set works and the count tracks it.
        assert _verify(instance, identity, original[0]).status_code == 401
        assert _verify(instance, identity, fresh[0]).status_code == 200
        assert instance.get(f"{API}/auth/mfa/status", headers=headers).json()["recovery_codes_remaining"] == 9


def test_regenerating_recovery_codes_needs_a_factor_and_the_password(unique_suffix):
    _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    with client() as instance:
        # No factor yet: codes exist to recover from losing one, so issuing them
        # beforehand would be meaningless.
        bare = bearer(login(instance, identity).json()["access_token"])
        assert instance.post(
            f"{API}/auth/mfa/recovery/regenerate", json={"current_password": PASSWORD}, headers=bare
        ).status_code == 409

        session = _enrol(instance, identity)
        headers = bearer(session["access_token"])
        assert instance.post(
            f"{API}/auth/mfa/recovery/regenerate",
            json={"current_password": "Definitely-Not-The-Password1"},
            headers=headers,
        ).status_code == 400
        # The refusal changed nothing.
        assert instance.get(f"{API}/auth/mfa/status", headers=headers).json()["recovery_codes_remaining"] == 10


def test_authenticator_can_recover_a_forgotten_password_without_creating_a_session(unique_suffix):
    _seed(unique_suffix)
    identity = f"emp.{unique_suffix}"
    new_password = "Harbour9-Velvet-Marble"
    with client() as instance:
        enrolled = _enrol(instance, identity)
        started = instance.post(f"{API}/auth/password-recovery/start", json={"identity": identity})
        assert started.status_code == 200, started.text
        assert started.json()["recovery_token"]

        verified = instance.post(
            f"{API}/auth/password-recovery/verify",
            json={"recovery_token": started.json()["recovery_token"], "code": _later(enrolled["secret"])},
        )
        assert verified.status_code == 200, verified.text
        reset_token = verified.json()["recovery_token"]

        reset = instance.post(
            f"{API}/auth/password-recovery/reset",
            json={"reset_token": reset_token, "new_password": new_password},
        )
        assert reset.status_code == 200, reset.text
        assert login(instance, identity, password=PASSWORD).status_code == 401
        fresh = login(instance, identity, password=new_password)
        assert fresh.status_code == 200, fresh.text
        assert instance.post(
            f"{API}/auth/password-recovery/reset",
            json={"reset_token": reset_token, "new_password": PASSWORD},
        ).status_code == 401
