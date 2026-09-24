from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.pagination import employee_search, ordered, paginate
from db.models import AttendanceRecord, Employee, LeaveBalance


class ReportRepository:
    def __init__(self, session):
        self.session = session

    def employees(self, unit_id=None, department_id=None, search=None):
        query = select(Employee).where(Employee.status == "ACTIVE")
        if unit_id is not None:
            query = query.where(Employee.unit_id == unit_id)
        if department_id is not None:
            query = query.where(Employee.department_id == department_id)
        return employee_search(query, Employee, search)

    async def employee_page(self, query, page, page_size, sort_by=None, sort_order="asc"):
        query = ordered(query, {"employee_code": Employee.employee_code, "name": Employee.first_name},
                        sort_by, sort_order, "employee_code", Employee.id)
        return await paginate(self.session, query.options(selectinload(Employee.department),
                              selectinload(Employee.designation_rel)), page, page_size)

    async def attendance(self, employee_ids, start, end):
        query = select(AttendanceRecord).where(AttendanceRecord.employee_id.in_(employee_ids),
                    AttendanceRecord.attendance_date >= start, AttendanceRecord.attendance_date <= end)
        return list((await self.session.scalars(query)).all())

    async def balances(self, employee_ids, year):
        query = select(LeaveBalance).options(selectinload(LeaveBalance.leave_type)).where(
            LeaveBalance.employee_id.in_(employee_ids), LeaveBalance.year == year)
        return list((await self.session.scalars(query)).all())

    async def balance_totals(self, employee_query, year):
        from db.models import LeaveType
        ids = employee_query.with_only_columns(Employee.id).order_by(None)
        query = (select(LeaveType.name, func.sum(LeaveBalance.allocated), func.sum(LeaveBalance.used),
                        func.sum(LeaveBalance.pending)).join(LeaveType, LeaveBalance.leave_type_id == LeaveType.id)
                 .where(LeaveBalance.employee_id.in_(ids), LeaveBalance.year == year)
                 .group_by(LeaveType.id, LeaveType.name).order_by(LeaveType.name))
        return [{"leave_type_name": name, "allocated": float(allocated), "used": float(used), "pending": float(pending)}
                for name, allocated, used, pending in (await self.session.execute(query)).all()]
