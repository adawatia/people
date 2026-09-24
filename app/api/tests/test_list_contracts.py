import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from core.settings import get_settings
from db.models import Employee, LeaveBalance, LeaveType, WorkArrangementRequest
from repositories.work_arrangement_repo import WorkArrangementRepository
from services.report_service import ReportService


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
            yield session, engine
        transaction.rollback()
    engine.dispose()


@pytest.mark.asyncio
async def test_paging_filters_counts_search_sort_and_bounds(database):
    session, _ = database
    suffix = uuid.uuid4().hex[:8]
    employee = Employee(employee_code=suffix, first_name=f"Page_{suffix}", last_name="Worker")
    session.add(employee)
    session.flush()
    for _ in range(6):
        session.add(WorkArrangementRequest(employee_id=employee.id, arrangement_type="WORK_FROM_HOME",
                    from_date=date(2026, 9, 1), to_date=date(2026, 9, 2), reason="Test request", status="PENDING"))
    session.flush()
    repo = WorkArrangementRepository(QueryAdapter(session))
    first = await repo.list_requests_page(employee_id=employee.id, page_size=2, search=suffix)
    second = await repo.list_requests_page(employee_id=employee.id, page=2, page_size=2, search=suffix)
    assert first["total"] == second["total"] == 6
    assert first["total_pages"] == 3
    assert not {x.id for x in first["items"]} & {x.id for x in second["items"]}
    assert (await repo.list_requests_page(employee_id=employee.id, status="REJECTED"))["total"] == 0
    assert (await repo.list_requests_page(employee_id=employee.id, search="%"))["total"] == 0
    for params in [{"page": 0}, {"page_size": 101}, {"sort_by": "id; DROP TABLE employees"}, {"sort_order": "bad"}]:
        with pytest.raises(HTTPException) as exc:
            await repo.list_requests_page(employee_id=employee.id, **params)
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_report_balances_are_batched_and_totals_ignore_page(database):
    session, engine = database
    suffix = uuid.uuid4().hex[:8]
    leave_type = LeaveType(name=f"Test {suffix}", code=suffix, is_paid=True)
    session.add(leave_type)
    employees = [Employee(employee_code=f"{suffix}-{i}", first_name=suffix, last_name="Report", status="ACTIVE") for i in range(5)]
    session.add_all(employees)
    session.flush()
    session.add_all([LeaveBalance(employee_id=e.id, leave_type_id=leave_type.id, year=2026, allocated=10, used=2, pending=1) for e in employees])
    session.flush()
    queries = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        queries.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        service = ReportService(QueryAdapter(session))
        result = await service.get_leave_balance_summary(2026, search=suffix, page_size=2)
        assert result.total == 5 and len(result.items) == 2
        assert result.breakdown == [{"leave_type_name": leave_type.name, "allocated": 50, "used": 10, "pending": 5}]
        count_two = len(queries)
        queries.clear()
        result = await service.get_leave_balance_summary(2026, search=suffix, page_size=5)
        assert len(result.items) == 5
        assert len(queries) <= count_two + 1
        assert len(queries) <= 7
        queries.clear()
        empty = await service.get_monthly_attendance_matrix(2026, 9, search="nonexistent-" + suffix)
        assert empty.total == 0 and empty.items == []
        records_sql = [q for q in queries if "FROM attendance_records" in q]
        assert records_sql and all("employee_id IN" in q for q in records_sql)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
