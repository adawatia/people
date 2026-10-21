"""Regression coverage for the ERP bulk upsert endpoints.

Both suites call the route handlers directly with a real session, matching
``test_erp_upserts.py``. They require a PostgreSQL test database
(``DATABASE_URL`` ending in ``_test``).

The bulk response contract is the shared envelope: one correlation id, summary
counts, and one item per ERP identity carrying its own status, code and
retryability.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from core.database import async_session_maker
from core.erp_auth import ErpPrincipal
from routers.erp_employees import upsert_employees_bulk
from routers.erp_master_data import upsert_designations_bulk, upsert_units_bulk
from schemas.employees import EmployeeBulkUpsert, EmployeeBulkUpsertItem
from schemas.erp_bulk import (
    ErpDesignationBulkUpsert,
    ErpDesignationUpsertItem,
    ErpUnitBulkUpsert,
    ErpUnitUpsertItem,
)
from schemas.org import OrganizationCreate
from services.employee_service import EmployeeService
from services.org_service import OrgService

STRONG_PASSWORD = "Str0ng-Passw0rd!2026#X"
PRINCIPAL = ErpPrincipal(client_id="test-client", scopes=frozenset({"*"}))


def unique_mobile(seed: str) -> str:
    """A 10-digit Indian mobile number that is unique per test run."""
    return f"9{int(seed, 16) % 10**9:09d}"


def fake_user_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.password_helper.hash = lambda value: f"hashed::{value}"
    return manager


def accepted(result):
    return [item for item in result.items if item.status == "accepted"]


def failed(result):
    return [item for item in result.items if item.status == "failed"]


@pytest.mark.asyncio
async def test_bulk_employee_upsert_isolates_failures_and_is_idempotent():
    suffix = uuid.uuid4().hex[:12]
    first_id = f"bulk-{suffix}-a"
    bad_id = f"bulk-{suffix}-bad"
    payload = EmployeeBulkUpsert(
        employees=[
            EmployeeBulkUpsertItem(
                erp_id=first_id,
                employee_code=f"BA{suffix}",
                first_name="Bulk",
                last_name="Alpha",
                phone_number=unique_mobile(suffix),
                official_email=f"bulk.{suffix}@example.com",
                initial_password=STRONG_PASSWORD,
            ),
            # A new employee without phone_number / initial_password cannot be provisioned.
            EmployeeBulkUpsertItem(erp_id=bad_id, employee_code=f"BC{suffix}", first_name="Bulk"),
        ]
    )
    manager = fake_user_manager()

    async with async_session_maker() as session:
        result = await upsert_employees_bulk(
            Response(), payload, batch_id=f"test-{suffix}", principal=PRINCIPAL,
            user_manager=manager, session=session,
        )

        assert result.received_count == 2
        assert result.accepted_count == 1 and result.failed_count == 1
        assert [item.key for item in accepted(result)] == [first_id]
        assert [item.key for item in failed(result)] == [bad_id]
        assert "phone_number" in failed(result)[0].message
        assert failed(result)[0].code == "VALIDATION_ERROR"
        assert failed(result)[0].retryable is False
        created_id = accepted(result)[0].id

        # A retry of the same page updates the same employee instead of duplicating it.
        retry = await upsert_employees_bulk(
            Response(), payload, batch_id=f"test-{suffix}-retry", principal=PRINCIPAL,
            user_manager=manager, session=session,
        )
        assert [item.id for item in accepted(retry)] == [created_id]

        # Partial updates through the bulk endpoint keep the same identity.
        partial = EmployeeBulkUpsert(employees=[EmployeeBulkUpsertItem(erp_id=first_id, last_name="Renamed")])
        updated = await upsert_employees_bulk(
            Response(), partial, batch_id=f"test-{suffix}-partial", principal=PRINCIPAL,
            user_manager=manager, session=session,
        )
        assert [item.id for item in accepted(updated)] == [created_id]

        employee = await EmployeeService(session).get_employee(created_id)
        assert employee.last_name == "Renamed"


@pytest.mark.asyncio
async def test_bulk_master_data_reports_per_item_outcomes():
    suffix = uuid.uuid4().hex[:12]
    unit_id = f"bulk-unit-{suffix}"
    designation_id = f"bulk-designation-{suffix}"

    async with async_session_maker() as session:
        await OrgService(session).upsert_organization(
            f"bulk-org-{suffix}", OrganizationCreate(name=f"Bulk Org {suffix}")
        )

        units = await upsert_units_bulk(
            Response(),
            ErpUnitBulkUpsert(
                units=[
                    ErpUnitUpsertItem(erp_id=unit_id, name=f"Bulk Unit {suffix}", code=f"BU{suffix}"),
                    # No name: a unit cannot be created from an incomplete payload.
                    ErpUnitUpsertItem(erp_id=f"{unit_id}-bad"),
                ]
            ),
            batch_id=f"units-{suffix}",
            principal=PRINCIPAL,
            session=session,
        )
        assert units.batch_id == f"units-{suffix}"
        assert units.received_count == 2
        assert [item.key for item in accepted(units)] == [unit_id]
        assert [item.key for item in failed(units)] == [f"{unit_id}-bad"]
        assert failed(units)[0].code == "VALIDATION_ERROR"

        retried = await upsert_units_bulk(
            Response(),
            ErpUnitBulkUpsert(units=[ErpUnitUpsertItem(erp_id=unit_id, city="Pune")]),
            batch_id=f"units-{suffix}-retry",
            principal=PRINCIPAL,
            session=session,
        )
        assert [item.id for item in accepted(retried)] == [item.id for item in accepted(units)]

        designations = await upsert_designations_bulk(
            Response(),
            ErpDesignationBulkUpsert(
                designations=[
                    ErpDesignationUpsertItem(erp_id=designation_id, name=f"Bulk Role {suffix}", code=f"BR{suffix}"),
                    ErpDesignationUpsertItem(erp_id=f"{designation_id}-bad"),
                ]
            ),
            batch_id=f"designations-{suffix}",
            principal=PRINCIPAL,
            session=session,
        )
        assert [item.key for item in accepted(designations)] == [designation_id]
        assert [item.key for item in failed(designations)] == [f"{designation_id}-bad"]
