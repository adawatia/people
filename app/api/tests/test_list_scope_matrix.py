import uuid
from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.employee_access import EmployeeAccessScope
from core.settings import get_settings
from db.models import (
    AttendancePunch,
    AttendanceRecord,
    Department,
    Employee,
    EmployeeWorkHistory,
    LeaveApplication,
    LeaveType,
    Notification,
    Organization,
    OvertimeRecord,
    Shift,
    ShiftAssignment,
    Unit,
    WorkArrangementRequest,
)
from repositories.attendance_punch_repo import AttendancePunchRepository
from repositories.attendance_record_repo import AttendanceRecordRepository
from repositories.employee_repo import EmployeeRepository
from repositories.leave_repo import LeaveRepository
from repositories.notification_repo import NotificationRepository
from repositories.overtime_repo import OvertimeRepository
from repositories.shift_repo import ShiftRepository
from repositories.work_arrangement_repo import WorkArrangementRepository


class QueryAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def scalars(self, statement):
        return self.session.scalars(statement)


@pytest.fixture
def database():
    engine = create_engine(get_settings().resolved_database_url_sync())
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def list_matrix(database):
    session = database
    suffix = uuid.uuid4().hex[:10]
    organization = session.scalar(select(Organization).limit(1))
    if organization is None:
        organization = Organization(name=f"Matrix {suffix}")
        session.add(organization)
        session.flush()

    unit_a = Unit(organization_id=organization.id, name=f"Matrix A {suffix}", code=f"MA{suffix}")
    unit_b = Unit(organization_id=organization.id, name=f"Matrix B {suffix}", code=f"MB{suffix}")
    session.add_all([unit_a, unit_b])
    session.flush()
    department_a = Department(unit_id=unit_a.id, name=f"Department A {suffix}", code=f"DA{suffix}")
    department_b = Department(unit_id=unit_b.id, name=f"Department B {suffix}", code=f"DB{suffix}")
    session.add_all([department_a, department_b])
    session.flush()

    employees_a = [
        Employee(
            employee_code=f"{suffix}-A-{index}",
            first_name=f"Matrix{suffix}",
            last_name="Scoped",
            unit_id=unit_a.id,
            department_id=department_a.id,
            status="ACTIVE",
        )
        for index in range(3)
    ]
    employee_b = Employee(
        employee_code=f"{suffix}-B-0",
        first_name=f"Matrix{suffix}",
        last_name="Outside",
        unit_id=unit_b.id,
        department_id=department_b.id,
        status="ACTIVE",
    )
    session.add_all([*employees_a, employee_b])
    session.flush()

    leave_type = LeaveType(name=f"Matrix Leave {suffix}", code=f"L{suffix}", is_paid=True)
    shift = Shift(
        unit_id=unit_a.id,
        name=f"Matrix Shift {suffix}",
        code=f"S{suffix}",
        start_time=time(9),
        end_time=time(18),
    )
    session.add_all([leave_type, shift])
    session.flush()

    all_employees = [*employees_a, employee_b]
    attendance_date = date(2097, 1, 15)
    punch_time = datetime(2097, 1, 15, 9, tzinfo=UTC)
    attendance = []
    for employee in all_employees:
        record = AttendanceRecord(
            employee_id=employee.id,
            attendance_date=attendance_date,
            status="PRESENT",
            worked_minutes=480,
        )
        session.add(record)
        session.flush()
        attendance.append(record)
        session.add_all(
            [
                AttendancePunch(employee_id=employee.id, punch_time=punch_time, punch_type="IN"),
                LeaveApplication(
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    from_date=date(2097, 2, 1),
                    to_date=date(2097, 2, 1),
                    days_count=1,
                    status="PENDING",
                ),
                WorkArrangementRequest(
                    employee_id=employee.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=date(2097, 3, 1),
                    to_date=date(2097, 3, 1),
                    reason="Matrix scope test",
                    status="PENDING",
                ),
                OvertimeRecord(
                    employee_id=employee.id,
                    attendance_record_id=record.id,
                    calculated_minutes=60,
                    status="PENDING",
                ),
                ShiftAssignment(
                    employee_id=employee.id,
                    shift_id=shift.id,
                    effective_from=date(2097, 1, 1),
                    status="ACTIVE",
                ),
            ]
        )

    for index in range(3):
        session.add(
            EmployeeWorkHistory(
                employee_id=employees_a[0].id,
                unit_id=unit_a.id,
                department_id=department_a.id,
                from_date=date(2096, 1, 1),
                remarks=f"Matrix history {suffix} {index}",
            )
        )
        session.add(
            Notification(
                title=f"Matrix notification {suffix} {index}",
                message="Matrix notification",
                notification_type="SYSTEM",
                target_role=f"MATRIX_{suffix}",
                created_at=punch_time,
            )
        )
    session.flush()
    return {
        "session": QueryAdapter(session),
        "suffix": suffix,
        "unit_a": unit_a,
        "department_a": department_a,
        "employees_a": employees_a,
        "employee_b": employee_b,
    }


