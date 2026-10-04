"""Regression coverage for the consolidated ERP write contract."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.database import async_session_maker
from db.models import AuthSession, User, now_ist
from routers.erp_employees import upsert_employee_from_erp
from schemas.designations import DesignationUpdate
from schemas.employees import EmployeeCreate, EmployeeUpsert
from schemas.org import DepartmentUpsert, OrganizationCreate, UnitUpdate
from schemas.shifts import ShiftAssignmentCreate, ShiftUpsert
from services.designation_service import DesignationService
from services.employee_service import EmployeeService
from services.org_service import OrgService
from services.shift_service import ShiftService


@pytest.mark.asyncio
async def test_erp_master_upserts_preserve_omitted_fields_and_support_retirement():
    suffix = uuid.uuid4().hex[:8]
    async with async_session_maker() as session:
        org_service = OrgService(session)
        await org_service.upsert_organization(f"org-{suffix}", OrganizationCreate(name=f"ERP Org {suffix}"))

        unit_id = f"unit-{suffix}"
        with pytest.raises(HTTPException) as missing_unit:
            await org_service.upsert_unit(unit_id, UnitUpdate(city="Pune"))
        assert missing_unit.value.status_code == 422
        unit = await org_service.upsert_unit(unit_id, UnitUpdate(name=f"Unit {suffix}", city="Mumbai"))
        unit = await org_service.upsert_unit(unit_id, UnitUpdate(city="Pune"))
        assert unit.name == f"Unit {suffix}" and unit.city == "Pune"
        unit = await org_service.upsert_unit(unit_id, UnitUpdate(is_active=False))
        assert unit.is_active is False
        unit = await org_service.upsert_unit(unit_id, UnitUpdate(is_active=True))
        assert unit.is_active is True

        department_id = f"dept-{suffix}"
        with pytest.raises(HTTPException) as missing_department:
            await org_service.upsert_department(department_id, DepartmentUpsert(name="Incomplete"))
        assert missing_department.value.status_code == 422
        department = await org_service.upsert_department(
            department_id, DepartmentUpsert(name=f"Dept {suffix}", unit_id=unit.id, code=f"D{suffix}")
        )
        department = await org_service.upsert_department(department_id, DepartmentUpsert(is_active=False))
        assert department.name == f"Dept {suffix}" and department.code == f"D{suffix}"
        assert department.is_active is False

        designation_service = DesignationService(session)
        with pytest.raises(HTTPException) as missing_designation:
            await designation_service.upsert_designation(f"desig-{suffix}", DesignationUpdate(code=f"X{suffix}"))
        assert missing_designation.value.status_code == 422
        designation = await designation_service.upsert_designation(
            f"desig-{suffix}", DesignationUpdate(name=f"Role {suffix}", code=f"R{suffix}")
        )
        designation = await designation_service.upsert_designation(
            f"desig-{suffix}", DesignationUpdate(is_active=False)
        )
        assert designation.id and designation.name == f"Role {suffix}" and designation.is_active is False

        shift_service = ShiftService(session)
        with pytest.raises(HTTPException) as missing_shift:
            await shift_service.upsert_shift(f"shift-{suffix}", ShiftUpsert(name="Incomplete"))
        assert missing_shift.value.status_code == 422
        shift = await shift_service.upsert_shift(
            f"shift-{suffix}", ShiftUpsert(name=f"Shift {suffix}", start_time="09:00", end_time="18:00")
        )
        shifted = await shift_service.upsert_shift(f"shift-{suffix}", ShiftUpsert(start_time="22:00"))
        assert shifted.id == shift.id and shifted.name == f"Shift {suffix}"
        assert shifted.is_cross_midnight is True


@pytest.mark.asyncio
async def test_employee_upsert_preserves_password_and_reconciles_login_status():
    suffix = uuid.uuid4().hex[:8]
    manager = SimpleNamespace(
        validate_password=AsyncMock(), password_helper=SimpleNamespace(hash=lambda _: "saved-hash")
    )
    async with async_session_maker() as session:
        erp_id = f"employee-{suffix}"
        with pytest.raises(HTTPException) as incomplete:
            await upsert_employee_from_erp(erp_id, EmployeeUpsert(first_name="A"), manager, session)
        assert incomplete.value.status_code == 422

        employee = await upsert_employee_from_erp(
            erp_id,
            EmployeeUpsert(
                employee_code=f"E{suffix}",
                first_name="First",
                phone_number=f"9{int(suffix, 16) % 1_000_000_000:09d}",
                initial_password="StrongPassword@123",
            ),
            manager,
            session,
        )
        row = await session.get(User, employee.user_id)
        assert row is not None and row.hashed_password == "saved-hash" and row.is_active
        auth_session = AuthSession(
            user_id=row.id,
            token_hash=uuid.uuid4().hex,
            expires_at=now_ist() + timedelta(days=1),
            absolute_expires_at=now_ist() + timedelta(days=1),
        )
        session.add(auth_session)
        await session.flush()
        auth_session_id = auth_session.id
        await session.commit()

        updated = await upsert_employee_from_erp(
            erp_id, EmployeeUpsert(first_name="Updated", initial_password="IgnoredPassword@123"), manager, session
        )
        assert updated.id == employee.id and updated.first_name == "Updated"
        manager.validate_password.assert_awaited_once()
        row = await session.get(User, employee.user_id)
        assert row.hashed_password == "saved-hash" and row.first_name == "Updated"

        await upsert_employee_from_erp(erp_id, EmployeeUpsert(status="INACTIVE"), manager, session)
        await session.refresh(row)
        assert row.is_active is False
        sessions = await session.get(AuthSession, auth_session_id)
        assert sessions is not None and sessions.revoked_at is not None

        await upsert_employee_from_erp(erp_id, EmployeeUpsert(status="ACTIVE"), manager, session)
        await session.refresh(row)
        assert row.is_active is True and row.hashed_password == "saved-hash"


@pytest.mark.asyncio
async def test_inactive_org_parents_block_new_assignments_without_cascading_child_flags():
    suffix = uuid.uuid4().hex[:8]
    async with async_session_maker() as session:
        org_service = OrgService(session)
        await org_service.upsert_organization(f"org-parent-{suffix}", OrganizationCreate(name=f"Parent Org {suffix}"))
        unit = await org_service.upsert_unit(
            f"unit-parent-{suffix}", UnitUpdate(name=f"Parent Unit {suffix}", code=f"U{suffix}")
        )
        department = await org_service.upsert_department(
            f"dept-parent-{suffix}", DepartmentUpsert(name=f"Parent Dept {suffix}", unit_id=unit.id)
        )
        employee = await EmployeeService(session).create_employee(
            EmployeeCreate(
                employee_code=f"E{suffix}",
                first_name="Test",
                unit_id=unit.id,
                department_id=department.id,
            )
        )
        shift_service = ShiftService(session)
        shift = await shift_service.upsert_shift(
            f"shift-parent-{suffix}",
            ShiftUpsert(name=f"Parent Shift {suffix}", start_time="09:00", end_time="18:00", unit_id=unit.id),
        )
        inactive_designation = await DesignationService(session).upsert_designation(
            f"designation-parent-{suffix}",
            DesignationUpdate(name=f"Parent Role {suffix}", code=f"R{suffix}", is_active=False),
        )
        with pytest.raises(HTTPException) as inactive_designation_assignment:
            await EmployeeService(session).create_employee(
                EmployeeCreate(employee_code=f"ED{suffix}", first_name="Test", designation_id=inactive_designation.id)
            )
        assert inactive_designation_assignment.value.status_code == 409

        retired_unit = await org_service.upsert_unit(f"unit-parent-{suffix}", UnitUpdate(is_active=False))
        assert retired_unit.is_active is False
        assert retired_unit.departments[0].is_active is True
        listed_department = (await org_service.list_departments(unit.id))[0]
        assert listed_department.is_active is True and listed_department.unit_is_active is False
        with pytest.raises(HTTPException) as inactive_department:
            await org_service.upsert_department(
                f"dept-new-{suffix}", DepartmentUpsert(name=f"New Dept {suffix}", unit_id=unit.id)
            )
        assert inactive_department.value.status_code == 409
        with pytest.raises(HTTPException) as employee_assignment:
            await EmployeeService(session).create_employee(
                EmployeeCreate(
                    employee_code=f"EU{suffix}",
                    first_name="Test",
                    unit_id=unit.id,
                    department_id=department.id,
                )
            )
        assert employee_assignment.value.status_code == 409
        with pytest.raises(HTTPException) as department_reactivation:
            await org_service.upsert_department(f"dept-parent-{suffix}", DepartmentUpsert(is_active=True))
        assert department_reactivation.value.status_code == 409
        with pytest.raises(HTTPException) as shift_reactivation:
            await shift_service.upsert_shift(f"shift-parent-{suffix}", ShiftUpsert(is_active=True))
        assert shift_reactivation.value.status_code == 409
        with pytest.raises(HTTPException) as shift_assignment:
            await shift_service.assign_shift(
                ShiftAssignmentCreate(employee_id=employee.id, shift_id=shift.id, effective_from=now_ist().date())
            )
        assert shift_assignment.value.status_code == 409

        await org_service.upsert_unit(f"unit-parent-{suffix}", UnitUpdate(is_active=True))
        reactivated_department = await org_service.upsert_department(
            f"dept-parent-{suffix}", DepartmentUpsert(is_active=True)
        )
        assert reactivated_department.is_active is True
        assignment = await shift_service.assign_shift(
            ShiftAssignmentCreate(employee_id=employee.id, shift_id=shift.id, effective_from=now_ist().date())
        )
        assert assignment.status == "ACTIVE"
