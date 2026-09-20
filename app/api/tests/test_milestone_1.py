import asyncio
import selectors
import sys
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from core.database import async_session_maker
from db.models import Department, Designation, Employee, EmployeeWorkHistory, Organization, Unit
from schemas.designations import DesignationCreate, DesignationUpdate
from schemas.employees import EmployeeCreate, EmployeeUpdate
from services.designation_service import DesignationService
from services.employee_service import EmployeeService


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:6]


def test_designation_service_crud(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            service = DesignationService(session)

            # 1. Create
            create_data = DesignationCreate(
                name=f"Software Engineer {unique_suffix}",
                code=f"SE_{unique_suffix}",
                description="Core platform engineering",
            )
            created = await service.create_designation(create_data)
            assert created.id is not None
            assert created.name == f"Software Engineer {unique_suffix}"

            # 2. Duplicate name validation
            with pytest.raises(HTTPException) as exc_info:
                await service.create_designation(create_data)
            assert exc_info.value.status_code == 400

            # 3. Get by ID
            fetched = await service.get_designation(created.id)
            assert fetched.id == created.id

            # 4. Update
            updated = await service.update_designation(
                created.id,
                DesignationUpdate(description="Senior platform engineering"),
            )
            assert updated.description == "Senior platform engineering"

            # 5. List
            all_desigs = await service.list_designations()
            assert any(d.id == created.id for d in all_desigs)

    run_async(_test())


def test_employee_profile_and_hierarchy(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            emp_service = EmployeeService(session)
            desig_service = DesignationService(session)

            # Create test org, unit, department
            org = Organization(name=f"Test Org {unique_suffix}", short_name="TO")
            session.add(org)
            await session.flush()

            unit = Unit(organization_id=org.id, name=f"Unit 1 {unique_suffix}", code=f"U1_{unique_suffix}")
            session.add(unit)
            await session.flush()

            dept1 = Department(unit_id=unit.id, name=f"Manufacturing {unique_suffix}", code=f"MFG_{unique_suffix}")
            dept2 = Department(unit_id=unit.id, name=f"Quality Assurance {unique_suffix}", code=f"QA_{unique_suffix}")
            session.add_all([dept1, dept2])
            await session.flush()

            desig = await desig_service.create_designation(
                DesignationCreate(name=f"Plant Operator {unique_suffix}", code=f"PO_{unique_suffix}")
            )

            # 1. Create manager employee
            mgr_data = EmployeeCreate(
                employee_code=f"EMP_MGR_{unique_suffix}",
                first_name="Jane",
                last_name="Manager",
                official_email=f"jane.manager.{unique_suffix}@example.com",
                phone_number="+919876500001",
                department_id=dept1.id,
                unit_id=unit.id,
                designation_id=desig.id,
                date_of_joining=date(2024, 1, 15),
                emergency_contact_name="Bob Manager",
                emergency_contact_phone="+919876500002",
                emergency_contact_relation="Spouse",
                current_address="123 Plant Road, Pune",
                pan_number="ABCDE1234F",
            )
            mgr_read = await emp_service.create_employee(mgr_data)
            assert mgr_read.id is not None
            assert mgr_read.full_name == "Jane Manager"
            assert mgr_read.department_name == dept1.name
            assert mgr_read.unit_name == unit.name
            assert mgr_read.designation_name == desig.name

            # Verify initial work history was logged
            mgr_history = await emp_service.get_work_history(mgr_read.id)
            assert len(mgr_history) == 1
            assert mgr_history[0].remarks == "Initial Appointment"

            # 2. Create staff reporting to manager
            staff_data = EmployeeCreate(
                employee_code=f"EMP_STF_{unique_suffix}",
                first_name="John",
                last_name="Worker",
                official_email=f"john.worker.{unique_suffix}@example.com",
                reporting_manager_id=mgr_read.id,
                department_id=dept1.id,
                unit_id=unit.id,
                designation_id=desig.id,
                date_of_joining=date(2024, 2, 1),
            )
            staff_read = await emp_service.create_employee(staff_data)
            assert staff_read.reporting_manager_id == mgr_read.id
            assert staff_read.reporting_manager_name == "Jane Manager"

            # 3. Test circular hierarchy prevention (manager reporting to staff)
            with pytest.raises(HTTPException) as exc_info:
                await emp_service.update_employee(
                    mgr_read.id,
                    EmployeeUpdate(reporting_manager_id=staff_read.id),
                )
            assert exc_info.value.status_code == 400
            assert "Circular" in exc_info.value.detail or "reporting" in exc_info.value.detail

            # 4. Test self-reporting prevention
            with pytest.raises(HTTPException) as exc_info:
                await emp_service.update_employee(
                    mgr_read.id,
                    EmployeeUpdate(reporting_manager_id=mgr_read.id),
                )
            assert exc_info.value.status_code == 400

            # 5. Test internal transfer / work history tracking
            updated_staff = await emp_service.update_employee(
                staff_read.id,
                EmployeeUpdate(department_id=dept2.id),
            )
            assert updated_staff.department_id == dept2.id
            assert updated_staff.department_name == dept2.name

            staff_history = await emp_service.get_work_history(staff_read.id)
            assert len(staff_history) == 2
            assert staff_history[0].department_id == dept2.id

            # 6. Test deactivation and reactivation
            deactivated = await emp_service.deactivate_employee(
                staff_read.id,
                exit_date=date.today(),
                exit_reason="Career break",
            )
            assert deactivated.status == "INACTIVE"
            assert deactivated.exit_date == date.today()

            activated = await emp_service.activate_employee(staff_read.id)
            assert activated.status == "ACTIVE"
            assert activated.exit_date is None

    run_async(_test())
