"""HTTP-level authentication hardening.

What these tests pin down, end to end:

* every workforce role signs in through the *same* business endpoint, and a
  technical account cannot use it (and vice versa);
* login responses do not reveal whether an account exists;
* repeated failures are throttled per IP, per account and per pair, and a
  temporary block never becomes a permanent lockout;
* refresh abuse is throttled without letting one attacker's tokens block a real
  user's refresh;
* changing a password (self-service or HR/ERP reset) ends every refresh chain;
* Super Admin MFA: challenge after the password, enrolment, recovery codes, and
  the challenge token being unusable as an access token;
* an access token cannot be revoked before it expires (stateless JWT) — the
  documented limitation this suite makes explicit.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from core.auth_throttle import get_auth_throttle
from core.database import async_session_maker, auth_engine
from core.settings import get_settings
from core.totp import totp_at
from db.models import Employee, User, now_ist
from tests.auth_helpers import (
    API,
    NEW_PASSWORD,
    PASSWORD,
    bearer,
    client,
    create_account,
    ensure_org_structure,
    login,
    next_code,
    refresh,
    run_async,
)

helper = PasswordHelper()


@pytest.fixture
def unique_suffix() -> Iterator[str]:
    yield uuid.uuid4().hex[:6]


@pytest.fixture(autouse=True)
def clean_throttle() -> Iterator[None]:
    """Throttle state is process-wide by design, so isolate every test."""
    throttle = get_auth_throttle()
    run_async(throttle.reset_all())
    yield
    run_async(throttle.reset_all())


def _seed(suffix: str, **account):
    """Create org structure plus one account in a fresh event loop."""

    async def _run():
        async with async_session_maker() as session:
            org, unit, department, designation = await ensure_org_structure(session, suffix)
            user, employee = await create_account(
                session,
                suffix=suffix,
                unit_id=unit.id,
                department_id=department.id,
                **account,
            )
            await auth_engine.dispose()
            return org, unit, department, designation, user, employee

    return run_async(_run())


def _create_user_only(suffix: str, *, label: str = "tech", password: str = PASSWORD, is_superuser: bool = False):
    """A login account with no Employee record (a pure technical identity)."""

    async def _run():
        async with async_session_maker() as session:
            user = User(
                email=f"{label}.{suffix}@people-hrms.co.in",
                username=f"{label}.{suffix}",
                first_name="Tech",
                last_name="Account",
                hashed_password=helper.hash(password),
                is_active=True,
                is_verified=True,
                is_superuser=is_superuser,
            )
            session.add(user)
            await session.commit()
            await auth_engine.dispose()
            return user.id

    return run_async(_run())


# ── authentication domains ────────────────────────────────────────────────────


def test_every_workforce_role_signs_in_through_the_same_business_endpoint(unique_suffix):
    """Role never decides the endpoint — only permissions and scope differ."""
    roles = [
        {"label": "emp"},
        {"label": "mgr", "role": "DEPARTMENT_MANAGER", "business_role": "DEPARTMENT_MANAGER", "access_scope": "DEPARTMENT"},
        {"label": "uhr", "role": "HR_ADMIN", "business_role": "HR_ADMIN", "access_scope": "UNIT"},
        {"label": "ohr", "role": "HR_ADMIN", "business_role": "HR_ADMIN", "access_scope": "ORGANIZATION"},
        {"label": "own", "role": "ORGANIZATION_OWNER", "business_role": "ORGANIZATION_OWNER", "access_scope": "ORGANIZATION"},
    ]
    with client() as instance:
        for spec in roles:
            _seed(f"{unique_suffix}{spec['label']}", **spec)
            response = login(instance, f"{spec['label']}.{unique_suffix}{spec['label']}")
            assert response.status_code == 200, (spec["label"], response.text)
            payload = response.json()
            assert payload["access_token"] and payload["refresh_token"]


def test_a_technical_account_cannot_use_the_business_login(unique_suffix):
    _create_user_only(unique_suffix, is_superuser=True)
    with client() as instance:
        # Correct password, but there is no employee profile: the API says so
        # explicitly (it is only reachable with a valid credential, so this
        # cannot be used to probe for account existence).
        response = login(instance, f"tech.{unique_suffix}")
        assert response.status_code == 403
        assert "technical account" in response.json()["detail"].lower()


def test_a_business_account_cannot_use_the_super_admin_login(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        response = instance.post(
            f"{API}/auth/super-admin/login", data={"username": f"emp.{unique_suffix}", "password": PASSWORD}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid login credentials"


def test_super_admin_login_rejects_identifiers_that_are_not_usernames(unique_suffix):
    _create_user_only(unique_suffix, is_superuser=True)
    with client() as instance:
        for identity in (f"tech.{unique_suffix}@people-hrms.co.in", "9876543210"):
            response = instance.post(f"{API}/auth/super-admin/login", data={"username": identity, "password": PASSWORD})
            assert response.status_code == 400


def test_business_login_rejects_email_and_accepts_username_or_mobile(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        assert login(instance, f"emp.{unique_suffix}@people-hrms.co.in").status_code == 400
        assert login(instance, f"emp.{unique_suffix}").status_code == 200


# ── enumeration resistance ────────────────────────────────────────────────────


def test_login_does_not_reveal_whether_an_account_exists(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        wrong_password = login(instance, f"emp.{unique_suffix}", password="Not-The-Password9!")
        unknown_username = login(instance, f"nobody.{unique_suffix}")
        unknown_mobile = login(instance, "9000000000")
        assert wrong_password.status_code == unknown_username.status_code == unknown_mobile.status_code == 401
        # Byte-identical bodies: no oracle in the wording, and the reason is only
        # recorded in the audit trail.
        assert wrong_password.json() == unknown_username.json() == unknown_mobile.json()

        unprivileged = instance.post(
            f"{API}/auth/super-admin/login", data={"username": f"emp.{unique_suffix}", "password": PASSWORD}
        )
        unknown_privileged = instance.post(
            f"{API}/auth/super-admin/login", data={"username": f"ghost.{unique_suffix}", "password": PASSWORD}
        )
        assert unprivileged.json() == unknown_privileged.json()
        assert unprivileged.status_code == 401


def test_authentication_events_are_audited_without_secrets(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        login(instance, f"emp.{unique_suffix}", password="Wrong-Password-9!")
        login(instance, f"emp.{unique_suffix}")

    async def _events():
        from db.models import AuditLog

        async with async_session_maker() as session:
            rows = list(
                await session.scalars(
                    select(AuditLog).where(AuditLog.action.in_(["AUTH_LOGIN_FAILED", "AUTH_LOGIN_SUCCESS"]))
                )
            )
            await auth_engine.dispose()
            return rows

    rows = run_async(_events())
    assert {row.action for row in rows} >= {"AUTH_LOGIN_FAILED", "AUTH_LOGIN_SUCCESS"}
    for row in rows:
        assert PASSWORD not in row.filters_json
        assert "Wrong-Password-9!" not in row.filters_json


# ── brute-force protection ────────────────────────────────────────────────────


def test_repeated_failures_are_throttled_and_recover(unique_suffix):
    _seed(unique_suffix, label="emp")
    _seed(f"{unique_suffix}other", label="emp")
    with client() as instance:
        last = None
        for _ in range(5):
            last = login(instance, f"emp.{unique_suffix}", password="Wrong-Password-9!")
        assert last is not None and last.status_code == 429
        assert int(last.headers["retry-after"]) > 0

        # While blocked, even the correct password is refused.
        assert login(instance, f"emp.{unique_suffix}").status_code == 429
        # Another employee behind the same client address is unaffected: the
        # block is scoped to the IP+account pair, so one person's typos cannot
        # lock out a colleague (or the whole office NAT).
        assert login(instance, f"emp.{unique_suffix}other", password="Wrong-Password-9!").status_code == 401

        run_async(get_auth_throttle().reset_all())
        assert login(instance, f"emp.{unique_suffix}").status_code == 200


def test_refresh_abuse_is_throttled_without_blocking_other_tokens(unique_suffix):
    limit = get_settings().auth_refresh_max_failures
    with client() as instance:
        presented = 0
        blocked = None
        for _ in range(limit + 2):
            response = refresh(instance, "not-a-real-refresh-token")
            presented += 1
            if response.status_code == 429:
                blocked = response
                break
        assert blocked is not None, f"no throttle after {presented} attempts"
        assert int(blocked.headers["retry-after"]) > 0
        # A different (real) token is not collateral damage.
        assert refresh(instance, "another-invalid-token-value").status_code == 401


def test_successful_sign_in_clears_earlier_failures(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        for _ in range(3):
            assert login(instance, f"emp.{unique_suffix}", password="Wrong-Password-9!").status_code == 401
        assert login(instance, f"emp.{unique_suffix}").status_code == 200
        # If the counter had not been cleared, three more failures would reach
        # the block threshold and return 429 instead.
        assert login(instance, f"emp.{unique_suffix}", password="Wrong-Password-9!").status_code == 401


# ── password change / reset consequences ─────────────────────────────────────


def test_changing_a_password_ends_every_session(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        first = login(instance, f"emp.{unique_suffix}").json()
        second = login(instance, f"emp.{unique_suffix}").json()

        response = instance.post(
            f"{API}/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=bearer(first["access_token"]),
        )
        assert response.status_code == 200, response.text
        assert response.json()["reauthentication_required"] is True

        # Both refresh chains are dead, so a stolen session cannot outlive the
        # remediation.
        assert refresh(instance, first["refresh_token"]).status_code == 401
        assert refresh(instance, second["refresh_token"]).status_code == 401

        assert login(instance, f"emp.{unique_suffix}", password=PASSWORD).status_code == 401
        assert login(instance, f"emp.{unique_suffix}", password=NEW_PASSWORD).status_code == 200


def test_an_access_token_stays_valid_until_it_expires(unique_suffix):
    """Documented limitation: access tokens are stateless JWTs.

    Revocation is enforced on the refresh chain; the exposure window is bounded
    by the access-token TTL (15 minutes by default, 5 for privileged sessions).
    """
    _seed(unique_suffix, label="emp")
    with client() as instance:
        session = login(instance, f"emp.{unique_suffix}").json()
        instance.post(
            f"{API}/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=bearer(session["access_token"]),
        )
        still_accepted = instance.get(f"{API}/users/me", headers=bearer(session["access_token"]))
        assert still_accepted.status_code == 200
        assert get_settings().access_token_ttl_seconds <= 900


def test_hr_temporary_password_reset_revokes_sessions_and_forces_a_change(unique_suffix):
    async def _seed_two_units():
        async with async_session_maker() as session:
            org, unit_a, department_a, _ = await ensure_org_structure(session, f"{unique_suffix}a")
            _, unit_b, department_b, _ = await ensure_org_structure(session, f"{unique_suffix}b")
            hr_user, _hr = await create_account(
                session,
                suffix=unique_suffix,
                label="hr",
                role="HR_ADMIN",
                business_role="HR_ADMIN",
                access_scope="UNIT",
                access_scope_id=unit_a.id,
                unit_id=unit_a.id,
                department_id=department_a.id,
            )
            employee_user, employee = await create_account(
                session, suffix=unique_suffix, label="emp", unit_id=unit_a.id, department_id=department_a.id
            )
            _, outsider = await create_account(
                session,
                suffix=unique_suffix,
                label="out",
                business_role="HR_ADMIN",
                role="HR_ADMIN",
                access_scope="UNIT",
                access_scope_id=unit_b.id,
                unit_id=unit_b.id,
                department_id=department_b.id,
            )
            await auth_engine.dispose()
            return employee, outsider

    employee, outsider = run_async(_seed_two_units())
    with client() as instance:
        existing = login(instance, f"emp.{unique_suffix}").json()
        temporary = "Temp-Pass-2026!Quartz"

        response = instance.post(
            f"{API}/auth/hr/employees/{employee.id}/password-reset",
            json={"temporary_password": temporary},
            headers=bearer(login(instance, f"hr.{unique_suffix}").json()["access_token"]),
        )
        assert response.status_code == 200, response.text
        assert response.json()["sessions_revoked"] is True

        # The employee's live session is gone and the old password no longer works.
        assert refresh(instance, existing["refresh_token"]).status_code == 401
        assert login(instance, f"emp.{unique_suffix}", password=PASSWORD).status_code == 401

        # The temporary password works, but the account is flagged for change.
        after_reset = login(instance, f"emp.{unique_suffix}", password=temporary)
        assert after_reset.status_code == 200
        assert after_reset.json()["must_change_password"] is True

        # Scope is still enforced on the reset endpoint: this HR admin cannot
        # reach an employee in another unit.
        denied = instance.post(
            f"{API}/auth/hr/employees/{outsider.id}/password-reset",
            json={"temporary_password": temporary},
            headers=bearer(login(instance, f"hr.{unique_suffix}").json()["access_token"]),
        )
        assert denied.status_code == 403


def test_must_change_password_clears_after_the_user_sets_their_own(unique_suffix):
    async def _reset():
        async with async_session_maker() as session:
            employee = await session.scalar(
                select(Employee).where(Employee.employee_code == f"EMP_{unique_suffix}"[:30])
            )
            user = await session.get(User, employee.user_id)
            user.hashed_password = helper.hash("Temp-Pass-2026!Quartz")
            user.must_change_password = True
            await session.commit()
            await auth_engine.dispose()

    _seed(unique_suffix, label="emp")
    run_async(_reset())
    with client() as instance:
        session = login(instance, f"emp.{unique_suffix}", password="Temp-Pass-2026!Quartz").json()
        me = instance.get(f"{API}/users/me", headers=bearer(session["access_token"]))
        assert me.json()["must_change_password"] is True

        changed = instance.post(
            f"{API}/auth/change-password",
            json={"current_password": "Temp-Pass-2026!Quartz", "new_password": NEW_PASSWORD},
            headers=bearer(session["access_token"]),
        )
        assert changed.status_code == 200
        fresh = login(instance, f"emp.{unique_suffix}", password=NEW_PASSWORD)
        assert fresh.json()["must_change_password"] is False


# ── Super Admin MFA ──────────────────────────────────────────────────────────


def test_super_admin_sign_in_requires_and_completes_mfa(unique_suffix, monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_required_for_super_admin", True)
    _seed(unique_suffix, label="root", is_superuser=True)

    with client() as instance:
        challenge = login(instance, f"root.{unique_suffix}", super_admin=True)
        assert challenge.status_code == 200
        body = challenge.json()
        assert body["mfa_required"] is True
        assert body["mfa_enrollment_required"] is True
        assert body["access_token"] is None and body["refresh_token"] is None

        enrollment = instance.post(f"{API}/auth/mfa/enroll", json={"mfa_token": body["mfa_token"]})
        assert enrollment.status_code == 200, enrollment.text
        secret = enrollment.json()["secret"]
        recovery_codes = enrollment.json()["recovery_codes"]
        assert secret and len(recovery_codes) == 10

        stale = totp_at(secret, now_ist() - timedelta(minutes=10))
        wrong = instance.post(
            f"{API}/auth/mfa/activate", json={"mfa_token": body["mfa_token"], "code": stale}
        )
        assert wrong.status_code == 400

        activation_code = totp_at(secret, now_ist())
        activated = instance.post(
            f"{API}/auth/mfa/activate",
            json={"mfa_token": body["mfa_token"], "code": activation_code},
        )
        assert activated.status_code == 200, activated.text
        session = activated.json()
        # Privileged sessions use the tighter policy.
        assert session["expires_in"] == get_settings().privileged_access_token_ttl_seconds < get_settings().access_token_ttl_seconds
        assert instance.get(f"{API}/users/me", headers=bearer(session["access_token"])).status_code == 200

        # Next sign-in: password, then the factor (no enrolment this time).
        again = login(instance, f"root.{unique_suffix}", super_admin=True).json()
        assert again["mfa_enrollment_required"] is False
        # The code that completed enrolment is spent: a code is single-use, so
        # re-presenting it at sign-in must not authenticate.
        assert instance.post(
            f"{API}/auth/mfa/verify",
            json={"mfa_token": again["mfa_token"], "code": activation_code},
        ).status_code == 401
        # The next code from the app signs in normally.
        assert instance.post(
            f"{API}/auth/mfa/verify",
            json={"mfa_token": again["mfa_token"], "code": next_code(secret)},
        ).status_code == 200

        # A recovery code works exactly once.
        recovery = instance.post(
            f"{API}/auth/mfa/verify", json={"mfa_token": again["mfa_token"], "code": recovery_codes[0]}
        )
        assert recovery.status_code == 200
        reused = instance.post(
            f"{API}/auth/mfa/verify", json={"mfa_token": again["mfa_token"], "code": recovery_codes[0]}
        )
        assert reused.status_code == 401


def test_the_mfa_challenge_token_is_not_an_access_token(unique_suffix, monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_required_for_super_admin", True)
    _seed(unique_suffix, label="root", is_superuser=True)
    with client() as instance:
        challenge = login(instance, f"root.{unique_suffix}", super_admin=True).json()
        presented = instance.get(f"{API}/users/me", headers=bearer(challenge["mfa_token"]))
        assert presented.status_code == 401


def test_employee_mfa_is_opt_in_and_always_honoured_once_enrolled(unique_suffix):
    _seed(unique_suffix, label="emp")
    with client() as instance:
        # Enrolment is available from an authenticated session, password re-verified.
        session = login(instance, f"emp.{unique_suffix}").json()
        headers = bearer(session["access_token"])
        assert instance.get(f"{API}/auth/mfa/status", headers=headers).json()["enabled"] is False

        issued = instance.post(f"{API}/auth/mfa/reset", json={"current_password": PASSWORD}, headers=headers)
        assert issued.status_code == 200, issued.text
        secret = issued.json()["secret"]

        refused = instance.post(
            f"{API}/auth/mfa/confirm",
            json={"current_password": "Not-My-Password-9!", "code": totp_at(secret, now_ist())},
            headers=headers,
        )
        assert refused.status_code == 400

        confirmed = instance.post(
            f"{API}/auth/mfa/confirm",
            json={"current_password": PASSWORD, "code": totp_at(secret, now_ist())},
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["enabled"] is True

        # From now on the factor is always requested, even though the policy for
        # a business account does not mandate one.
        challenge = login(instance, f"emp.{unique_suffix}")
        assert challenge.status_code == 200
        assert challenge.json()["mfa_required"] is True
        assert challenge.json()["mfa_enrollment_required"] is False

        signed_in = instance.post(
            f"{API}/auth/mfa/verify",
            json={"mfa_token": challenge.json()["mfa_token"], "code": next_code(secret)},
        ).json()
        removed = instance.post(
            f"{API}/auth/mfa/disable",
            json={"current_password": PASSWORD},
            headers=bearer(signed_in["access_token"]),
        )
        assert removed.status_code == 200, removed.text
        # With no factor enrolled the account signs in in one step again.
        assert login(instance, f"emp.{unique_suffix}").json().get("mfa_required", False) is False