def _assert_stable_pages(first, repeated, second, expected_employee_ids=None):
    first_ids = [item.id if hasattr(item, "id") else item.notification_id for item in first["items"]]
    repeated_ids = [item.id if hasattr(item, "id") else item.notification_id for item in repeated["items"]]
    second_ids = [item.id if hasattr(item, "id") else item.notification_id for item in second["items"]]
    assert first_ids == repeated_ids
    assert not set(first_ids) & set(second_ids)
    if expected_employee_ids is not None:
        assert {item.employee_id for item in [*first["items"], *second["items"]]} <= expected_employee_ids


@pytest.mark.asyncio
async def test_scope_isolation_and_deterministic_ordering_across_business_lists(list_matrix):
    session = list_matrix["session"]
    unit_id = list_matrix["unit_a"].id
    department_id = list_matrix["department_a"].id
    expected = {employee.id for employee in list_matrix["employees_a"]}
    common = {"page_size": 2, "sort_order": "asc"}

    async def assert_pages(fetch):
        first = await fetch(page=1, **common)
        repeated = await fetch(page=1, **common)
        second = await fetch(page=2, **common)
        assert first["total"] == 3
        _assert_stable_pages(first, repeated, second, expected)

    attendance_repo = AttendanceRecordRepository(session)
    await assert_pages(
        lambda **paging: attendance_repo.list_records_page(
            unit_ids={unit_id}, sort_by="attendance_date", **paging
        )
    )
    punch_repo = AttendancePunchRepository(session)
    await assert_pages(
        lambda **paging: punch_repo.list_punches_page(unit_ids={unit_id}, sort_by="punch_time", **paging)
    )
    leave_repo = LeaveRepository(session)
    await assert_pages(
        lambda **paging: leave_repo.list_applications_page(
            department_ids={department_id}, sort_by="status", **paging
        )
    )
    work_repo = WorkArrangementRepository(session)
    await assert_pages(
        lambda **paging: work_repo.list_requests_page(unit_ids={unit_id}, sort_by="status", **paging)
    )
    overtime_repo = OvertimeRepository(session)
    await assert_pages(
        lambda **paging: overtime_repo.list_page(
            unit_ids={unit_id}, sort_by="attendance_date", **paging
        )
    )
    shift_repo = ShiftRepository(session)
    scope = EmployeeAccessScope(unit_ids={unit_id})
    await assert_pages(
        lambda **paging: shift_repo.assignments_page(scope, sort_by="effective_from", **paging)
    )

    employee_repo = EmployeeRepository(session)
    page_one, total = await employee_repo.list_paginated(
        page=1,
        page_size=2,
        allowed_unit_ids={unit_id},
        sort_by="status",
        sort_order="asc",
    )
    repeated, _ = await employee_repo.list_paginated(
        page=1,
        page_size=2,
        allowed_unit_ids={unit_id},
        sort_by="status",
        sort_order="asc",
    )
    page_two, _ = await employee_repo.list_paginated(
        page=2,
        page_size=2,
        allowed_unit_ids={unit_id},
        sort_by="status",
        sort_order="asc",
    )
    assert total == 3
    assert [item.id for item in page_one] == [item.id for item in repeated]
    assert not {item.id for item in page_one} & {item.id for item in page_two}
    assert {item.id for item in [*page_one, *page_two]} == expected


@pytest.mark.asyncio
async def test_deterministic_ordering_for_history_notifications_and_lookup_lists(list_matrix):
    session = list_matrix["session"]
    suffix = list_matrix["suffix"]
    employee = list_matrix["employees_a"][0]
    employee_repo = EmployeeRepository(session)

    async def history(page):
        return await employee_repo.work_history_page(
            employee.id,
            page=page,
            page_size=2,
            search=f"Matrix history {suffix}",
            sort_by="from_date",
            sort_order="asc",
        )

    first, repeated, second = await history(1), await history(1), await history(2)
    assert first["total"] == 3
    _assert_stable_pages(first, repeated, second)

    notification_repo = NotificationRepository(session)
    audience = Notification.target_role == f"MATRIX_{suffix}"

    async def notifications(page):
        return await notification_repo.list_page(
            audience,
            page,
            2,
            search=f"Matrix notification {suffix}",
            sort_by="created_at",
            sort_order="asc",
        )

    first, repeated, second = await notifications(1), await notifications(1), await notifications(2)
    assert first["total"] == 3
    _assert_stable_pages(first, repeated, second)

    shift_repo = ShiftRepository(session)
    for index in range(3):
        list_matrix["session"].session.add(
            Shift(
                unit_id=list_matrix["unit_a"].id,
                name=f"Lookup {suffix}",
                code=f"LK{suffix}{index}",
                start_time=time(9),
                end_time=time(18),
            )
        )
    list_matrix["session"].session.flush()

    async def definitions(page):
        return await shift_repo.definitions_page(
            unit_id=list_matrix["unit_a"].id,
            page=page,
            page_size=2,
            search=f"Lookup {suffix}",
            sort_by="name",
            sort_order="asc",
        )

    first, repeated, second = await definitions(1), await definitions(1), await definitions(2)
    assert first["total"] == 3
    _assert_stable_pages(first, repeated, second)
