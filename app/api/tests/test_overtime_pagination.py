from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.settings import get_settings
from db.models import AttendanceRecord, Employee, Organization, OvertimeRecord, Unit
from services.overtime_service import OvertimeService


class AsyncQueryAdapter:
    """Run real SQL without a worker thread; production uses AsyncSession."""

    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def scalar(self, statement):
        return self.session.scalar(statement)


@pytest.mark.asyncio
async def test_overtime_pages_apply_scope_search_dates_and_stable_order():
    engine = create_engine(get_settings().resolved_database_url_sync())
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            with Session(connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                organization = session.query(Organization).first()
                if organization is None:
                    organization = Organization(name="Pagination test", short_name="PAGINATION")
                    session.add(organization)
                    session.flush()
                units = [Unit(name="Page unit A", code="PAGE_A", organization_id=organization.id),
                         Unit(name="Page unit B", code="PAGE_B", organization_id=organization.id)]
                session.add_all(units)
                session.flush()
                alice = Employee(employee_code="A_100", first_name="Alice", last_name="Singh", unit_id=units[0].id)
                other = Employee(employee_code="B200", first_name="Alice", last_name="Singh", unit_id=units[1].id)
                session.add_all([alice, other])
                session.flush()
                for employee, day, count, status in [
                    (alice, date(2026, 9, 2), 3, "PENDING"),
                    (alice, date(2026, 8, 1), 1, "PENDING"),
                    (alice, date(2026, 9, 3), 1, "APPROVED"),
                    (other, date(2026, 9, 2), 1, "PENDING"),
                ]:
                    attendance = AttendanceRecord(employee_id=employee.id, attendance_date=day)
                    session.add(attendance)
                    session.flush()
                    session.add_all([
                        OvertimeRecord(employee_id=employee.id, attendance_record_id=attendance.id,
                                       calculated_minutes=60, status=status)
                        for _ in range(count)
                    ])
                session.commit()
                # Force the query to provide its related data; don't rely on fixture identity-map state.
                session.expunge_all()
                service = OvertimeService(AsyncQueryAdapter(session))
                filters = {"unit_ids": {units[0].id}, "q": " Alice Singh ", "status": "PENDING",
                           "from_date": date(2026, 9, 1), "to_date": date(2026, 9, 30), "page_size": 2}
                first = await service.list_overtime(page=1, **filters)
                second = await service.list_overtime(page=2, **filters)
                assert first.total == second.total == 3
                assert first.total_pages == 2
                assert first.has_next and not first.has_prev
                assert second.has_prev and not second.has_next
                ids = [item.id for item in first.items + second.items]
                assert ids == sorted(ids, reverse=True) and len(set(ids)) == 3
                assert first.items[0].employee_name == "Alice Singh"
                assert first.items[0].employee_code == "A_100"
                assert first.items[0].attendance_date == date(2026, 9, 2)
                literal = await service.list_overtime(page=1, q="%", unit_ids={units[0].id})
                assert literal.total == 0
                assert literal.total_pages == 1
                self_page = await service.list_overtime(page=1, employee_id=alice.id)
                assert self_page.total == 5
            transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_inverted_overtime_dates_are_rejected_before_query():
    with pytest.raises(HTTPException) as error:
        await OvertimeService(None).list_overtime(from_date=date(2026, 10, 1), to_date=date(2026, 9, 1))
    assert error.value.status_code == 422
