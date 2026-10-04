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
from schemas.employees import EmployeeUpsert
from schemas.org import DepartmentUpsert, OrganizationCreate, UnitUpdate
from schemas.shifts import ShiftUpsert
from services.designation_service import DesignationService
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
