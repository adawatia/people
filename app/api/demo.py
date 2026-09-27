"""
People HRMS realistic demo-data + full API exercise harness.

Purpose
-------
1. Seed a realistic, synthetic Indian technology-services organization through
   the ERP-owned HTTP APIs (never by writing directly to PostgreSQL).
2. Exercise every OpenAPI operation in the attached HRMS API contract at least
   once, including normal employee, manager, HR, executive, Super Admin, MFA,
   sessions, reports, workflow actions, and documented negative endpoints.
3. Assert endpoint coverage at the end.

This script is intended for a disposable development/test database. It creates,
updates, deactivates/reactivates, and deletes demo records and it changes demo
account authentication state. Do NOT point it at production.

Typical use
-----------
Preview only (no requests are sent):
    uv run python demo.py

Execute against a local API:
    export ERP_API_KEY='...'
    # Optional: defaults are superadmin / SuperAdmin@123
    # export DEMO_SUPER_ADMIN_USERNAME='superadmin'
    # export DEMO_SUPER_ADMIN_PASSWORD='SuperAdmin@123'
    uv run python demo.py --execute --ack-leave-changes

Useful environment variables
----------------------------
ERP_DEMO_BASE_URL               default http://127.0.0.1:8000/api/v1
ERP_API_CLIENT_ID               preferred HMAC client id with --execute
ERP_API_CLIENT_SECRET           preferred HMAC secret with --execute
ERP_API_KEY                     development-only fallback with --execute
ERP_DEMO_INITIAL_PASSWORD       default Cobalt!Harbor92#
DEMO_SUPER_ADMIN_USERNAME       default superadmin
DEMO_SUPER_ADMIN_PASSWORD       default SuperAdmin@123
DEMO_SUPER_ADMIN_TOTP_SECRET    required only when Super Admin is already MFA-enrolled
DEMO_SUPER_ADMIN_RECOVERY_CODE  alternative to TOTP secret for an enrolled Super Admin
DEMO_RUN_ID                     optional unique suffix; defaults to UTC timestamp
DEMO_ALLOW_REMOTE               set to 1 to allow --execute against a non-local host

Notes
-----
- Synthetic names, salaries, contact details, and company data are used.
- Standard leave codes are suffixed per run so repeated demo runs are less likely
  to collide with previous data.
- The script calls retired/ERP-owned browser endpoints too and verifies their
  documented failure status (for example employee onboarding = 410 and browser
  punch writes = 403). These count as API coverage because the contract itself
  documents the negative behavior.
- Full happy-path MFA enrollment for /auth/mfa/enroll + /activate is available
  when a fresh Super Admin login returns mfa_enrollment_required. If the Super
  Admin is already enrolled, those two operations are still called and recorded
  as expected negative state checks while /auth/mfa/verify is exercised normally.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Snapshot from the attached OpenAPI contract.
# At runtime, --execute attempts to load /openapi.json from the target server
# and uses that live operation set instead. This snapshot keeps dry-run useful.
# ---------------------------------------------------------------------------

OPENAPI_OPERATIONS_SNAPSHOT: set[tuple[str, str]] = {
    ("DELETE", "/api/v1/auth/session"),
    ("DELETE", "/api/v1/auth/sessions"),
    ("DELETE", "/api/v1/auth/sessions/{session_id}"),
    ("DELETE", "/api/v1/integrations/erp/departments/{department_id}"),
    ("DELETE", "/api/v1/integrations/erp/designations/{designation_id}"),
    ("DELETE", "/api/v1/integrations/erp/units/{unit_id}"),
    ("GET", "/"),
    ("GET", "/api/v1/attendance/"),
    ("GET", "/api/v1/attendance/checkins"),
    ("GET", "/api/v1/attendance/corrections"),
    ("GET", "/api/v1/attendance/employee/{emp_id}/calendar"),
    ("GET", "/api/v1/attendance/employee/{emp_id}/summary"),
    ("GET", "/api/v1/attendance/records/{record_id}"),
    ("GET", "/api/v1/auth/mfa/status"),
    ("GET", "/api/v1/auth/session"),
    ("GET", "/api/v1/auth/sessions"),
    ("GET", "/api/v1/dashboard/metrics"),
    ("GET", "/api/v1/dashboard/owner"),
    ("GET", "/api/v1/dashboard/owner/exceptions"),
    ("GET", "/api/v1/dashboard/technical-metrics"),
    ("GET", "/api/v1/dashboard/widgets"),
    ("GET", "/api/v1/designations/"),
    ("GET", "/api/v1/designations/{designation_id}"),
    ("GET", "/api/v1/employees/"),
    ("GET", "/api/v1/employees/{emp_id}"),
    ("GET", "/api/v1/employees/{emp_id}/work-history"),
    ("GET", "/api/v1/holidays/lists"),
    ("GET", "/api/v1/holidays/lists/{list_id}"),
    ("GET", "/api/v1/integrations/erp/leaves/changes"),
    ("GET", "/api/v1/leaves/"),
    ("GET", "/api/v1/leaves/balance/employee/{emp_id}"),
    ("GET", "/api/v1/leaves/periods"),
    ("GET", "/api/v1/leaves/types"),
    ("GET", "/api/v1/leaves/types/{type_id}"),
    ("GET", "/api/v1/leaves/{app_id}"),
    ("GET", "/api/v1/notifications"),
    ("GET", "/api/v1/notifications/unread-count"),
    ("GET", "/api/v1/org/departments"),
    ("GET", "/api/v1/org/departments/{dept_id}"),
    ("GET", "/api/v1/org/organization"),
    ("GET", "/api/v1/org/units"),
    ("GET", "/api/v1/org/units/{unit_id}"),
    ("GET", "/api/v1/overtime/"),
    ("GET", "/api/v1/overtime/employee/{emp_id}/summary"),
    ("GET", "/api/v1/overtime/{ot_id}"),
    ("GET", "/api/v1/reports/attendance-matrix"),
    ("GET", "/api/v1/reports/leave-summary"),
    ("GET", "/api/v1/shifts/"),
    ("GET", "/api/v1/shifts/assignments"),
    ("GET", "/api/v1/shifts/assignments/{assignment_id}"),
    ("GET", "/api/v1/shifts/employee/{emp_id}/schedule"),
    ("GET", "/api/v1/shifts/{shift_id}"),
    ("GET", "/api/v1/users/me"),
    ("GET", "/api/v1/users/me/permissions"),
    ("GET", "/api/v1/work-arrangements/"),
    ("GET", "/api/v1/work-arrangements/{req_id}"),
    ("GET", "/db-health"),
    ("GET", "/health"),
    ("PATCH", "/api/v1/auth/super-admin/username"),
    ("PATCH", "/api/v1/integrations/erp/departments/{department_id}"),
    ("PATCH", "/api/v1/integrations/erp/designations/{designation_id}"),
    ("PATCH", "/api/v1/integrations/erp/employees/{employee_id}"),
    ("PATCH", "/api/v1/integrations/erp/employees/{employee_id}/activate"),
    ("PATCH", "/api/v1/integrations/erp/employees/{employee_id}/deactivate"),
    ("PATCH", "/api/v1/integrations/erp/organization"),
    ("PATCH", "/api/v1/integrations/erp/shifts/assignments/{assignment_id}/cancel"),
    ("PATCH", "/api/v1/integrations/erp/shifts/{shift_id}"),
    ("PATCH", "/api/v1/integrations/erp/units/{unit_id}"),
    ("PATCH", "/api/v1/leaves/types/{type_id}"),
    ("PATCH", "/api/v1/leaves/{app_id}/approve"),
    ("PATCH", "/api/v1/leaves/{app_id}/cancel"),
    ("PATCH", "/api/v1/leaves/{app_id}/cancellation/approve"),
    ("PATCH", "/api/v1/leaves/{app_id}/cancellation/reject"),
    ("PATCH", "/api/v1/leaves/{app_id}/reject"),
    ("PATCH", "/api/v1/notifications/{id}/read"),
    ("PATCH", "/api/v1/overtime/{ot_id}/approve"),
    ("PATCH", "/api/v1/overtime/{ot_id}/reject"),
    ("PATCH", "/api/v1/work-arrangements/{req_id}/approve"),
    ("PATCH", "/api/v1/work-arrangements/{req_id}/cancel"),
    ("PATCH", "/api/v1/work-arrangements/{req_id}/reject"),
    ("POST", "/api/v1/attendance/checkins"),
    ("POST", "/api/v1/attendance/checkins/bulk"),
    ("POST", "/api/v1/attendance/corrections"),
    ("POST", "/api/v1/attendance/process"),
    ("POST", "/api/v1/auth/change-password"),
    ("POST", "/api/v1/auth/employee/login"),
    ("POST", "/api/v1/auth/hr/employees/{employee_id}/password-reset"),
    ("POST", "/api/v1/auth/integrations/erp/employees/{employee_id}/password-reset"),
    ("POST", "/api/v1/auth/mfa/activate"),
    ("POST", "/api/v1/auth/mfa/confirm"),
    ("POST", "/api/v1/auth/mfa/disable"),
    ("POST", "/api/v1/auth/mfa/enroll"),
    ("POST", "/api/v1/auth/mfa/recovery/regenerate"),
    ("POST", "/api/v1/auth/mfa/reset"),
    ("POST", "/api/v1/auth/mfa/verify"),
    ("POST", "/api/v1/auth/password-recovery/reset"),
    ("POST", "/api/v1/auth/password-recovery/start"),
    ("POST", "/api/v1/auth/password-recovery/verify"),
    ("POST", "/api/v1/auth/session"),
    ("POST", "/api/v1/auth/session/refresh"),
    ("POST", "/api/v1/auth/super-admin/login"),
    ("POST", "/api/v1/employees/onboard"),
    ("POST", "/api/v1/integrations/erp/attendance/records"),
    ("POST", "/api/v1/integrations/erp/attendance/records/bulk"),
    ("POST", "/api/v1/integrations/erp/departments"),
    ("POST", "/api/v1/integrations/erp/designations"),
    ("POST", "/api/v1/integrations/erp/employees"),
    ("POST", "/api/v1/integrations/erp/holidays/bulk"),
    ("POST", "/api/v1/integrations/erp/leaves/balances"),
    ("POST", "/api/v1/integrations/erp/leaves/balances/bulk"),
    ("POST", "/api/v1/integrations/erp/leaves/changes/ack"),
    ("POST", "/api/v1/integrations/erp/overtime/records/bulk"),
    ("POST", "/api/v1/integrations/erp/shifts"),
    ("POST", "/api/v1/integrations/erp/shifts/assignments"),
    ("POST", "/api/v1/integrations/erp/shifts/assignments/bulk"),
    ("POST", "/api/v1/integrations/erp/units"),
    ("POST", "/api/v1/leaves/"),
    ("POST", "/api/v1/leaves/periods"),
    ("POST", "/api/v1/leaves/types"),
    ("POST", "/api/v1/notifications/mark-all-read"),
    ("POST", "/api/v1/work-arrangements/"),
}


SENSITIVE_KEYS = {
    "password",
    "current_password",
    "new_password",
    "temporary_password",
    "initial_password",
    "access_token",
    "refresh_token",
    "mfa_token",
    "recovery_token",
    "reset_token",
    "secret",
    "otpauth_uri",
    "recovery_codes",
    "x-api-key",
}

DEFAULT_INITIAL_PASSWORD = "Cobalt!Harbor92#"
PASSWORD_AFTER_RECOVERY = "Quartz!River74%"
PASSWORD_FINAL = "Jade!Falcon83$"
PASSWORD_TARGET_ERP = "Silver!Comet61&"
PASSWORD_TARGET_HR = "Amber!Forest58#"

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class DemoError(RuntimeError):
    """A request, dependency, or API coverage assertion failed."""


@dataclass
class DemoResponse:
    status: int
    body: Any


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                if key.lower() == "recovery_codes" and isinstance(item, list):
                    result[key] = [f"*** ({len(item)} codes)"]
                else:
                    result[key] = "***"
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def compact_json(value: Any) -> str:
    return json.dumps(redact(value), indent=2, default=str, ensure_ascii=False)


def without_keys(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in keys and value is not None}


def require_id(body: Any, label: str) -> int:
    if not isinstance(body, dict) or not isinstance(body.get("id"), int):
        raise DemoError(f"{label} did not return an integer id: {body!r}")
    return int(body["id"])


def page_items(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        items = body.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def find_item(items: Iterable[dict[str, Any]], key: str, value: Any) -> dict[str, Any] | None:
    for item in items:
        if item.get(key) == value:
            return item
    return None


def next_weekday(start: date, business_days: int) -> date:
    """Return a weekday at least business_days weekdays after start."""
    current = start
    remaining = max(1, business_days)
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def recent_weekdays(ending: date, count: int) -> list[date]:
    values: list[date] = []
    current = ending
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current -= timedelta(days=1)
    return sorted(values)


def demo_holiday_dates(data: dict[str, Any]) -> set[date]:
    """Return active explicit holidays seeded by this demo.

    Leave/WFH workflows must not pick dates that this same script has just
    declared non-working through the ERP holiday sync.
    """
    values: set[date] = set()
    for item in data.get("holidays", []):
        if not item.get("is_active", True):
            continue
        raw = item.get("holiday_date")
        if not raw:
            continue
        try:
            values.add(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    return values


def next_demo_working_day(data: dict[str, Any], start: date, business_days: int) -> date:
    """Return a future demo working day, skipping weekends + seeded holidays."""
    holidays = demo_holiday_dates(data)
    current = start
    remaining = max(1, business_days)
    while remaining:
        current += timedelta(days=1)
        if current.weekday() >= 5 or current in holidays:
            continue
        remaining -= 1
    return current


def totp_for_counter(
    secret: str,
    counter: int,
    *,
    digits: int = 6,
) -> str:
    """Generate an RFC 6238 SHA-1 TOTP for an explicit time-step."""
    normalized = re.sub(r"\s+", "", secret).upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        key = base64.b32decode(normalized + padding, casefold=True)
    except Exception as exc:
        raise DemoError("Invalid base32 TOTP secret") from exc

    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def totp_now(secret: str, *, step_seconds: int = 30, digits: int = 6) -> str:
    """Generate the current RFC 6238 SHA-1 TOTP."""
    counter = int(time.time() // step_seconds)
    return totp_for_counter(secret, counter, digits=digits)



class Coverage:
    def __init__(self, expected: set[tuple[str, str]]) -> None:
        self.expected = set(expected)
        self.called: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, str]] = []
        self._patterns = self._compile_patterns(self.expected)

    @staticmethod
    def _compile_patterns(expected: set[tuple[str, str]]) -> list[tuple[str, re.Pattern[str], str]]:
        values: list[tuple[str, re.Pattern[str], str, int]] = []
        for method, template in expected:
            if template == "/":
                pattern = re.compile(r"^/$")
            else:
                escaped = re.escape(template)
                regex = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", escaped)
                pattern = re.compile("^" + regex + "$")
            placeholders = template.count("{")
            values.append((method, pattern, template, placeholders))
        values.sort(key=lambda row: (row[3], -len(row[2])))
        return [(m, p, t) for m, p, t, _ in values]

    def record(self, method: str, path: str) -> None:
        method = method.upper()
        for expected_method, pattern, template in self._patterns:
            if expected_method == method and pattern.match(path):
                self.called.add((method, template))
                self.calls.append((method, template))
                return
        # Requests to /openapi.json are intentionally not part of the API snapshot.
        if path != "/openapi.json":
            print(f"WARNING: request not present in OpenAPI snapshot: {method} {path}")

    def report(self) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        missing = sorted(self.expected - self.called)
        extra = sorted(self.called - self.expected)
        return missing, extra


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        erp_api_key: str,
        erp_client_id: str,
        erp_client_secret: str,
        execute: bool,
        coverage: Coverage,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.api_prefix = parsed.path.rstrip("/")
        self.erp_api_key = erp_api_key
        self.erp_client_id = erp_client_id
        self.erp_client_secret = erp_client_secret
        self.execute = execute
        self.coverage = coverage
        self._fake_id = 1000
        self._fake_session = 5000

    def _next_id(self) -> int:
        self._fake_id += 1
        return self._fake_id

    def _next_session(self) -> int:
        self._fake_session += 1
        return self._fake_session

    def _full_url_and_path(self, path: str, *, root: bool) -> tuple[str, str]:
        if root:
            request_path = "/" + path.lstrip("/") if path != "/" else "/"
            return f"{self.origin}{request_path}", request_path
        relative = path.lstrip("/")
        request_path = f"{self.api_prefix}/{relative}"
        return f"{self.origin}{request_path}", request_path

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        query: dict[str, Any] | None = None,
        token: str | None = None,
        api_key: bool = False,
        form: bool = False,
        expected: set[int] | None = None,
        root: bool = False,
        allow_partial_failure: bool = False,
        label: str | None = None,
    ) -> DemoResponse:
        method = method.upper()
        expected = expected or {200, 201, 204}
        url, request_path = self._full_url_and_path(path, root=root)
        clean_query = {k: v for k, v in (query or {}).items() if v is not None}
        if clean_query:
            url += "?" + urlencode(clean_query, doseq=True)

        self.coverage.record(method, request_path)

        title = label or f"{method} {request_path}"
        print(f"\n→ {title}")
        if clean_query:
            print("  query:", compact_json(clean_query))
        if payload is not None:
            print("  body:", compact_json(payload))

        if not self.execute:
            response = self._dry_response(method, request_path, payload, expected)
            print(f"  dry status: {response.status}")
            if response.body is not None:
                print("  dry response:", compact_json(response.body))
            return response

        headers = {
            "Accept": "application/json",
            "User-Agent": "People-HRMS-Demo/2.0",
        }
        body: bytes | None = None
        if payload is not None:
            if form:
                body = urlencode(payload).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(payload).encode()
                headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if api_key:
            if self.erp_client_id and self.erp_client_secret:
                timestamp = str(int(time.time()))
                nonce = secrets.token_hex(16)
                query_string = urlparse(url).query
                target = request_path + (f"?{query_string}" if query_string else "")
                body_hash = hashlib.sha256(body or b"").hexdigest()
                canonical = f"{method}\n{target}\n{timestamp}\n{nonce}\n{body_hash}"
                signature = hmac.new(
                    self.erp_client_secret.encode(), canonical.encode(), hashlib.sha256
                ).hexdigest()
                headers.update(
                    {
                        "X-ERP-Client-ID": self.erp_client_id,
                        "X-ERP-Timestamp": timestamp,
                        "X-ERP-Nonce": nonce,
                        "X-ERP-Signature": signature,
                    }
                )
            else:
                headers["X-API-Key"] = self.erp_api_key

        request = Request(url, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=45) as raw_response:
                status = int(raw_response.status)
                raw = raw_response.read()
                content_type = raw_response.headers.get("content-type", "")
                if not raw:
                    result = None
                elif "json" in content_type:
                    result = json.loads(raw)
                else:
                    result = raw.decode(errors="replace")
        except HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            try:
                result = json.loads(raw) if raw else None
            except Exception:
                result = raw.decode(errors="replace")
        except URLError as exc:
            raise DemoError(f"Could not reach {url}: {exc.reason}") from exc

        print(f"  status: {status}")
        if result is not None:
            print("  response:", compact_json(result))

        # Several list endpoints expose ``sort_by`` as a free-form string in
        # OpenAPI while validating it against an internal route-specific
        # allowlist.  The demo should not weaken that validation or guess every
        # private allowlist.  When a read-only list request is rejected only for
        # an unsupported sort field/order, retry once using the endpoint's
        # default deterministic ordering while preserving pagination/filters.
        def _is_sort_validation_error(response: Any) -> bool:
            if not isinstance(response, dict):
                return False
            detail = response.get("detail")
            if isinstance(detail, str):
                return "unsupported sort field or order" in detail.lower()
            if isinstance(detail, list):
                for error in detail:
                    if not isinstance(error, dict):
                        continue
                    loc = error.get("loc")
                    if (
                        isinstance(loc, list)
                        and len(loc) >= 2
                        and loc[0] == "query"
                        and loc[1] in {"sort_by", "sort_order"}
                    ):
                        return True
            return False

        sort_error = (
            status == 422
            and method == "GET"
            and any(key in clean_query for key in ("sort_by", "sort_order"))
            and _is_sort_validation_error(result)
        )
        if sort_error:
            fallback_query = dict(clean_query)
            fallback_query.pop("sort_by", None)
            fallback_query.pop("sort_order", None)
            print("  ↻ endpoint rejected explicit sorting; retrying with its default order")
            return self.request(
                method,
                path,
                payload,
                query=fallback_query,
                token=token,
                api_key=api_key,
                form=form,
                expected=expected,
                root=root,
                allow_partial_failure=allow_partial_failure,
                label=f"{title} (default ordering)",
            )

        if status not in expected:
            raise DemoError(
                f"{method} {request_path} returned {status}; expected {sorted(expected)}. Response: {result!r}"
            )

        if (
            not allow_partial_failure
            and isinstance(result, dict)
            and isinstance(result.get("failed"), list)
            and result.get("failed")
        ):
            raise DemoError(
                f"{method} {request_path} returned partial failures: {json.dumps(result['failed'], default=str)}"
            )

        return DemoResponse(status=status, body=result)

    def _dry_response(
        self,
        method: str,
        path: str,
        payload: Any,
        expected: set[int],
    ) -> DemoResponse:
        success_codes = sorted(code for code in expected if 200 <= code < 300)
        status = success_codes[0] if success_codes else min(expected)
        if status >= 400:
            return DemoResponse(status, {"detail": f"Dry-run expected status {status}"})

        if path.endswith(("/auth/employee/login", "/auth/super-admin/login")):
            return DemoResponse(
                status,
                {
                    "access_token": f"dry-access-{self._next_session()}",
                    "refresh_token": f"dry-refresh-{self._next_session()}",
                    "session_id": self._next_session(),
                    "mfa_required": False,
                    "mfa_enrollment_required": False,
                    "must_change_password": False,
                },
            )

        if path.endswith("/auth/session/refresh") or (path.endswith("/auth/session") and method == "POST"):
            return DemoResponse(
                status,
                {
                    "access_token": f"dry-access-{self._next_session()}",
                    "refresh_token": f"dry-refresh-{self._next_session()}",
                    "session_id": self._next_session(),
                    "expires_in": 900,
                    "refresh_expires_at": "2099-01-01T00:00:00Z",
                    "absolute_expires_at": "2099-01-01T00:00:00Z",
                },
            )

        if path.endswith("/auth/sessions") and method == "GET":
            return DemoResponse(
                status,
                [
                    {
                        "id": self._next_session(),
                        "created_at": "2099-01-01T00:00:00Z",
                        "expires_at": "2099-02-01T00:00:00Z",
                        "absolute_expires_at": "2099-02-01T00:00:00Z",
                        "is_current": True,
                    }
                ],
            )

        if path.endswith("/auth/session") and method == "GET":
            return DemoResponse(
                status,
                {
                    "id": self._next_session(),
                    "created_at": "2099-01-01T00:00:00Z",
                    "expires_at": "2099-02-01T00:00:00Z",
                    "absolute_expires_at": "2099-02-01T00:00:00Z",
                    "is_current": True,
                },
            )

        if path.endswith(("/auth/mfa/reset", "/auth/mfa/enroll")):
            return DemoResponse(
                status,
                {
                    "secret": "JBSWY3DPEHPK3PXP",
                    "otpauth_uri": "otpauth://totp/People%20HRMS:demo?secret=JBSWY3DPEHPK3PXP&issuer=People%20HRMS",
                    "recovery_codes": ["DEMO-RECOVERY-1", "DEMO-RECOVERY-2"],
                    "replacing_existing": False,
                },
            )

        if path.endswith(("/auth/mfa/confirm", "/auth/mfa/status")):
            return DemoResponse(
                status,
                {
                    "enabled": path.endswith("/confirm"),
                    "recovery_codes_remaining": 8,
                    "replacement_pending": False,
                },
            )

        if path.endswith(("/auth/mfa/activate", "/auth/mfa/verify")):
            return DemoResponse(
                status,
                {
                    "access_token": f"dry-access-{self._next_session()}",
                    "refresh_token": f"dry-refresh-{self._next_session()}",
                    "session_id": self._next_session(),
                    "mfa_required": False,
                    "mfa_enrollment_required": False,
                },
            )

        if path.endswith("/auth/mfa/recovery/regenerate"):
            return DemoResponse(
                status,
                {
                    "recovery_codes": [
                        "DEMO-RECOVERY-3",
                        "DEMO-RECOVERY-4",
                        "DEMO-RECOVERY-5",
                        "DEMO-RECOVERY-6",
                    ],
                    "recovery_codes_remaining": 4,
                },
            )

        if path.endswith("/auth/password-recovery/start"):
            return DemoResponse(status, {"message": "ok", "recovery_token": "dry-recovery-token", "expires_in": 300})

        if path.endswith("/auth/password-recovery/verify"):
            return DemoResponse(status, {"message": "verified", "recovery_token": "dry-reset-token", "expires_in": 300})

        if path.endswith("/notifications"):
            return DemoResponse(
                status,
                {
                    "items": [
                        {
                            "notification_id": self._next_id(),
                            "title": "Demo notification",
                            "message": "Synthetic workflow event",
                            "notification_type": "workflow",
                            "is_read": False,
                            "created_at": "2099-01-01T00:00:00Z",
                        }
                    ],
                    "total": 1,
                    "page": 1,
                    "page_size": 25,
                    "total_pages": 1,
                },
            )

        if path.endswith("/holidays/lists"):
            return DemoResponse(
                status,
                {"items": [{"id": self._next_id(), "name": "Default 2099"}], "total": 1, "page": 1, "page_size": 25},
            )

        if path.endswith("/overtime/"):
            return DemoResponse(
                status,
                {
                    "items": [
                        {
                            "id": self._next_id(),
                            "employee_id": 1,
                            "attendance_record_id": 1,
                            "calculated_minutes": 60,
                            "approved_minutes": 0,
                            "status": "PENDING",
                            "erp_event_id": "DRY-OT-1",
                        },
                        {
                            "id": self._next_id(),
                            "employee_id": 2,
                            "attendance_record_id": 2,
                            "calculated_minutes": 45,
                            "approved_minutes": 0,
                            "status": "PENDING",
                            "erp_event_id": "DRY-OT-2",
                        },
                    ],
                    "total": 2,
                    "page": 1,
                    "page_size": 25,
                    "total_pages": 1,
                },
            )

        if path.endswith(("/integrations/erp/attendance/records", "/integrations/erp/attendance/records/bulk")):
            records = payload if isinstance(payload, list) else (payload or {}).get("records", [])
            accepted = [
                {"erp_record_id": item["erp_record_id"], "id": self._next_id()}
                for item in records
                if isinstance(item, dict) and item.get("erp_record_id")
            ]
            return DemoResponse(status, {"accepted": accepted, "duplicates": [], "failed": []})

        if path.endswith("/integrations/erp/overtime/records/bulk"):
            accepted = [
                {"erp_event_id": item["erp_event_id"], "id": self._next_id()}
                for item in (payload or [])
                if isinstance(item, dict) and item.get("erp_event_id")
            ]
            return DemoResponse(status, {"accepted": accepted, "duplicates": [], "failed": []})

        if path.endswith("/integrations/erp/leaves/changes"):
            return DemoResponse(status, {"items": [{"event_id": "DRY-LEAVE-EVENT-1"}], "has_more": False})

        if path.endswith("/integrations/erp/shifts/assignments/bulk"):
            employees = (payload or {}).get("employee_ids", [])
            return DemoResponse(
                status,
                [{"id": self._next_id(), "employee_id": employee_id, "shift_id": (payload or {}).get("shift_id", 1)}
                 for employee_id in employees],
            )

        create_like = (
            method == "POST"
            and any(
                marker in path
                for marker in (
                    "/integrations/erp/units",
                    "/integrations/erp/departments",
                    "/integrations/erp/designations",
                    "/integrations/erp/shifts",
                    "/integrations/erp/employees",
                    "/leaves/periods",
                    "/leaves/types",
                    "/leaves/",
                    "/work-arrangements/",
                    "/attendance/corrections",
                )
            )
        )
        if create_like:
            return DemoResponse(status, {"id": self._next_id()})

        if method == "PATCH":
            return DemoResponse(status, {"id": self._next_id()})

        if method == "GET" and any(
            path.endswith(suffix)
            for suffix in (
                "/org/units",
                "/org/departments",
                "/designations/",
                "/employees/",
                "/shifts/",
                "/shifts/assignments",
                "/attendance/",
                "/attendance/checkins",
                "/attendance/corrections",
                "/leaves/periods",
                "/leaves/types",
                "/leaves/",
                "/work-arrangements/",
            )
        ):
            return DemoResponse(status, {"items": [], "total": 0, "page": 1, "page_size": 25, "total_pages": 0})

        return DemoResponse(status, {"id": self._next_id()} if method in {"POST", "PATCH"} else {})


def load_live_openapi_operations(api: ApiClient) -> set[tuple[str, str]] | None:
    if not api.execute:
        return None
    try:
        req = Request(f"{api.origin}/openapi.json", headers={"Accept": "application/json"})
        with urlopen(req, timeout=20) as response:
            spec = json.loads(response.read())
    except Exception as exc:
        print(f"WARNING: could not load live /openapi.json ({exc}); using attached snapshot.")
        return None

    operations: set[tuple[str, str]] = set()
    for path, item in spec.get("paths", {}).items():
        for method in item:
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                operations.add((method.upper(), path))
    return operations


def build_demo_data(run_id: str) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    suffix = re.sub(r"[^A-Za-z0-9]", "", run_id)[-8:] or "DEMO0001"
    short_suffix = suffix[-4:].upper()
    digits = int("".join(ch for ch in suffix if ch.isdigit())[-5:] or "24001")

    def phone(index: int) -> str:
        # Synthetic 10-digit Indian-format mobile number for a local demo DB.
        return f"9{digits % 100000:05d}{index:04d}"[-10:]

    def username(key: str) -> str:
        return f"demo.{key}.{suffix.lower()}"

    def email(key: str) -> str:
        return f"{key}.{suffix.lower()}@example.org"

    organization = {
        "name": "AsterPeak Technologies Private Limited",
        "short_name": "AsterPeak",
        "industry": "Technology Services",
        "address_line1": "42 Innovation Avenue, Outer Ring Road",
        "address_line2": "Bellandur",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "postal_code": "560103",
        "phone": "+91-80-4712-3456",
        "email": "people.ops@example.org",
        "website": "https://example.org/asterpeak",
        "tax_id": f"29DEMO{short_suffix}1Z5",
    }

    units = [
        {"key": "blr", "name": "Bengaluru Head Office", "code": f"APS-BLR-{short_suffix}", "city": "Bengaluru"},
        {"key": "pune", "name": "Pune Delivery Centre", "code": f"APS-PUN-{short_suffix}", "city": "Pune"},
        {"key": "ggn", "name": "Gurugram Commercial Office", "code": f"APS-GGN-{short_suffix}", "city": "Gurugram"},
    ]

    departments = [
        {"key": "people", "unit_key": "blr", "name": "People & Culture", "code": f"APS-PC-{short_suffix}"},
        {"key": "finance", "unit_key": "blr", "name": "Finance & Operations", "code": f"APS-FIN-{short_suffix}"},
        {"key": "product_eng", "unit_key": "blr", "name": "Product Engineering", "code": f"APS-PE-{short_suffix}"},
        {"key": "platform", "unit_key": "pune", "name": "Platform Engineering", "code": f"APS-PLT-{short_suffix}"},
        {"key": "qa", "unit_key": "pune", "name": "Quality Engineering", "code": f"APS-QA-{short_suffix}"},
        {"key": "sales", "unit_key": "ggn", "name": "Sales & Customer Success", "code": f"APS-SALES-{short_suffix}"},
    ]

    designations = [
        {"key": "md", "name": "Managing Director", "code": f"MD-{short_suffix}", "description": "Organization executive leadership"},
        {"key": "people_director", "name": "Director - People", "code": f"DIR-PPL-{short_suffix}", "description": "Organization-wide people leadership"},
        {"key": "hrbp", "name": "HR Business Partner", "code": f"HRBP-{short_suffix}", "description": "Unit HR operations"},
        {"key": "eng_manager", "name": "Engineering Manager", "code": f"EM-{short_suffix}", "description": "Engineering people manager"},
        {"key": "senior_engineer", "name": "Senior Software Engineer", "code": f"SSE-{short_suffix}", "description": "Senior individual contributor"},
        {"key": "engineer", "name": "Software Engineer", "code": f"SE-{short_suffix}", "description": "Software engineer"},
        {"key": "qa_manager", "name": "QA Manager", "code": f"QAM-{short_suffix}", "description": "Quality engineering manager"},
        {"key": "qa_engineer", "name": "QA Engineer", "code": f"QAE-{short_suffix}", "description": "Quality engineer"},
        {"key": "finance_manager", "name": "Finance Manager", "code": f"FM-{short_suffix}", "description": "Finance manager"},
        {"key": "finance_analyst", "name": "Finance Analyst", "code": f"FA-{short_suffix}", "description": "Finance analyst"},
        {"key": "sales_manager", "name": "Sales Manager", "code": f"SM-{short_suffix}", "description": "Commercial team manager"},
        {"key": "account_exec", "name": "Account Executive", "code": f"AE-{short_suffix}", "description": "Customer-facing account executive"},
    ]

    shifts = [
        {
            "key": "blr_general",
            "unit_key": "blr",
            "name": "Bengaluru General Shift",
            "code": f"BLR-GEN-{short_suffix}",
            "start_time": "09:30:00",
            "end_time": "18:30:00",
            "grace_minutes": 10,
            "break_minutes": 30,
            "is_cross_midnight": False,
            "is_active": True,
            "begin_check_in_before_minutes": 60,
            "allow_check_out_after_minutes": 120,
            "late_entry_grace_minutes": 10,
            "early_exit_grace_minutes": 10,
            "half_day_threshold_hours": 4.0,
            "absent_threshold_hours": 2.0,
            "enable_auto_attendance": True,
        },
        {
            "key": "pune_early",
            "unit_key": "pune",
            "name": "Pune Engineering Shift",
            "code": f"PUN-ENG-{short_suffix}",
            "start_time": "08:30:00",
            "end_time": "17:30:00",
            "grace_minutes": 10,
            "break_minutes": 30,
            "is_cross_midnight": False,
            "is_active": True,
            "begin_check_in_before_minutes": 60,
            "allow_check_out_after_minutes": 120,
            "late_entry_grace_minutes": 10,
            "early_exit_grace_minutes": 10,
            "half_day_threshold_hours": 4.0,
            "absent_threshold_hours": 2.0,
            "enable_auto_attendance": True,
        },
        {
            "key": "ggn_sales",
            "unit_key": "ggn",
            "name": "Gurugram Commercial Shift",
            "code": f"GGN-SALES-{short_suffix}",
            "start_time": "10:00:00",
            "end_time": "19:00:00",
            "grace_minutes": 10,
            "break_minutes": 30,
            "is_cross_midnight": False,
            "is_active": True,
            "begin_check_in_before_minutes": 60,
            "allow_check_out_after_minutes": 120,
            "late_entry_grace_minutes": 10,
            "early_exit_grace_minutes": 10,
            "half_day_threshold_hours": 4.0,
            "absent_threshold_hours": 2.0,
            "enable_auto_attendance": True,
        },
    ]

    raw_employees = [
        # key, first, last, unit, dept, designation, shift, manager, role, business_role, scope, salary, joining
        ("owner", "Arjun", "Mehta", "blr", "people", "md", "blr_general", None,
         "ORGANIZATION_OWNER", "ORGANIZATION_OWNER", "ORGANIZATION", 650000, "2021-04-01"),
        ("org_hr", "Kavya", "Iyer", "blr", "people", "people_director", "blr_general", "owner",
         "HR_ADMIN", "HR_ADMIN", "ORGANIZATION", 325000, "2021-07-12"),
        ("blr_hr", "Neha", "Bansal", "blr", "people", "hrbp", "blr_general", "org_hr",
         "HR_ADMIN", "HR_ADMIN", "UNIT", 145000, "2023-02-06"),
        ("eng_manager", "Rohan", "Kapoor", "blr", "product_eng", "eng_manager", "blr_general", "owner",
         "DEPARTMENT_MANAGER", "DEPARTMENT_MANAGER", "DEPARTMENT", 250000, "2022-06-13"),
        ("eng_aisha", "Aisha", "Verma", "blr", "product_eng", "senior_engineer", "blr_general", "eng_manager",
         "EMPLOYEE", None, "SELF", 195000, "2023-01-16"),
        ("eng_karan", "Karan", "Shah", "blr", "product_eng", "engineer", "blr_general", "eng_manager",
         "EMPLOYEE", None, "SELF", 135000, "2024-03-04"),
        ("eng_nikhil", "Nikhil", "Sethi", "blr", "product_eng", "engineer", "blr_general", "eng_manager",
         "EMPLOYEE", None, "SELF", 125000, "2025-01-20"),
        ("security", "Tara", "Sen", "blr", "product_eng", "engineer", "blr_general", "eng_manager",
         "EMPLOYEE", None, "SELF", 118000, "2025-07-07"),
        ("password_target", "Mihir", "Jain", "blr", "product_eng", "engineer", "blr_general", "eng_manager",
         "EMPLOYEE", None, "SELF", 112000, "2026-01-05"),
        ("fin_manager", "Priya", "Nair", "blr", "finance", "finance_manager", "blr_general", "owner",
         "DEPARTMENT_MANAGER", "DEPARTMENT_MANAGER", "DEPARTMENT", 220000, "2022-09-01"),
        ("fin_analyst", "Vivek", "Rao", "blr", "finance", "finance_analyst", "blr_general", "fin_manager",
         "EMPLOYEE", None, "SELF", 105000, "2024-08-12"),
        ("pune_manager", "Ananya", "Kulkarni", "pune", "platform", "eng_manager", "pune_early", "owner",
         "DEPARTMENT_MANAGER", "DEPARTMENT_MANAGER", "DEPARTMENT", 235000, "2022-11-14"),
        ("pune_engineer", "Siddharth", "Patil", "pune", "platform", "senior_engineer", "pune_early", "pune_manager",
         "EMPLOYEE", None, "SELF", 175000, "2024-02-19"),
        ("qa_manager", "Meera", "Joshi", "pune", "qa", "qa_manager", "pune_early", "pune_manager",
         "DEPARTMENT_MANAGER", "DEPARTMENT_MANAGER", "DEPARTMENT", 205000, "2023-05-22"),
        ("qa_engineer", "Aditya", "Deshmukh", "pune", "qa", "qa_engineer", "pune_early", "qa_manager",
         "EMPLOYEE", None, "SELF", 110000, "2025-02-10"),
        ("lifecycle", "Ritu", "Menon", "pune", "qa", "qa_engineer", "pune_early", "qa_manager",
         "EMPLOYEE", None, "SELF", 98000, "2026-02-02"),
        ("sales_manager", "Rahul", "Arora", "ggn", "sales", "sales_manager", "ggn_sales", "owner",
         "DEPARTMENT_MANAGER", "DEPARTMENT_MANAGER", "DEPARTMENT", 240000, "2022-04-18"),
        ("sales_exec", "Isha", "Malhotra", "ggn", "sales", "account_exec", "ggn_sales", "sales_manager",
         "EMPLOYEE", None, "SELF", 145000, "2024-06-03"),
    ]

    employees: list[dict[str, Any]] = []
    for index, row in enumerate(raw_employees, start=1):
        (
            key,
            first,
            last,
            unit_key,
            department_key,
            designation_key,
            shift_key,
            manager_key,
            role,
            business_role,
            access_scope,
            salary,
            joining,
        ) = row
        employees.append(
            {
                "key": key,
                "employee_code": f"APS-{short_suffix}-{index:03d}",
                "username": username(key),
                "official_email": email(key),
                "phone_number": phone(index),
                "first_name": first,
                "last_name": last,
                "role": role,
                "business_role": business_role,
                "access_scope": access_scope,
                "unit_key": unit_key,
                "department_key": department_key,
                "designation_key": designation_key,
                "shift_key": shift_key,
                "manager_key": manager_key,
                "date_of_joining": joining,
                "employment_type": "PERMANENT",
                "biometric_id": f"APS-BIO-{short_suffix}-{index:03d}",
                "overtime_eligible": key not in {"owner", "org_hr"},
                "monthly_salary": salary,
                "gender": "FEMALE" if first in {"Kavya", "Neha", "Aisha", "Tara", "Priya", "Ananya", "Meera", "Ritu", "Isha"} else "MALE",
            }
        )

    leave_codes = {
        "casual": f"CL{short_suffix}",
        "sick": f"SL{short_suffix}",
        "earned": f"EL{short_suffix}",
        "lop": f"LOP{short_suffix}",
    }

    leave_periods = [
        {
            "name": f"Calendar Year {today.year} - {short_suffix}",
            "from_date": f"{today.year}-01-01",
            "to_date": f"{today.year}-12-31",
            "is_active": True,
        }
    ]

    leave_types = [
        {
            "key": "casual",
            "name": "Casual Leave",
            "code": leave_codes["casual"],
            "is_paid": True,
            "annual_allocation": 12,
            "max_consecutive_days": 3,
            "requires_approval": True,
            "carry_forward": False,
            "include_holidays": False,
            "is_active": True,
        },
        {
            "key": "sick",
            "name": "Sick Leave",
            "code": leave_codes["sick"],
            "is_paid": True,
            "annual_allocation": 10,
            "max_consecutive_days": 5,
            "requires_approval": True,
            "carry_forward": False,
            "include_holidays": False,
            "is_active": True,
        },
        {
            "key": "earned",
            "name": "Earned Leave",
            "code": leave_codes["earned"],
            "is_paid": True,
            "annual_allocation": 18,
            "max_consecutive_days": 10,
            "requires_approval": True,
            "carry_forward": True,
            "include_holidays": False,
            "is_active": True,
        },
        {
            "key": "lop",
            "name": "Loss of Pay",
            "code": leave_codes["lop"],
            "is_paid": False,
            "annual_allocation": 0,
            "max_consecutive_days": None,
            "requires_approval": True,
            "carry_forward": False,
            "include_holidays": False,
            "is_active": True,
        },
    ]

    holidays = [
        {
            "erp_holiday_id": f"APS-{short_suffix}-HOL-REPUBLIC",
            "name": "Republic Day",
            "holiday_date": f"{today.year}-01-26",
            "description": "Organization holiday",
            "is_active": True,
        },
        {
            "erp_holiday_id": f"APS-{short_suffix}-HOL-FOUNDATION",
            "name": "AsterPeak Foundation Day",
            "holiday_date": f"{today.year}-07-15",
            "description": "Company foundation day",
            "is_active": True,
        },
        {
            "erp_holiday_id": f"APS-{short_suffix}-HOL-INDEPENDENCE",
            "name": "Independence Day",
            "holiday_date": f"{today.year}-08-15",
            "description": "Organization holiday",
            "is_active": True,
        },
        {
            "erp_holiday_id": f"APS-{short_suffix}-HOL-GANDHI",
            "name": "Gandhi Jayanti",
            "holiday_date": f"{today.year}-10-02",
            "description": "Organization holiday",
            "is_active": True,
        },
        {
            "erp_holiday_id": f"APS-{short_suffix}-HOL-YEAREND",
            "name": "Year-end Company Holiday",
            "holiday_date": f"{today.year}-12-31",
            "description": "Company-wide year-end holiday",
            "is_active": True,
        },
    ]

    # Realistic attendance for the latest 8 weekdays. A few records intentionally
    # show absence/half-day/late arrival so dashboards and filters are meaningful.
    attendance_dates = recent_weekdays(today, 8)
    skip_today = {"eng_aisha", "eng_karan", "eng_nikhil", "security"}
    employee_map = {item["key"]: item for item in employees}
    shift_start = {"blr_general": "09:30:00", "pune_early": "08:30:00", "ggn_sales": "10:00:00"}
    shift_end = {"blr_general": "18:30:00", "pune_early": "17:30:00", "ggn_sales": "19:00:00"}

    attendance: list[dict[str, Any]] = []
    attendance_index = 0
    for employee_index, employee in enumerate(employees):
        if employee["key"] in {"owner"}:
            # Keep the MD in headcount but avoid cluttering operational attendance.
            continue
        for day_index, attendance_day in enumerate(attendance_dates):
            if attendance_day == today and employee["key"] in skip_today:
                continue
            attendance_index += 1
            pattern = (employee_index * 5 + day_index * 3) % 17
            status = "PRESENT"
            punch_in = shift_start[employee["shift_key"]]
            punch_out = shift_end[employee["shift_key"]]
            worked_minutes = 510
            overtime_minutes = 0
            late_minutes = 0
            early_exit_minutes = 0

            if pattern == 1:
                status = "ABSENT"
                punch_in = None
                punch_out = None
                worked_minutes = 0
            elif pattern == 5:
                status = "HALF_DAY"
                punch_in = shift_start[employee["shift_key"]]
                punch_out = "13:30:00"
                worked_minutes = 240
                early_exit_minutes = 240
            elif pattern in {7, 12}:
                # Present but late.
                if employee["shift_key"] == "pune_early":
                    punch_in = "08:52:00"
                elif employee["shift_key"] == "ggn_sales":
                    punch_in = "10:24:00"
                else:
                    punch_in = "09:55:00"
                worked_minutes = 485
                late_minutes = 15

            # Seed meaningful pending overtime for three employees on the latest
            # available attendance day.
            if attendance_day == attendance_dates[-1] and employee["key"] in {
                "eng_aisha",
                "eng_karan",
                "sales_exec",
            }:
                if employee["shift_key"] == "ggn_sales":
                    punch_out = "20:30:00"
                elif employee["shift_key"] == "pune_early":
                    punch_out = "19:00:00"
                else:
                    punch_out = "20:00:00"
                worked_minutes = 600
                overtime_minutes = 90
                status = "PRESENT"

            attendance.append(
                {
                    "key": f"{employee['key']}_{attendance_day.isoformat()}",
                    "employee_key": employee["key"],
                    "shift_key": employee["shift_key"],
                    "erp_record_id": f"APS-{short_suffix}-ATT-{attendance_index:05d}",
                    "attendance_date": attendance_day.isoformat(),
                    "status": status,
                    "punch_in": punch_in,
                    "punch_out": punch_out,
                    "worked_minutes": worked_minutes,
                    "overtime_minutes": overtime_minutes,
                    "late_minutes": late_minutes,
                    "early_exit_minutes": early_exit_minutes,
                }
            )

    attendance_by_emp: dict[str, list[dict[str, Any]]] = {}
    for record in attendance:
        attendance_by_emp.setdefault(record["employee_key"], []).append(record)

    overtime: list[dict[str, Any]] = []
    for index, employee_key in enumerate(("eng_aisha", "eng_karan", "sales_exec"), start=1):
        candidates = attendance_by_emp[employee_key]
        attendance_item = candidates[-1]
        employee = employee_map[employee_key]
        day = attendance_item["attendance_date"]
        if employee["shift_key"] == "ggn_sales":
            start_time, end_time = "19:00:00", "20:30:00"
        elif employee["shift_key"] == "pune_early":
            start_time, end_time = "17:30:00", "19:00:00"
        else:
            start_time, end_time = "18:30:00", "20:00:00"
        overtime.append(
            {
                "erp_event_id": f"APS-{short_suffix}-OT-{index:03d}",
                "employee_key": employee_key,
                "attendance_key": attendance_item["key"],
                "overtime_start": f"{day}T{start_time}+05:30",
                "overtime_end": f"{day}T{end_time}+05:30",
                "calculated_minutes": 90,
                "approved_minutes": 0,
                "status": "PENDING",
            }
        )

    leave_balances: list[dict[str, Any]] = []
    for employee_index, employee in enumerate(employees):
        for key, allocated in (("casual", 12), ("sick", 10), ("earned", 18), ("lop", 0)):
            used = 0 if key == "lop" else (employee_index + len(key)) % 4
            leave_balances.append(
                {
                    "employee_key": employee["key"],
                    "leave_code": leave_codes[key],
                    "year": today.year,
                    "allocated": allocated,
                    "used": used,
                    "pending": 0,
                }
            )

    return {
        "run_id": run_id,
        "suffix": suffix,
        "short_suffix": short_suffix,
        "today": today,
        "organization": organization,
        "units": units,
        "departments": departments,
        "designations": designations,
        "shifts": shifts,
        "employees": employees,
        "employee_map": employee_map,
        "leave_periods": leave_periods,
        "leave_types": leave_types,
        "leave_codes": leave_codes,
        "leave_balances": leave_balances,
        "holidays": holidays,
        "attendance": attendance,
        "overtime": overtime,
        "attendance_dates": attendance_dates,
    }


@dataclass
class DemoContext:
    data: dict[str, Any]
    unit_ids: dict[str, int]
    department_ids: dict[str, int]
    designation_ids: dict[str, int]
    shift_ids: dict[str, int]
    employee_ids: dict[str, int]
    assignment_ids: dict[str, int]
    attendance_ids: dict[str, int]
    leave_type_ids: dict[str, int]
    tokens: dict[str, dict[str, Any]]
    overtime_ids: dict[str, int]


def new_context(data: dict[str, Any]) -> DemoContext:
    return DemoContext(
        data=data,
        unit_ids={},
        department_ids={},
        designation_ids={},
        shift_ids={},
        employee_ids={},
        assignment_ids={},
        attendance_ids={},
        leave_type_ids={},
        tokens={},
        overtime_ids={},
    )


def make_employee_payload(ctx: DemoContext, item: dict[str, Any], password: str) -> dict[str, Any]:
    payload = without_keys(
        item,
        "key",
        "unit_key",
        "department_key",
        "designation_key",
        "shift_key",
        "manager_key",
    )
    access_scope = item.get("access_scope")
    access_scope_id: int | None
    if access_scope == "DEPARTMENT":
        access_scope_id = ctx.department_ids[item["department_key"]]
    elif access_scope == "UNIT":
        access_scope_id = ctx.unit_ids[item["unit_key"]]
    else:
        access_scope_id = None

    payload.update(
        {
            "unit_id": ctx.unit_ids[item["unit_key"]],
            "department_id": ctx.department_ids[item["department_key"]],
            "designation_id": ctx.designation_ids[item["designation_key"]],
            "shift_id": ctx.shift_ids[item["shift_key"]],
            "reporting_manager_id": ctx.employee_ids.get(item.get("manager_key")),
            "access_scope_id": access_scope_id,
            "initial_password": password,
            "create_user_account": True,
        }
    )
    return payload


def bearer(ctx: DemoContext, actor: str) -> str:
    token = ctx.tokens.get(actor, {}).get("access_token")
    if not token:
        raise DemoError(f"No access token available for actor {actor!r}")
    return str(token)


def refresh_token(ctx: DemoContext, actor: str) -> str:
    token = ctx.tokens.get(actor, {}).get("refresh_token")
    if not token:
        raise DemoError(f"No refresh token available for actor {actor!r}")
    return str(token)


def business_login(api: ApiClient, ctx: DemoContext, actor: str, password: str) -> dict[str, Any]:
    employee = ctx.data["employee_map"][actor]
    response = api.request(
        "POST",
        "auth/employee/login",
        {"username": employee["username"], "password": password},
        form=True,
        expected={200},
        label=f"Business login: {actor}",
    )
    body = response.body if isinstance(response.body, dict) else {}
    ctx.tokens[actor] = dict(body)
    return body


def seed_erp_data(api: ApiClient, ctx: DemoContext, initial_password: str) -> None:
    data = ctx.data

    print("\n" + "=" * 80)
    print("PHASE 1 — ERP-owned realistic demo data")
    print("=" * 80)

    api.request(
        "PATCH",
        "integrations/erp/organization",
        data["organization"],
        api_key=True,
        expected={200},
        label="ERP organization sync",
    )

    for item in data["units"]:
        response = api.request(
            "POST",
            "integrations/erp/units",
            without_keys(item, "key"),
            api_key=True,
            expected={201},
            label=f"Create unit: {item['name']}",
        )
        ctx.unit_ids[item["key"]] = require_id(response.body, f"unit {item['key']}")

    for item in data["departments"]:
        payload = without_keys(item, "key", "unit_key") | {"unit_id": ctx.unit_ids[item["unit_key"]]}
        response = api.request(
            "POST",
            "integrations/erp/departments",
            payload,
            api_key=True,
            expected={201},
            label=f"Create department: {item['name']}",
        )
        ctx.department_ids[item["key"]] = require_id(response.body, f"department {item['key']}")

    for item in data["designations"]:
        response = api.request(
            "POST",
            "integrations/erp/designations",
            without_keys(item, "key"),
            api_key=True,
            expected={201},
            label=f"Create designation: {item['name']}",
        )
        ctx.designation_ids[item["key"]] = require_id(response.body, f"designation {item['key']}")

    for item in data["shifts"]:
        payload = without_keys(item, "key", "unit_key") | {"unit_id": ctx.unit_ids[item["unit_key"]]}
        response = api.request(
            "POST",
            "integrations/erp/shifts",
            payload,
            api_key=True,
            expected={201},
            label=f"Create shift: {item['name']}",
        )
        ctx.shift_ids[item["key"]] = require_id(response.body, f"shift {item['key']}")

    # Exercise shift update against a real retained shift.
    api.request(
        "PATCH",
        f"integrations/erp/shifts/{ctx.shift_ids['blr_general']}",
        {"grace_minutes": 12, "late_entry_grace_minutes": 12},
        api_key=True,
        expected={200},
        label="Update Bengaluru shift grace period",
    )

    for item in data["employees"]:
        response = api.request(
            "POST",
            "integrations/erp/employees",
            make_employee_payload(ctx, item, initial_password),
            api_key=True,
            expected={200},
            label=f"Create employee: {item['first_name']} {item['last_name']}",
        )
        ctx.employee_ids[item["key"]] = require_id(response.body, f"employee {item['key']}")

    # Employee update and lifecycle APIs on a dedicated synthetic employee.
    lifecycle_id = ctx.employee_ids["lifecycle"]
    api.request(
        "PATCH",
        f"integrations/erp/employees/{lifecycle_id}",
        {
            "monthly_salary": 102000,
            "employment_type": "PERMANENT",
            "overtime_eligible": True,
        },
        api_key=True,
        expected={200},
        label="Update lifecycle-demo employee",
    )
    api.request(
        "PATCH",
        f"integrations/erp/employees/{lifecycle_id}/deactivate",
        {
            "exit_date": data["today"].isoformat(),
            "exit_reason": "Temporary lifecycle API demonstration",
        },
        api_key=True,
        expected={200},
        label="Deactivate lifecycle-demo employee",
    )
    api.request(
        "PATCH",
        f"integrations/erp/employees/{lifecycle_id}/activate",
        api_key=True,
        expected={200},
        label="Reactivate lifecycle-demo employee",
    )

    # ERP password-reset API uses a dedicated account that is not needed for login flows.
    api.request(
        "POST",
        f"auth/integrations/erp/employees/{ctx.employee_ids['password_target']}/password-reset",
        {"temporary_password": PASSWORD_TARGET_ERP},
        api_key=True,
        expected={200},
        label="ERP temporary password reset",
    )

    # Single shift assignment.
    first = data["employee_map"]["owner"]
    response = api.request(
        "POST",
        "integrations/erp/shifts/assignments",
        {
            "employee_id": ctx.employee_ids["owner"],
            "shift_id": ctx.shift_ids[first["shift_key"]],
            "effective_from": first["date_of_joining"],
        },
        api_key=True,
        expected={201},
        label="Assign MD shift",
    )
    ctx.assignment_ids["owner"] = require_id(response.body, "owner shift assignment")

    # Reserve one employee for the shift-assignment cancellation lifecycle test.
    #
    # Shift assignments are open-ended by default. Creating a second future
    # assignment for an employee who already has an ACTIVE open-ended assignment
    # correctly fails the API's overlap invariant. Therefore the lifecycle employee
    # is deliberately excluded from the initial bulk assignment. We create and
    # cancel a future assignment first, then install the employee's real current
    # assignment after the cancelled record can no longer overlap.
    shift_lifecycle_key = "security"

    # Bulk assignment grouped by shift for the remaining employees.
    bulk_excluded = {"owner", shift_lifecycle_key}
    for shift_key in sorted({item["shift_key"] for item in data["employees"] if item["key"] not in bulk_excluded}):
        selected = [
            item
            for item in data["employees"]
            if item["key"] not in bulk_excluded and item["shift_key"] == shift_key
        ]
        response = api.request(
            "POST",
            "integrations/erp/shifts/assignments/bulk",
            {
                "shift_id": ctx.shift_ids[shift_key],
                "effective_from": min(item["date_of_joining"] for item in selected),
                "employee_ids": [ctx.employee_ids[item["key"]] for item in selected],
            },
            api_key=True,
            expected={201},
            label=f"Bulk assign {shift_key}",
        )
        if isinstance(response.body, list):
            for item, created in zip(selected, response.body):
                if isinstance(created, dict) and isinstance(created.get("id"), int):
                    ctx.assignment_ids[item["key"]] = int(created["id"])

    # Exercise assignment cancellation without violating the no-overlap rule.
    lifecycle_employee = data["employee_map"][shift_lifecycle_key]
    future_assignment = api.request(
        "POST",
        "integrations/erp/shifts/assignments",
        {
            "employee_id": ctx.employee_ids[shift_lifecycle_key],
            "shift_id": ctx.shift_ids[lifecycle_employee["shift_key"]],
            "effective_from": next_weekday(data["today"], 30).isoformat(),
        },
        api_key=True,
        expected={201},
        label="Create cancellable future shift assignment",
    )
    future_assignment_id = require_id(future_assignment.body, "future shift assignment")
    api.request(
        "PATCH",
        f"integrations/erp/shifts/assignments/{future_assignment_id}/cancel",
        api_key=True,
        expected={200},
        label="Cancel future shift assignment",
    )

    # Restore the employee's realistic active assignment after the cancellation
    # test. This leaves the final demo data in the same usable state as every
    # other employee.
    response = api.request(
        "POST",
        "integrations/erp/shifts/assignments",
        {
            "employee_id": ctx.employee_ids[shift_lifecycle_key],
            "shift_id": ctx.shift_ids[lifecycle_employee["shift_key"]],
            "effective_from": lifecycle_employee["date_of_joining"],
        },
        api_key=True,
        expected={201},
        label="Assign active shift after cancellation test",
    )
    ctx.assignment_ids[shift_lifecycle_key] = require_id(response.body, "active shift assignment after cancellation")

    api.request(
        "POST",
        "integrations/erp/holidays/bulk",
        data["holidays"],
        api_key=True,
        expected={200},
        label="Sync organization holidays",
    )

    # Attendance single endpoint gets one row, bulk gets all remaining rows.
    attendance_payloads: list[dict[str, Any]] = []
    for item in data["attendance"]:
        employee = data["employee_map"][item["employee_key"]]
        attendance_payloads.append(
            without_keys(item, "key", "employee_key", "shift_key")
            | {
                "employee_id": ctx.employee_ids[item["employee_key"]],
                "employee_code": employee["employee_code"],
                "shift_id": ctx.shift_ids[item["shift_key"]],
            }
        )

    first_response = api.request(
        "POST",
        "integrations/erp/attendance/records",
        [attendance_payloads[0]],
        api_key=True,
        expected={200},
        label="Sync one attendance record",
    )
    for item in (first_response.body or {}).get("accepted", []) if isinstance(first_response.body, dict) else []:
        if item.get("erp_record_id") and item.get("id") is not None:
            ctx.attendance_ids[str(item["erp_record_id"])] = int(item["id"])

    bulk_response = api.request(
        "POST",
        "integrations/erp/attendance/records/bulk",
        {"records": attendance_payloads[1:]},
        api_key=True,
        expected={200},
        label=f"Bulk sync {len(attendance_payloads) - 1} attendance records",
    )
    if isinstance(bulk_response.body, dict):
        for item in [*bulk_response.body.get("accepted", []), *bulk_response.body.get("duplicates", [])]:
            if isinstance(item, dict) and item.get("erp_record_id") and item.get("id") is not None:
                ctx.attendance_ids[str(item["erp_record_id"])] = int(item["id"])

    # Leave master data is ERP-owned in the current OpenAPI contract.
    for item in data["leave_periods"]:
        api.request(
            "POST",
            "leaves/periods",
            item,
            api_key=True,
            expected={201},
            label=f"Create leave period: {item['name']}",
        )

    for item in data["leave_types"]:
        response = api.request(
            "POST",
            "leaves/types",
            without_keys(item, "key"),
            api_key=True,
            expected={201},
            label=f"Create leave type: {item['name']}",
        )
        ctx.leave_type_ids[item["key"]] = require_id(response.body, f"leave type {item['key']}")

    # Exercise ERP leave-type update with a harmless description-equivalent field.
    api.request(
        "PATCH",
        f"leaves/types/{ctx.leave_type_ids['casual']}",
        {"max_consecutive_days": 3, "is_active": True},
        api_key=True,
        expected={200},
        label="Update Casual Leave policy",
    )

    balances = [
        without_keys(item, "employee_key")
        | {
            "employee_id": ctx.employee_ids[item["employee_key"]],
            "employee_code": data["employee_map"][item["employee_key"]]["employee_code"],
        }
        for item in data["leave_balances"]
    ]
    api.request(
        "POST",
        "integrations/erp/leaves/balances",
        balances[:1],
        api_key=True,
        expected={200},
        label="Sync one leave balance",
    )
    api.request(
        "POST",
        "integrations/erp/leaves/balances/bulk",
        balances[1:],
        api_key=True,
        expected={200},
        label=f"Bulk sync {len(balances) - 1} leave balances",
    )

    overtime_payload: list[dict[str, Any]] = []
    attendance_by_key = {item["key"]: item for item in data["attendance"]}
    for item in data["overtime"]:
        attendance_item = attendance_by_key[item["attendance_key"]]
        attendance_record_id = ctx.attendance_ids.get(attendance_item["erp_record_id"])
        if attendance_record_id is None:
            if api.execute:
                raise DemoError(
                    f"No attendance id returned for {attendance_item['erp_record_id']}; cannot link overtime."
                )
            attendance_record_id = 1
        overtime_payload.append(
            without_keys(item, "employee_key", "attendance_key")
            | {
                "employee_id": ctx.employee_ids[item["employee_key"]],
                "employee_code": data["employee_map"][item["employee_key"]]["employee_code"],
                "attendance_record_id": attendance_record_id,
            }
        )
    overtime_response = api.request(
        "POST",
        "integrations/erp/overtime/records/bulk",
        overtime_payload,
        api_key=True,
        expected={200},
        label="Sync pending overtime records",
    )
    if isinstance(overtime_response.body, dict):
        for item in overtime_response.body.get("accepted", []):
            if isinstance(item, dict) and item.get("erp_event_id") and item.get("id") is not None:
                ctx.overtime_ids[str(item["erp_event_id"])] = int(item["id"])

    # Scratch CRUD proves ERP update/delete APIs without damaging retained demo data.
    scratch_unit = api.request(
        "POST",
        "integrations/erp/units",
        {"name": f"Temporary API Test Unit {data['short_suffix']}", "code": f"TMP-U-{data['short_suffix']}", "city": "Bengaluru"},
        api_key=True,
        expected={201},
        label="Create scratch unit for CRUD coverage",
    )
    scratch_unit_id = require_id(scratch_unit.body, "scratch unit")
    api.request(
        "PATCH",
        f"integrations/erp/units/{scratch_unit_id}",
        {"city": "Mysuru", "is_active": False},
        api_key=True,
        expected={200},
        label="Update scratch unit",
    )

    scratch_department = api.request(
        "POST",
        "integrations/erp/departments",
        {
            "name": f"Temporary Department {data['short_suffix']}",
            "code": f"TMP-D-{data['short_suffix']}",
            "unit_id": scratch_unit_id,
        },
        api_key=True,
        expected={201},
        label="Create scratch department for CRUD coverage",
    )
    scratch_department_id = require_id(scratch_department.body, "scratch department")
    api.request(
        "PATCH",
        f"integrations/erp/departments/{scratch_department_id}",
        {"name": f"Temporary Department Updated {data['short_suffix']}", "is_active": False},
        api_key=True,
        expected={200},
        label="Update scratch department",
    )

    scratch_designation = api.request(
        "POST",
        "integrations/erp/designations",
        {
            "name": f"Temporary Designation {data['short_suffix']}",
            "code": f"TMP-DSG-{data['short_suffix']}",
            "description": "Created and removed by full API demo",
        },
        api_key=True,
        expected={201},
        label="Create scratch designation for CRUD coverage",
    )
    scratch_designation_id = require_id(scratch_designation.body, "scratch designation")
    api.request(
        "PATCH",
        f"integrations/erp/designations/{scratch_designation_id}",
        {"description": "Updated before deletion", "is_active": False},
        api_key=True,
        expected={200},
        label="Update scratch designation",
    )

    api.request(
        "DELETE",
        f"integrations/erp/departments/{scratch_department_id}",
        api_key=True,
        expected={204},
        label="Delete scratch department",
    )
    api.request(
        "DELETE",
        f"integrations/erp/units/{scratch_unit_id}",
        api_key=True,
        expected={204},
        label="Delete scratch unit",
    )
    api.request(
        "DELETE",
        f"integrations/erp/designations/{scratch_designation_id}",
        api_key=True,
        expected={204},
        label="Delete scratch designation",
    )


def login_business_actors(api: ApiClient, ctx: DemoContext, initial_password: str) -> None:
    print("\n" + "=" * 80)
    print("PHASE 2 — Business authentication for role/scope coverage")
    print("=" * 80)

    for actor in (
        "owner",
        "org_hr",
        "blr_hr",
        "eng_manager",
        "eng_aisha",
        "eng_karan",
        "eng_nikhil",
        "security",
    ):
        business_login(api, ctx, actor, initial_password)


def exercise_read_apis(api: ApiClient, ctx: DemoContext) -> None:
    data = ctx.data
    hr_token = bearer(ctx, "blr_hr")
    manager_token = bearer(ctx, "eng_manager")
    employee_token = bearer(ctx, "eng_aisha")
    owner_token = bearer(ctx, "owner")

    print("\n" + "=" * 80)
    print("PHASE 3 — Account, directory, organization, shifts, attendance reads")
    print("=" * 80)

    api.request("GET", "users/me", token=employee_token, expected={200})
    api.request("GET", "users/me/permissions", token=employee_token, expected={200})

    api.request(
        "GET",
        "dashboard/metrics",
        token=manager_token,
        expected={200},
        label="Manager dashboard metrics",
    )
    api.request(
        "GET",
        "dashboard/widgets",
        token=manager_token,
        expected={200},
        label="Permission-aware dashboard widgets",
    )

    api.request("GET", "org/organization", token=hr_token, expected={200})

    api.request(
        "GET",
        "org/units",
        token=hr_token,
        query={"page": 1, "page_size": 2, "search": "Office", "sort_by": "name", "sort_order": "asc"},
        expected={200},
        label="Paginated/filterable units",
    )
    api.request("GET", f"org/units/{ctx.unit_ids['blr']}", token=hr_token, expected={200})

    api.request(
        "GET",
        "org/departments",
        token=hr_token,
        query={
            "unit_id": ctx.unit_ids["blr"],
            "page": 1,
            "page_size": 3,
            "search": "",
            "sort_by": "name",
            "sort_order": "asc",
        },
        expected={200},
    )
    api.request(
        "GET",
        f"org/departments/{ctx.department_ids['product_eng']}",
        token=hr_token,
        expected={200},
    )

    api.request(
        "GET",
        "designations/",
        token=hr_token,
        query={"is_active": True, "page": 1, "page_size": 5, "sort_by": "name", "sort_order": "asc"},
        expected={200},
    )
    api.request(
        "GET",
        f"designations/{ctx.designation_ids['engineer']}",
        token=hr_token,
        expected={200},
    )

    api.request(
        "GET",
        "employees/",
        token=hr_token,
        query={
            "page": 1,
            "page_size": 5,
            "search": "a",
            "unit_id": ctx.unit_ids["blr"],
            "status": "ACTIVE",
            # The employees API validates sort_by against an internal allowlist,
            # while the OpenAPI contract currently exposes it only as a free-form
            # string. Do not guess a field here: use the endpoint's default stable
            # ordering so this demo remains compatible with the published contract.
        },
        expected={200},
        label="Server-paginated employee directory",
    )
    api.request(
        "GET",
        f"employees/{ctx.employee_ids['eng_aisha']}",
        token=manager_token,
        expected={200},
    )
    api.request(
        "GET",
        f"employees/{ctx.employee_ids['lifecycle']}/work-history",
        token=owner_token,
        query={"page": 1, "page_size": 10, "sort_by": "created_at", "sort_order": "desc"},
        expected={200},
    )

    # Retired browser-side employee onboarding endpoint is intentionally exercised.
    legacy_payload = {
        "employee_code": f"LEGACY-{data['short_suffix']}",
        "first_name": "Legacy",
        "last_name": "Blocked",
        "phone_number": "9000000001",
        "initial_password": DEFAULT_INITIAL_PASSWORD,
        "create_user_account": True,
    }
    api.request(
        "POST",
        "employees/onboard",
        legacy_payload,
        token=hr_token,
        expected={410},
        label="Expected 410: employee onboarding is ERP-owned",
    )

    api.request(
        "GET",
        "shifts/",
        token=hr_token,
        query={"page": 1, "page_size": 5, "unit_id": ctx.unit_ids["blr"], "is_active": True},
        expected={200},
    )
    api.request("GET", f"shifts/{ctx.shift_ids['blr_general']}", token=hr_token, expected={200})

    api.request(
        "GET",
        "shifts/assignments",
        token=hr_token,
        query={"page": 1, "page_size": 5, "employee_id": ctx.employee_ids["owner"], "status": "ACTIVE"},
        expected={200},
    )
    api.request(
        "GET",
        f"shifts/assignments/{ctx.assignment_ids['owner']}",
        token=hr_token,
        expected={200},
    )
    api.request(
        "GET",
        f"shifts/employee/{ctx.employee_ids['eng_aisha']}/schedule",
        token=employee_token,
        query={"for_timestamp": datetime.now(UTC).isoformat()},
        expected={200},
    )

    holiday_lists = api.request(
        "GET",
        "holidays/lists",
        token=hr_token,
        # Holiday-list sorting is explicitly constrained by FastAPI to
        # ``name`` or ``id``.  Use a documented-valid field rather than
        # guessing derived fields such as ``year``.
        query={"page": 1, "page_size": 10, "sort_by": "name", "sort_order": "asc"},
        expected={200},
        label="Paginated holiday lists",
    )
    holiday_items = page_items(holiday_lists.body)
    holiday_list_id = int(holiday_items[0]["id"]) if holiday_items and holiday_items[0].get("id") is not None else 1
    api.request(
        "GET",
        f"holidays/lists/{holiday_list_id}",
        token=hr_token,
        expected={200, 404},
        label="Holiday-list detail",
    )

    aisha_records = [item for item in data["attendance"] if item["employee_key"] == "eng_aisha"]
    known_record = aisha_records[-1]
    latest_day = date.fromisoformat(known_record["attendance_date"])
    record_id = ctx.attendance_ids.get(known_record["erp_record_id"], 1)

    api.request(
        "GET",
        "attendance/",
        token=hr_token,
        query={
            "from_date": data["attendance_dates"][0].isoformat(),
            "to_date": latest_day.isoformat(),
            "status": "PRESENT",
            "page": 1,
            "page_size": 10,
            "sort_by": "attendance_date",
            "sort_order": "desc",
        },
        expected={200},
    )
    api.request("GET", f"attendance/records/{record_id}", token=hr_token, expected={200})
    api.request(
        "GET",
        f"attendance/employee/{ctx.employee_ids['eng_aisha']}/calendar",
        token=employee_token,
        query={"year": latest_day.year, "month": latest_day.month},
        expected={200},
    )
    api.request(
        "GET",
        f"attendance/employee/{ctx.employee_ids['eng_aisha']}/summary",
        token=employee_token,
        query={"year": latest_day.year, "month": latest_day.month},
        expected={200},
    )
    api.request(
        "GET",
        "attendance/checkins",
        token=hr_token,
        query={
            "page": 1,
            "page_size": 10,
            "employee_id": ctx.employee_ids["eng_aisha"],
            "sort_order": "desc",
        },
        expected={200},
        label="Raw check-in list (may legitimately be empty for ERP-processed demo data)",
    )

    # Browser punch writes are intentionally forbidden; exercise both documented negative APIs.
    punch_payload = {
        "employee_id": ctx.employee_ids["eng_aisha"],
        "punch_time": datetime.now(UTC).isoformat(),
        "punch_type": "IN",
        "device_id": "DEMO-BROWSER",
        "source": "WEB",
        "erp_event_id": f"DEMO-BROWSER-{data['short_suffix']}",
    }
    api.request(
        "POST",
        "attendance/checkins",
        punch_payload,
        token=employee_token,
        expected={403},
        label="Expected 403: browser check-in write is ERP-owned",
    )
    api.request(
        "POST",
        "attendance/checkins/bulk",
        {"punches": [punch_payload]},
        token=employee_token,
        expected={403},
        label="Expected 403: browser bulk check-in write is ERP-owned",
    )

    # HR attendance processing, scoped to the unit, on a single employee/date.
    process_day = next_weekday(data["today"], 1)
    api.request(
        "POST",
        "attendance/process",
        {
            "from_date": process_day.isoformat(),
            "to_date": process_day.isoformat(),
            "employee_id": ctx.employee_ids["security"],
            "unit_id": ctx.unit_ids["blr"],
        },
        token=hr_token,
        expected={200},
        label="HR attendance processing endpoint",
    )

    correction = api.request(
        "POST",
        "attendance/corrections",
        {
            "attendance_record_id": record_id,
            "requested_punch_out": "19:55",
            "reason": "Biometric device missed the final checkout during an approved late deployment.",
            "erp_correction_id": f"APS-{data['short_suffix']}-CORR-001",
        },
        token=hr_token,
        expected={201},
        label="Submit attendance correction for ERP reconciliation",
    )
    _ = correction
    api.request(
        "GET",
        "attendance/corrections",
        token=hr_token,
        query={"status": "PENDING_ERP_RECONCILIATION", "page": 1, "page_size": 10, "sort_order": "desc"},
        expected={200},
    )


def create_leave(
    api: ApiClient,
    ctx: DemoContext,
    *,
    actor: str,
    leave_type: str,
    from_date: date,
    to_date: date | None = None,
    reason: str,
) -> int:
    response = api.request(
        "POST",
        "leaves/",
        {
            "employee_id": ctx.employee_ids[actor],
            "leave_type_id": ctx.leave_type_ids[leave_type],
            "from_date": from_date.isoformat(),
            "to_date": (to_date or from_date).isoformat(),
            "half_day": False,
            "reason": reason,
        },
        token=bearer(ctx, actor),
        expected={201},
        label=f"Apply leave: {actor}",
    )
    return require_id(response.body, f"leave application {actor}")


def exercise_leave_workflows(api: ApiClient, ctx: DemoContext) -> dict[str, int]:
    data = ctx.data
    today = data["today"]
    manager_token = bearer(ctx, "eng_manager")

    print("\n" + "=" * 80)
    print("PHASE 4 — Leave workflows: approve, reject, cancel, cancellation decisions")
    print("=" * 80)

    # Master/read endpoints.
    api.request(
        "GET",
        "leaves/periods",
        token=manager_token,
        query={"page": 1, "page_size": 10, "sort_order": "asc"},
        expected={200},
    )
    api.request(
        "GET",
        "leaves/types",
        token=manager_token,
        query={"is_active": True, "page": 1, "page_size": 10, "sort_by": "name", "sort_order": "asc"},
        expected={200},
    )
    api.request(
        "GET",
        f"leaves/types/{ctx.leave_type_ids['casual']}",
        token=manager_token,
        expected={200},
    )
    api.request(
        "GET",
        f"leaves/balance/employee/{ctx.employee_ids['eng_aisha']}",
        token=bearer(ctx, "eng_aisha"),
        query={"for_date": today.isoformat()},
        expected={200},
    )

    # Use the same explicit holiday calendar seeded by this demo.  A plain
    # weekday helper is insufficient: e.g. from 2026-09-25 the fifth weekday
    # is 2026-10-02, which this demo seeds as Gandhi Jayanti.
    future1 = next_demo_working_day(data, today, 5)
    future2 = next_demo_working_day(data, today, 7)
    future3 = next_demo_working_day(data, today, 9)

    leave_ids: dict[str, int] = {}

    leave_ids["approve"] = create_leave(
        api,
        ctx,
        actor="eng_aisha",
        leave_type="casual",
        from_date=future1,
        reason="Family appointment planned in advance.",
    )
    api.request(
        "GET",
        f"leaves/{leave_ids['approve']}",
        token=bearer(ctx, "eng_aisha"),
        expected={200},
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['approve']}/approve",
        token=manager_token,
        expected={200},
        label="Manager approves Aisha leave",
    )

    leave_ids["reject"] = create_leave(
        api,
        ctx,
        actor="eng_karan",
        leave_type="casual",
        from_date=future2,
        reason="Personal engagement.",
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['reject']}/reject",
        {"rejection_reason": "Team release activity is scheduled; please choose another date."},
        token=manager_token,
        expected={200},
        label="Manager rejects Karan leave",
    )

    leave_ids["pending_cancel"] = create_leave(
        api,
        ctx,
        actor="eng_nikhil",
        leave_type="earned",
        from_date=future3,
        reason="Planned personal travel.",
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['pending_cancel']}/cancel",
        {"reason": "Travel plan changed."},
        token=bearer(ctx, "eng_nikhil"),
        expected={200},
        label="Employee cancels pending leave",
    )

    # Started-leave cancellation flow. Current-day leave is used because the
    # service turns an already-started approved leave into CANCELLATION_PENDING.
    # On environments that prohibit same-day cancellation transitions, the final
    # decision endpoints are still invoked and accept documented state errors.
    leave_ids["cancel_approve"] = create_leave(
        api,
        ctx,
        actor="security",
        leave_type="sick",
        from_date=today,
        reason="Medical appointment.",
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['cancel_approve']}/approve",
        token=manager_token,
        expected={200},
    )
    cancel_req = api.request(
        "PATCH",
        f"leaves/{leave_ids['cancel_approve']}/cancel",
        {"effective_date": today.isoformat(), "reason": "Returned to work earlier than expected."},
        token=bearer(ctx, "security"),
        expected={200, 400, 409},
        label="Request cancellation of started leave",
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['cancel_approve']}/cancellation/approve",
        token=manager_token,
        expected={200, 400, 409},
        label="Approve started-leave cancellation",
    )

    # Use another employee for the cancellation-rejection branch.
    leave_ids["cancel_reject"] = create_leave(
        api,
        ctx,
        actor="eng_nikhil",
        leave_type="sick",
        from_date=today,
        reason="Health recovery day.",
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['cancel_reject']}/approve",
        token=manager_token,
        expected={200},
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['cancel_reject']}/cancel",
        {"effective_date": today.isoformat(), "reason": "Requested an early return."},
        token=bearer(ctx, "eng_nikhil"),
        expected={200, 400, 409},
    )
    api.request(
        "PATCH",
        f"leaves/{leave_ids['cancel_reject']}/cancellation/reject",
        {"rejection_reason": "Original approved leave remains appropriate for the recorded absence."},
        token=manager_token,
        expected={200, 400, 409},
        label="Reject started-leave cancellation",
    )

    api.request(
        "GET",
        "leaves/",
        token=manager_token,
        query={
            "from_date": today.isoformat(),
            "to_date": future3.isoformat(),
            "page": 1,
            "page_size": 5,
            "sort_by": "applied_at",
            "sort_order": "desc",
        },
        expected={200},
        label="Paginated manager leave queue",
    )

    return leave_ids


def exercise_work_arrangements(api: ApiClient, ctx: DemoContext) -> dict[str, int]:
    data = ctx.data
    manager_token = bearer(ctx, "eng_manager")
    today = data["today"]

    print("\n" + "=" * 80)
    print("PHASE 5 — Work-arrangement workflows")
    print("=" * 80)

    requests: dict[str, int] = {}
    scenarios = [
        ("approve", "eng_aisha", next_demo_working_day(data, today, 12), "Home internet maintenance requires working remotely."),
        ("reject", "eng_karan", next_demo_working_day(data, today, 13), "Need a focused work-from-home day for documentation."),
        ("cancel", "eng_nikhil", next_demo_working_day(data, today, 14), "Planned remote work for a home appointment."),
    ]
    for key, actor, day, reason in scenarios:
        response = api.request(
            "POST",
            "work-arrangements/",
            {
                "employee_id": ctx.employee_ids[actor],
                "arrangement_type": "WORK_FROM_HOME",
                "from_date": day.isoformat(),
                "to_date": day.isoformat(),
                "reason": reason,
                "destination_location": "Home",
                "contact_phone": data["employee_map"][actor]["phone_number"],
            },
            token=bearer(ctx, actor),
            expected={201},
            label=f"Create WFH request: {actor}",
        )
        requests[key] = require_id(response.body, f"work arrangement {key}")

    api.request(
        "GET",
        f"work-arrangements/{requests['approve']}",
        token=bearer(ctx, "eng_aisha"),
        expected={200},
    )
    api.request(
        "PATCH",
        f"work-arrangements/{requests['approve']}/approve",
        token=manager_token,
        expected={200},
        label="Approve WFH request",
    )
    api.request(
        "PATCH",
        f"work-arrangements/{requests['reject']}/reject",
        {"rejection_reason": "In-person release workshop is scheduled for that day."},
        token=manager_token,
        expected={200},
        label="Reject WFH request",
    )
    api.request(
        "PATCH",
        f"work-arrangements/{requests['cancel']}/cancel",
        token=bearer(ctx, "eng_nikhil"),
        expected={200},
        label="Cancel pending WFH request",
    )
    api.request(
        "GET",
        "work-arrangements/",
        token=manager_token,
        query={"page": 1, "page_size": 5, "sort_by": "created_at", "sort_order": "desc"},
        expected={200},
        label="Paginated team WFH queue",
    )
    return requests


def resolve_overtime_ids(api: ApiClient, ctx: DemoContext) -> None:
    if len(ctx.overtime_ids) >= 2:
        return
    response = api.request(
        "GET",
        "overtime/",
        token=bearer(ctx, "org_hr"),
        query={"page": 1, "page_size": 100, "sort_by": "id", "sort_order": "asc"},
        expected={200},
        label="Resolve overtime IDs after ERP sync",
    )
    for item in page_items(response.body):
        event_id = item.get("erp_event_id")
        if event_id and item.get("id") is not None:
            ctx.overtime_ids[str(event_id)] = int(item["id"])


def exercise_overtime(api: ApiClient, ctx: DemoContext) -> None:
    data = ctx.data
    manager_token = bearer(ctx, "eng_manager")

    print("\n" + "=" * 80)
    print("PHASE 6 — Overtime reads and approval/rejection")
    print("=" * 80)

    resolve_overtime_ids(api, ctx)

    event_a = data["overtime"][0]["erp_event_id"]
    event_b = data["overtime"][1]["erp_event_id"]
    ot_a = ctx.overtime_ids.get(event_a)
    ot_b = ctx.overtime_ids.get(event_b)
    if ot_a is None or ot_b is None:
        if api.execute:
            raise DemoError("Could not resolve at least two overtime IDs for approval/rejection.")
        ot_a, ot_b = 1, 2

    api.request(
        "GET",
        "overtime/",
        token=manager_token,
        query={
            "employee_id": ctx.employee_ids["eng_aisha"],
            "page": 1,
            "page_size": 5,
            "sort_order": "desc",
        },
        expected={200},
    )
    api.request("GET", f"overtime/{ot_a}", token=manager_token, expected={200})
    latest_day = data["attendance_dates"][-1]
    api.request(
        "GET",
        f"overtime/employee/{ctx.employee_ids['eng_aisha']}/summary",
        token=bearer(ctx, "eng_aisha"),
        query={"month": latest_day.month, "year": latest_day.year},
        expected={200},
    )

    api.request(
        "PATCH",
        f"overtime/{ot_a}/approve",
        {"approved_minutes": 75, "remarks": "Approved after validating the production deployment window."},
        token=manager_token,
        expected={200},
        label="Approve overtime",
    )
    api.request(
        "PATCH",
        f"overtime/{ot_b}/reject",
        {"remarks": "Time was part of the planned flexible schedule and is not overtime."},
        token=manager_token,
        expected={200},
        label="Reject overtime",
    )


def exercise_reports_and_owner(api: ApiClient, ctx: DemoContext) -> None:
    data = ctx.data
    manager_token = bearer(ctx, "eng_manager")
    owner_token = bearer(ctx, "owner")
    month_day = data["attendance_dates"][-1]

    print("\n" + "=" * 80)
    print("PHASE 7 — Reports and executive analytics")
    print("=" * 80)

    api.request(
        "GET",
        "reports/attendance-matrix",
        token=manager_token,
        query={
            "year": month_day.year,
            "month": month_day.month,
            "page": 1,
            "page_size": 5,
            "department_id": ctx.department_ids["product_eng"],
            "sort_order": "asc",
        },
        expected={200},
        label="Department-scoped attendance matrix",
    )
    api.request(
        "GET",
        "reports/leave-summary",
        token=owner_token,
        query={"year": data["today"].year, "page": 1, "page_size": 5, "sort_order": "asc"},
        expected={200},
        label="Organization leave summary",
    )

    api.request(
        "GET",
        "dashboard/owner",
        token=owner_token,
        query={
            "from_date": data["attendance_dates"][0].isoformat(),
            "to_date": data["attendance_dates"][-1].isoformat(),
        },
        expected={200},
        label="Executive organization dashboard",
    )
    api.request(
        "GET",
        "dashboard/owner/exceptions",
        token=owner_token,
        query={
            "kind": "absent",
            "target_date": data["attendance_dates"][-1].isoformat(),
            "page": 1,
            "page_size": 10,
            "sort_order": "asc",
        },
        expected={200, 400},
        label="Executive absence exception drill-down",
    )


def exercise_notifications(api: ApiClient, ctx: DemoContext) -> None:
    print("\n" + "=" * 80)
    print("PHASE 8 — Notifications")
    print("=" * 80)

    token = bearer(ctx, "eng_aisha")
    response = api.request(
        "GET",
        "notifications",
        token=token,
        query={"page": 1, "page_size": 10, "unread": True, "sort_order": "desc"},
        expected={200},
    )
    api.request("GET", "notifications/unread-count", token=token, expected={200})

    items = page_items(response.body)
    notification_id = None
    for item in items:
        if item.get("notification_id") is not None:
            notification_id = int(item["notification_id"])
            break
        if item.get("id") is not None:
            notification_id = int(item["id"])
            break
    if notification_id is None:
        notification_id = 999_999_999

    api.request(
        "PATCH",
        f"notifications/{notification_id}/read",
        token=token,
        expected={200, 404},
        label="Mark one notification read",
    )
    api.request("POST", "notifications/mark-all-read", token=token, expected={200})


def exercise_leave_feed(api: ApiClient, ctx: DemoContext, *, acknowledge: bool) -> None:
    print("\n" + "=" * 80)
    print("PHASE 9 — ERP leave outcome feed")
    print("=" * 80)

    changes = api.request(
        "GET",
        "integrations/erp/leaves/changes",
        query={"limit": 100},
        api_key=True,
        expected={200},
    )
    items = []
    if isinstance(changes.body, dict) and isinstance(changes.body.get("items"), list):
        items = [item for item in changes.body["items"] if isinstance(item, dict)]
    event_ids = [str(item["event_id"]) for item in items if item.get("event_id")]

    if not event_ids:
        # Still exercise the acknowledgement contract without mutating real events.
        event_ids = [f"DEMO-NONEXISTENT-{ctx.data['short_suffix']}"]

    if acknowledge:
        api.request(
            "POST",
            "integrations/erp/leaves/changes/ack",
            event_ids,
            api_key=True,
            expected={200},
            label=f"Acknowledge {len(event_ids)} leave outcome event(s)",
        )
    else:
        # Coverage requirement: the API is still called. Unknown IDs are safe
        # because the contract returns them as unknown without affecting real rows.
        safe_ids = [f"DEMO-COVERAGE-{ctx.data['short_suffix']}"]
        api.request(
            "POST",
            "integrations/erp/leaves/changes/ack",
            safe_ids,
            api_key=True,
            expected={200},
            label="Exercise leave acknowledgement with a safe unknown event ID",
        )


def exercise_hr_password_reset(api: ApiClient, ctx: DemoContext) -> None:
    print("\n" + "=" * 80)
    print("PHASE 10 — HR account administration")
    print("=" * 80)
    api.request(
        "POST",
        f"auth/hr/employees/{ctx.employee_ids['password_target']}/password-reset",
        {"temporary_password": PASSWORD_TARGET_HR},
        token=bearer(ctx, "blr_hr"),
        expected={200},
        label="HR resets employee temporary password",
    )


def exercise_sessions_and_employee_mfa(api: ApiClient, ctx: DemoContext, initial_password: str) -> None:
    print("\n" + "=" * 80)
    print("PHASE 11 — Sessions, opt-in TOTP MFA, password recovery")
    print("=" * 80)


    # Fresh security-demo login.
    login = business_login(api, ctx, "security", initial_password)
    access = str(login.get("access_token") or "")
    refresh = str(login.get("refresh_token") or "")
    if not access or not refresh:
        if api.execute:
            raise DemoError("Security demo login did not return access + refresh tokens.")
        access = "dry-access"
        refresh = "dry-refresh"

    api.request("GET", "auth/session", token=access, expected={200})

    extra1 = api.request("POST", "auth/session", token=access, expected={201}, label="Create additional session")
    extra1_body = extra1.body if isinstance(extra1.body, dict) else {}
    extra1_refresh = str(extra1_body.get("refresh_token") or "dry-extra-refresh")
    api.request(
        "DELETE",
        "auth/session",
        {"refresh_token": extra1_refresh},
        expected={200},
        label="Revoke one browser session by refresh token",
    )

    extra2 = api.request("POST", "auth/session", token=access, expected={201}, label="Create second additional session")
    extra2_body = extra2.body if isinstance(extra2.body, dict) else {}
    extra2_id = int(extra2_body.get("session_id") or 1)

    api.request("GET", "auth/sessions", token=access, expected={200})
    api.request(
        "DELETE",
        f"auth/sessions/{extra2_id}",
        token=access,
        expected={200},
        label="Revoke one signed-in device by session ID",
    )

    refreshed = api.request(
        "POST",
        "auth/session/refresh",
        {"refresh_token": refresh},
        expected={200},
        label="Rotate refresh token",
    )
    if isinstance(refreshed.body, dict):
        access = str(refreshed.body.get("access_token") or access)
        refresh = str(refreshed.body.get("refresh_token") or refresh)

    api.request("GET", "auth/mfa/status", token=access, expected={200}, label="MFA status before opt-in")

    setup = api.request(
        "POST",
        "auth/mfa/reset",
        {"current_password": initial_password},
        token=access,
        expected={200},
        label="Generate pending authenticator secret from settings",
    )
    setup_body = setup.body if isinstance(setup.body, dict) else {}
    secret = str(setup_body.get("secret") or "JBSWY3DPEHPK3PXP")
    api.request(
        "POST",
        "auth/mfa/confirm",
        {"current_password": initial_password, "code": totp_now(secret)},
        token=access,
        expected={200},
        label="Confirm TOTP authenticator",
    )
    api.request("GET", "auth/mfa/status", token=access, expected={200}, label="MFA status after opt-in")

    recovery_response = api.request(
        "POST",
        "auth/mfa/recovery/regenerate",
        {"current_password": initial_password},
        token=access,
        expected={200},
        label="Regenerate recovery codes",
    )
    recovery_body = recovery_response.body if isinstance(recovery_response.body, dict) else {}
    recovery_codes = [str(code) for code in recovery_body.get("recovery_codes", []) if code]
    if len(recovery_codes) < 3:
        raise DemoError(
            "MFA recovery-code regeneration returned fewer than 3 codes; "
            "the demo needs three distinct single-use codes to avoid TOTP replay waits."
        )

    # A new login now requires MFA. Use a single-use recovery code so the
    # demo does not block waiting for another 30-second TOTP time-step.
    challenge = business_login(api, ctx, "security", initial_password)
    mfa_token = str(challenge.get("mfa_token") or "")
    if mfa_token:
        verified = api.request(
            "POST",
            "auth/mfa/verify",
            {"mfa_token": mfa_token, "code": recovery_codes.pop(0)},
            expected={200},
            label="Verify MFA login with a single-use recovery code",
        )
        if isinstance(verified.body, dict):
            access = str(verified.body.get("access_token") or access)
            refresh = str(verified.body.get("refresh_token") or refresh)
            ctx.tokens["security"] = dict(verified.body)
    else:
        # Dry-run and policy variants can already return a normal session. Call
        # verify with an invalid challenge so the operation is still covered.
        api.request(
            "POST",
            "auth/mfa/verify",
            {"mfa_token": "coverage-invalid-token", "code": "000000"},
            expected={400, 401},
            label="MFA verify state check",
        )

    # Password recovery authenticated with a distinct single-use recovery code.
    identity = ctx.data["employee_map"]["security"]["username"]
    recovery_start = api.request(
        "POST",
        "auth/password-recovery/start",
        {"identity": identity},
        expected={200},
        label="Start MFA-backed password recovery",
    )
    start_body = recovery_start.body if isinstance(recovery_start.body, dict) else {}
    recovery_token_value = str(start_body.get("recovery_token") or "dry-recovery-token")
    recovery_verify = api.request(
        "POST",
        "auth/password-recovery/verify",
        {"recovery_token": recovery_token_value, "code": recovery_codes.pop(0)},
        expected={200},
        label="Verify authenticator for password recovery",
    )
    verify_body = recovery_verify.body if isinstance(recovery_verify.body, dict) else {}
    reset_token = str(
        verify_body.get("reset_token")
        or verify_body.get("recovery_token")
        or "dry-reset-token"
    )
    api.request(
        "POST",
        "auth/password-recovery/reset",
        {"reset_token": reset_token, "new_password": PASSWORD_AFTER_RECOVERY},
        expected={200},
        label="Reset password after MFA recovery",
    )

    # Re-login after recovery and verify MFA again.
    challenge = business_login(api, ctx, "security", PASSWORD_AFTER_RECOVERY)
    mfa_token = str(challenge.get("mfa_token") or "")
    if mfa_token:
        verified = api.request(
            "POST",
            "auth/mfa/verify",
            {"mfa_token": mfa_token, "code": recovery_codes.pop(0)},
            expected={200},
            label="MFA login after recovered password using recovery code",
        )
        if isinstance(verified.body, dict):
            access = str(verified.body.get("access_token") or access)
            refresh = str(verified.body.get("refresh_token") or refresh)
            ctx.tokens["security"] = dict(verified.body)
    else:
        access = str(challenge.get("access_token") or access)
        refresh = str(challenge.get("refresh_token") or refresh)

    # Replacement secret flow while old authenticator remains valid until confirm.
    replacement = api.request(
        "POST",
        "auth/mfa/reset",
        {"current_password": PASSWORD_AFTER_RECOVERY},
        token=access,
        expected={200},
        label="Start authenticator replacement",
    )
    replacement_body = replacement.body if isinstance(replacement.body, dict) else {}
    replacement_secret = str(replacement_body.get("secret") or secret)
    api.request(
        "POST",
        "auth/mfa/confirm",
        {"current_password": PASSWORD_AFTER_RECOVERY, "code": totp_now(replacement_secret)},
        token=access,
        expected={200},
        label="Confirm replacement authenticator",
    )
    secret = replacement_secret

    api.request(
        "POST",
        "auth/mfa/disable",
        {"current_password": PASSWORD_AFTER_RECOVERY},
        token=access,
        expected={200},
        label="Disable optional MFA for the demo employee",
    )
    api.request("GET", "auth/mfa/status", token=access, expected={200}, label="MFA status after disable")

    # Change-password endpoint revokes all sessions, by design.
    api.request(
        "POST",
        "auth/change-password",
        {"current_password": PASSWORD_AFTER_RECOVERY, "new_password": PASSWORD_FINAL},
        token=access,
        expected={200},
        label="Change own password and revoke sessions",
    )

    # Re-login using the final known password and keep this token for final cleanup.
    final_login = business_login(api, ctx, "security", PASSWORD_FINAL)
    ctx.tokens["security"] = dict(final_login)


def exercise_superadmin(api: ApiClient, ctx: DemoContext) -> None:
    print("\n" + "=" * 80)
    print("PHASE 12 — Super Admin login, MFA enrollment/verification, technical metrics")
    print("=" * 80)

    username = os.environ.get("DEMO_SUPER_ADMIN_USERNAME", "superadmin")
    password = os.environ.get("DEMO_SUPER_ADMIN_PASSWORD", "SuperAdmin@123")

    login = api.request(
        "POST",
        "auth/super-admin/login",
        {"username": username, "password": password},
        form=True,
        expected={200},
        label="Super Admin login",
    )
    body = login.body if isinstance(login.body, dict) else {}
    access = str(body.get("access_token") or "")
    mfa_token = str(body.get("mfa_token") or "")

    if body.get("mfa_enrollment_required") and mfa_token:
        enrollment = api.request(
            "POST",
            "auth/mfa/enroll",
            {"mfa_token": mfa_token},
            expected={200},
            label="Super Admin first-time authenticator enrollment",
        )
        enrollment_body = enrollment.body if isinstance(enrollment.body, dict) else {}
        secret = str(enrollment_body.get("secret") or "")
        if not secret:
            raise DemoError("Super Admin MFA enrollment did not return a TOTP secret.")
        activated = api.request(
            "POST",
            "auth/mfa/activate",
            {"mfa_token": mfa_token, "code": totp_now(secret)},
            expected={200},
            label="Activate Super Admin authenticator and sign in",
        )
        body = activated.body if isinstance(activated.body, dict) else {}
        access = str(body.get("access_token") or "")
    elif body.get("mfa_required") and mfa_token:
        secret = os.environ.get("DEMO_SUPER_ADMIN_TOTP_SECRET", "")
        recovery_code = os.environ.get("DEMO_SUPER_ADMIN_RECOVERY_CODE", "")
        if api.execute and not secret and not recovery_code:
            raise DemoError(
                "Super Admin is already MFA-enrolled. Set DEMO_SUPER_ADMIN_TOTP_SECRET "
                "or DEMO_SUPER_ADMIN_RECOVERY_CODE for full coverage."
            )
        code = recovery_code or (totp_now(secret) if secret else "000000")
        verified = api.request(
            "POST",
            "auth/mfa/verify",
            {"mfa_token": mfa_token, "code": code},
            expected={200},
            label="Verify existing Super Admin MFA",
        )
        verified_body = verified.body if isinstance(verified.body, dict) else {}
        access = str(verified_body.get("access_token") or "")

        # First-time enrollment APIs are invalid once a factor exists, but they
        # are still intentionally exercised so operation coverage remains 100%.
        api.request(
            "POST",
            "auth/mfa/enroll",
            {"mfa_token": mfa_token},
            expected={400, 409},
            label="Expected state rejection: enroll when factor already exists",
        )
        api.request(
            "POST",
            "auth/mfa/activate",
            {"mfa_token": mfa_token, "code": code},
            expected={400, 401, 409},
            label="Expected state rejection: activate already-enrolled factor",
        )
    else:
        # MFA policy disabled: technical account already has a session. Exercise
        # the login-time enrollment endpoints with invalid challenge tokens.
        api.request(
            "POST",
            "auth/mfa/enroll",
            {"mfa_token": "coverage-invalid-superadmin-token"},
            expected={400, 401},
            label="MFA enrollment endpoint state check",
        )
        api.request(
            "POST",
            "auth/mfa/activate",
            {"mfa_token": "coverage-invalid-superadmin-token", "code": "000000"},
            expected={400, 401},
            label="MFA activation endpoint state check",
        )

    if not access:
        if api.execute:
            raise DemoError("Super Admin flow did not produce an access token.")
        access = "dry-superadmin-access"

    api.request("GET", "dashboard/technical-metrics", token=access, expected={200})

    # Change username and immediately restore it. This exercises the endpoint
    # without leaving the demo Super Admin renamed.
    temp_username = (username[:34] + ".demo." + ctx.data["short_suffix"].lower())[:50]
    api.request(
        "PATCH",
        "auth/super-admin/username",
        {"username": temp_username, "current_password": password},
        token=access,
        expected={200},
        label="Temporarily rename Super Admin",
    )
    api.request(
        "PATCH",
        "auth/super-admin/username",
        {"username": username, "current_password": password},
        token=access,
        expected={200},
        label="Restore Super Admin username",
    )


def final_session_cleanup(api: ApiClient, ctx: DemoContext) -> None:
    print("\n" + "=" * 80)
    print("PHASE 13 — Final session cleanup")
    print("=" * 80)

    token = bearer(ctx, "security")
    api.request(
        "DELETE",
        "auth/sessions",
        token=token,
        expected={200},
        label="Log security-demo account out everywhere",
    )


def exercise_public_health(api: ApiClient) -> None:
    print("\n" + "=" * 80)
    print("PHASE 0 — Public service endpoints")
    print("=" * 80)
    api.request("GET", "/", root=True, expected={200})
    api.request("GET", "/health", root=True, expected={200})
    api.request("GET", "/db-health", root=True, expected={200, 503})


def assert_api_coverage(api: ApiClient) -> None:
    missing, extra = api.coverage.report()
    print("\n" + "=" * 80)
    print("OPENAPI COVERAGE")
    print("=" * 80)
    print(f"Expected operations: {len(api.coverage.expected)}")
    print(f"Covered operations : {len(api.coverage.called)}")

    if extra:
        print("\nMatched operations not in expected set:")
        for method, path in extra:
            print(f"  {method:6} {path}")

    if missing:
        print("\nMISSING OPERATIONS:")
        for method, path in missing:
            print(f"  {method:6} {path}")
        raise DemoError(f"API coverage incomplete: {len(missing)} operation(s) were not called.")

    print("\n✓ Every OpenAPI operation was exercised at least once.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed realistic People HRMS demo data and exercise every OpenAPI operation."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send HTTP requests. Without this flag, print a dependency-aware dry run.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ERP_DEMO_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="HRMS API v1 base URL.",
    )
    parser.add_argument(
        "--ack-leave-changes",
        action="store_true",
        help="Acknowledge real leave outcome events after creating workflow data.",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("DEMO_RUN_ID") or datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
        help="Unique suffix used for codes/usernames. Defaults to the current UTC timestamp.",
    )
    return parser.parse_args()


def guard_environment(args: argparse.Namespace) -> None:
    if not args.execute:
        return

    parsed = urlparse(args.base_url)
    if parsed.hostname not in LOCAL_HOSTS and os.environ.get("DEMO_ALLOW_REMOTE") != "1":
        raise DemoError(
            f"Refusing to mutate non-local host {parsed.hostname!r}. "
            "Set DEMO_ALLOW_REMOTE=1 only for an explicitly disposable test environment."
        )
    has_hmac = bool(os.environ.get("ERP_API_CLIENT_ID") and os.environ.get("ERP_API_CLIENT_SECRET"))
    if not has_hmac and not os.environ.get("ERP_API_KEY"):
        raise DemoError(
            "Set ERP_API_CLIENT_ID and ERP_API_CLIENT_SECRET, or use ERP_API_KEY for a development server."
        )


def main() -> int:
    args = parse_args()
    try:
        guard_environment(args)

        initial_password = os.environ.get("ERP_DEMO_INITIAL_PASSWORD", DEFAULT_INITIAL_PASSWORD)
        data = build_demo_data(args.run_id)
        coverage = Coverage(set(OPENAPI_OPERATIONS_SNAPSHOT))
        api = ApiClient(
            args.base_url,
            erp_api_key=os.environ.get("ERP_API_KEY", ""),
            erp_client_id=os.environ.get("ERP_API_CLIENT_ID", ""),
            erp_client_secret=os.environ.get("ERP_API_CLIENT_SECRET", ""),
            execute=args.execute,
            coverage=coverage,
        )

        live_operations = load_live_openapi_operations(api)
        if live_operations:
            api.coverage = Coverage(live_operations)
            print(f"Loaded live OpenAPI contract with {len(live_operations)} operations.")
        else:
            print(f"Using attached OpenAPI snapshot with {len(OPENAPI_OPERATIONS_SNAPSHOT)} operations.")

        ctx = new_context(data)

        print("\nPeople HRMS full demo")
        print(f"Run ID: {data['run_id']}")
        print(f"Company: {data['organization']['name']}")
        print(f"Employees: {len(data['employees'])}")
        print(f"Attendance rows planned: {len(data['attendance'])}")
        print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

        exercise_public_health(api)
        seed_erp_data(api, ctx, initial_password)
        login_business_actors(api, ctx, initial_password)
        exercise_read_apis(api, ctx)
        leave_ids = exercise_leave_workflows(api, ctx)
        _ = leave_ids
        exercise_work_arrangements(api, ctx)
        exercise_overtime(api, ctx)
        exercise_reports_and_owner(api, ctx)
        exercise_notifications(api, ctx)
        exercise_leave_feed(api, ctx, acknowledge=args.ack_leave_changes)
        exercise_hr_password_reset(api, ctx)
        exercise_sessions_and_employee_mfa(api, ctx, initial_password)
        exercise_superadmin(api, ctx)
        final_session_cleanup(api, ctx)
        assert_api_coverage(api)

        print("\nDemo completed successfully.")
        print("Synthetic login password for ordinary seeded accounts:")
        print(f"  Initial: {initial_password}")
        print(f"  Security demo final password: {PASSWORD_FINAL}")
        print(f"  Password-target final temporary password: {PASSWORD_TARGET_HR}")
        return 0
    except DemoError as exc:
        print(f"\nDEMO FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
