"""Editable end-to-end ERP API workflow for manual HRMS testing.

This script deliberately uses HTTP rather than writing to PostgreSQL. Edit
``ERP_DATA`` below with real test values, start the API, preview the requests,
and then execute them:

    uv run python demo.py
    uv run python demo.py --execute

Environment variables:

    ERP_API_KEY                 required with --execute
    ERP_DEMO_BASE_URL           default http://127.0.0.1:8000/api/v1
    ERP_DEMO_INITIAL_PASSWORD   strong temporary employee password

The workflow is dependency ordered: organization -> units -> departments ->
designations -> shifts -> employees -> assignments -> holidays -> attendance
-> leave balances -> overtime -> leave outcome pull/ack. IDs returned by an
earlier endpoint are inserted into dependent requests automatically.

The create endpoints are not globally idempotent. Use unique codes, usernames,
emails, mobile numbers, ERP record IDs, and ERP event IDs for each real run.
Bulk endpoints can return HTTP 200 with failed rows, so this client treats a
non-empty ``failed`` collection as a failed run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Edit this section with the real data you want to insert manually.
# ``key`` values are local references used only inside this file.
# ---------------------------------------------------------------------------

ERP_DATA: dict[str, Any] = {
    "organization": {
        "name": "Manual ERP Test Company",
        "short_name": "METC",
        "industry": "Technology",
        "city": "Mumbai",
        "state": "Maharashtra",
        "country": "India",
        "email": "people@example.test",
    },
    "units": [
        {"key": "head_office", "name": "Head Office", "code": "ERP-MANUAL-HO", "city": "Mumbai"},
    ],
    "departments": [
        {"key": "engineering", "unit_key": "head_office", "name": "Engineering", "code": "ERP-MANUAL-ENG"},
    ],
    "designations": [
        {"key": "manager", "name": "Engineering Manager", "code": "ERP-MANUAL-MGR"},
        {"key": "engineer", "name": "Software Engineer", "code": "ERP-MANUAL-DEV"},
    ],
    "shifts": [
        {
            "key": "general",
            "unit_key": "head_office",
            "name": "General Shift",
            "code": "ERP-MANUAL-GEN",
            "start_time": "09:30:00",
            "end_time": "18:30:00",
            "grace_minutes": 10,
            "break_minutes": 30,
            "is_cross_midnight": False,
            "is_active": True,
        },
    ],
    # Put managers before employees who reference them through manager_key.
    "employees": [
        {
            "key": "manager",
            "employee_code": "ERP-MANUAL-MGR-001",
            "username": "erp.manual.manager",
            "official_email": "erp.manual.manager@example.test",
            "phone_number": "9876501001",
            "first_name": "Manual",
            "last_name": "Manager",
            "role": "DEPARTMENT_MANAGER",
            "business_role": "DEPARTMENT_MANAGER",
            "access_scope": "DEPARTMENT",
            "unit_key": "head_office",
            "department_key": "engineering",
            "designation_key": "manager",
            "shift_key": "general",
            "date_of_joining": "2026-01-01",
            "employment_type": "PERMANENT",
            "biometric_id": "ERP-BIO-MGR-001",
            "overtime_eligible": True,
        },
        {
            "key": "employee",
            "employee_code": "ERP-MANUAL-EMP-001",
            "username": "erp.manual.employee",
            "official_email": "erp.manual.employee@example.test",
            "phone_number": "9876501002",
            "first_name": "Manual",
            "last_name": "Employee",
            "role": "EMPLOYEE",
            "business_role": None,
            "access_scope": "SELF",
            "unit_key": "head_office",
            "department_key": "engineering",
            "designation_key": "engineer",
            "shift_key": "general",
            "manager_key": "manager",
            "date_of_joining": "2026-01-01",
            "employment_type": "PERMANENT",
            "biometric_id": "ERP-BIO-EMP-001",
            "overtime_eligible": True,
        },
    ],
    "holidays": [
        {
            "erp_holiday_id": "ERP-MANUAL-HOL-001",
            "name": "Manual Test Holiday",
            "holiday_date": "2026-10-02",
            "description": "Replace with the real ERP holiday",
            "is_active": True,
        },
    ],
    "attendance": [
        {
            "key": "manager_day",
            "employee_key": "manager",
            "shift_key": "general",
            "erp_record_id": "ERP-MANUAL-ATT-MGR-001",
            "attendance_date": "2026-09-23",
            "status": "PRESENT",
            "punch_in": "09:28:00",
            "punch_out": "18:35:00",
            "worked_minutes": 517,
            "overtime_minutes": 7,
            "late_minutes": 0,
            "early_exit_minutes": 0,
        },
        {
            "key": "employee_day",
            "employee_key": "employee",
            "shift_key": "general",
            "erp_record_id": "ERP-MANUAL-ATT-EMP-001",
            "attendance_date": "2026-09-23",
            "status": "PRESENT",
            "punch_in": "09:45:00",
            "punch_out": "19:30:00",
            "worked_minutes": 555,
            "overtime_minutes": 60,
            "late_minutes": 5,
            "early_exit_minutes": 0,
        },
    ],
    # leave_code must already exist in HRMS. The default seed normally creates CL.
    "leave_balances": [
        {
            "employee_key": "manager",
            "leave_code": "CL",
            "year": 2026,
            "allocated": 12,
            "used": 1,
            "pending": 0,
        },
        {
            "employee_key": "employee",
            "leave_code": "CL",
            "year": 2026,
            "allocated": 12,
            "used": 2,
            "pending": 0,
        },
    ],
    "overtime": [
        {
            "erp_event_id": "ERP-MANUAL-OT-001",
            "employee_key": "employee",
            "attendance_key": "employee_day",
            "overtime_start": "2026-09-23T18:30:00+05:30",
            "overtime_end": "2026-09-23T19:30:00+05:30",
            "calculated_minutes": 60,
            "approved_minutes": 0,
            "status": "PENDING",
        },
    ],
}


SENSITIVE_KEYS = {"initial_password", "new_password", "password", "x-api-key"}


class ErpApiError(RuntimeError):
    """One ERP request or partial-success row failed."""


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***" if key.lower() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class ErpClient:
    def __init__(self, base_url: str, api_key: str, *, execute: bool):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.execute = execute
        self._fake_id = 1000

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        query: dict[str, Any] | None = None,
    ) -> Any:
        query_string = f"?{urlencode(query)}" if query else ""
        url = f"{self.base_url}/{path.lstrip('/')}{query_string}"
        print(f"\n{method} {url}")
        if payload is not None:
            print(json.dumps(redact(payload), indent=2, default=str))
        if not self.execute:
            return self._dry_response(path, payload)

        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                result = json.loads(raw) if raw else None
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise ErpApiError(f"{method} {path} returned {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ErpApiError(f"Could not reach {url}: {exc.reason}") from exc

        if result is not None:
            print("Response:", json.dumps(result, indent=2, default=str))
        self._raise_for_partial_failure(path, result)
        return result

    def _next_id(self) -> int:
        self._fake_id += 1
        return self._fake_id

    def _dry_response(self, path: str, payload: Any) -> Any:
        if path.endswith("attendance/records"):
            return {
                "accepted": [
                    {"erp_record_id": item["erp_record_id"], "id": self._next_id()} for item in payload
                ],
                "duplicates": [],
                "failed": [],
            }
        if path.endswith("attendance/records/bulk"):
            return {
                "accepted": [
                    {"erp_record_id": item["erp_record_id"], "id": self._next_id()}
                    for item in payload["records"]
                ],
                "duplicates": [],
                "failed": [],
            }
        if path.endswith("/changes"):
            return {"items": [], "has_more": False}
        if path.endswith("/changes/ack"):
            return {"acknowledged": payload, "unknown": []}
        if path.endswith("assignments/bulk"):
            return []
        if path.endswith("holidays/bulk"):
            return {"accepted": [item["erp_holiday_id"] for item in payload], "failed": []}
        if path.endswith(("balances", "balances/bulk")):
            return {"accepted": payload, "failed": []}
        if path.endswith("overtime/records/bulk"):
            return {
                "accepted": [
                    {"erp_event_id": item["erp_event_id"], "id": self._next_id()} for item in payload
                ],
                "duplicates": [],
                "failed": [],
            }
        return {"id": self._next_id()}

    @staticmethod
    def _raise_for_partial_failure(path: str, result: Any) -> None:
        if isinstance(result, dict) and result.get("failed"):
            raise ErpApiError(f"{path} returned failed rows: {json.dumps(result['failed'], default=str)}")


def without_keys(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in keys and value is not None}


def require_id(result: Any, label: str) -> int:
    if not isinstance(result, dict) or not isinstance(result.get("id"), int):
        raise ErpApiError(f"{label} did not return an integer id")
    return result["id"]


def attendance_ids(result: Any) -> dict[str, int]:
    items = [] if not isinstance(result, dict) else [*result.get("accepted", []), *result.get("duplicates", [])]
    return {
        str(item["erp_record_id"]): int(item["id"])
        for item in items
        if item.get("erp_record_id") and item.get("id") is not None
    }


def run_leave_feed(client: ErpClient, *, acknowledge: bool) -> None:
    changes = client.request("GET", "integrations/erp/leaves/changes", query={"limit": 100})
    events = changes.get("items", []) if isinstance(changes, dict) else []
    print(f"\nLeave outcome events available for ERP: {len(events)}")
    event_ids = [item["event_id"] for item in events if item.get("event_id")]
    if acknowledge and event_ids:
        client.request("POST", "integrations/erp/leaves/changes/ack", event_ids)
    elif event_ids:
        print("Events were not acknowledged. Re-run with --ack-leave-changes after verifying them.")


def run_workflow(client: ErpClient, *, acknowledge: bool, exercise_lifecycle: bool) -> None:
    data = deepcopy(ERP_DATA)
    # Deliberately unrelated to the sample employees' names, email addresses,
    # and usernames so it passes the same personal-information checks as every
    # other temporary password. Override this for real manual testing.
    initial_password = os.environ.get("ERP_DEMO_INITIAL_PASSWORD", "Cobalt!Harbor92#")

    print("\n[1/11] Organization")
    client.request("PATCH", "integrations/erp/organization", data["organization"])

    print("\n[2/11] Units")
    unit_ids: dict[str, int] = {}
    for item in data["units"]:
        result = client.request("POST", "integrations/erp/units", without_keys(item, "key"))
        unit_ids[item["key"]] = require_id(result, f"unit {item['key']}")

    print("\n[3/11] Departments")
    department_ids: dict[str, int] = {}
    for item in data["departments"]:
        payload = without_keys(item, "key", "unit_key") | {"unit_id": unit_ids[item["unit_key"]]}
        result = client.request("POST", "integrations/erp/departments", payload)
        department_ids[item["key"]] = require_id(result, f"department {item['key']}")

    print("\n[4/11] Designations")
    designation_ids: dict[str, int] = {}
    for item in data["designations"]:
        result = client.request("POST", "integrations/erp/designations", without_keys(item, "key"))
        designation_ids[item["key"]] = require_id(result, f"designation {item['key']}")

    print("\n[5/11] Shift definitions")
    shift_ids: dict[str, int] = {}
    for item in data["shifts"]:
        payload = without_keys(item, "key", "unit_key") | {"unit_id": unit_ids[item["unit_key"]]}
        result = client.request("POST", "integrations/erp/shifts", payload)
        shift_ids[item["key"]] = require_id(result, f"shift {item['key']}")

    print("\n[6/11] Employees and linked login accounts")
    employee_ids: dict[str, int] = {}
    for item in data["employees"]:
        payload = without_keys(
            item,
            "key",
            "unit_key",
            "department_key",
            "designation_key",
            "shift_key",
            "manager_key",
        )
        payload.update(
            {
                "unit_id": unit_ids[item["unit_key"]],
                "department_id": department_ids[item["department_key"]],
                "designation_id": designation_ids[item["designation_key"]],
                "shift_id": shift_ids[item["shift_key"]],
                "reporting_manager_id": employee_ids.get(item.get("manager_key")),
                "access_scope_id": (
                    department_ids[item["department_key"]]
                    if item.get("access_scope") == "DEPARTMENT"
                    else unit_ids[item["unit_key"]]
                    if item.get("access_scope") == "UNIT"
                    else None
                ),
                "initial_password": initial_password,
                "create_user_account": True,
            }
        )
        result = client.request("POST", "integrations/erp/employees", payload)
        employee_ids[item["key"]] = require_id(result, f"employee {item['key']}")

    print("\n[7/11] Shift assignments")
    employee_items = data["employees"]
    first = employee_items[0]
    client.request(
        "POST",
        "integrations/erp/shifts/assignments",
        {
            "employee_id": employee_ids[first["key"]],
            "shift_id": shift_ids[first["shift_key"]],
            "effective_from": first["date_of_joining"],
        },
    )
    for shift_key in {item["shift_key"] for item in employee_items[1:]}:
        selected = [item for item in employee_items[1:] if item["shift_key"] == shift_key]
        client.request(
            "POST",
            "integrations/erp/shifts/assignments/bulk",
            {
                "shift_id": shift_ids[shift_key],
                "effective_from": min(item["date_of_joining"] for item in selected),
                "employee_ids": [employee_ids[item["key"]] for item in selected],
            },
        )

    print("\n[8/11] Organization holidays")
    client.request("POST", "integrations/erp/holidays/bulk", data["holidays"])

    print("\n[9/11] Processed attendance")
    attendance_records = []
    for item in data["attendance"]:
        attendance_records.append(
            without_keys(item, "key", "employee_key", "shift_key")
            | {
                "employee_id": employee_ids[item["employee_key"]],
                "employee_code": next(
                    employee["employee_code"]
                    for employee in employee_items
                    if employee["key"] == item["employee_key"]
                ),
                "shift_id": shift_ids[item["shift_key"]],
            }
        )
    record_ids: dict[str, int] = {}
    if attendance_records:
        record_ids.update(
            attendance_ids(client.request("POST", "integrations/erp/attendance/records", [attendance_records[0]]))
        )
    if len(attendance_records) > 1:
        record_ids.update(
            attendance_ids(
                client.request(
                    "POST",
                    "integrations/erp/attendance/records/bulk",
                    {"records": attendance_records[1:]},
                )
            )
        )

    print("\n[10/11] Leave balances")
    balances = [
        without_keys(item, "employee_key") | {"employee_id": employee_ids[item["employee_key"]]}
        for item in data["leave_balances"]
    ]
    if balances:
        client.request("POST", "integrations/erp/leaves/balances", [balances[0]])
    if len(balances) > 1:
        client.request("POST", "integrations/erp/leaves/balances/bulk", balances[1:])

    print("\n[11/11] Overtime records and leave outcome feed")
    overtime_payload = []
    attendance_by_key = {item["key"]: item for item in data["attendance"]}
    for item in data["overtime"]:
        attendance = attendance_by_key[item["attendance_key"]]
        record_id = record_ids.get(attendance["erp_record_id"])
        if record_id is None:
            raise ErpApiError(
                f"No attendance id returned for {attendance['erp_record_id']}; overtime cannot be linked"
            )
        overtime_payload.append(
            without_keys(item, "employee_key", "attendance_key")
            | {
                "employee_id": employee_ids[item["employee_key"]],
                "attendance_record_id": record_id,
            }
        )
    if overtime_payload:
        client.request("POST", "integrations/erp/overtime/records/bulk", overtime_payload)

    if exercise_lifecycle:
        employee_id = employee_ids[employee_items[-1]["key"]]
        client.request(
            "PATCH",
            f"integrations/erp/employees/{employee_id}",
            {"employment_type": employee_items[-1]["employment_type"]},
        )
        client.request(
            "PATCH",
            f"integrations/erp/employees/{employee_id}/deactivate",
            {"exit_date": datetime.now(UTC).date().isoformat(), "exit_reason": "ERP lifecycle API test"},
        )
        client.request("PATCH", f"integrations/erp/employees/{employee_id}/activate")

    run_leave_feed(client, acknowledge=acknowledge)
    print("\nERP workflow completed successfully." if client.execute else "\nDry run completed. Add --execute to send it.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or execute the ordered ERP-to-HRMS API workflow.")
    parser.add_argument("--execute", action="store_true", help="Send requests. Without this flag, only print them.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ERP_DEMO_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="HRMS API v1 base URL.",
    )
    parser.add_argument(
        "--leave-feed-only",
        action="store_true",
        help="Only pull HRMS leave outcomes. Useful after manually approving/rejecting leave.",
    )
    parser.add_argument(
        "--ack-leave-changes",
        action="store_true",
        help="Acknowledge leave events after pulling them. Omit while inspecting real data.",
    )
    parser.add_argument(
        "--exercise-lifecycle",
        action="store_true",
        help="After provisioning, test employee update, deactivate, and activate, leaving the employee active.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("ERP_API_KEY", "")
    if args.execute and not api_key:
        print("ERP_API_KEY is required with --execute.", file=sys.stderr)
        return 2
    client = ErpClient(args.base_url, api_key, execute=args.execute)
    try:
        if args.leave_feed_only:
            run_leave_feed(client, acknowledge=args.ack_leave_changes)
        else:
            run_workflow(
                client,
                acknowledge=args.ack_leave_changes,
                exercise_lifecycle=args.exercise_lifecycle,
            )
    except ErpApiError as exc:
        print(f"\nERP workflow failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
