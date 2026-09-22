"""Organization-owner aggregate analytics without sensitive employee fields."""

import math
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    Department,
    Employee,
    LeaveApplication,
    OvertimeRecord,
    Unit,
    WorkArrangementRequest,
    now_ist,
)
from repositories.employee_repo import EmployeeRepository
from schemas.dashboard import (
    OwnerDashboardResponse,
    OwnerExceptionResponse,
    OwnerOrgRow,
    OwnerSummary,
    OwnerTrendPoint,
)
from services.employee_service import EmployeeService

WORKING_STATUSES = {"PRESENT", "HALF_DAY", "WORK_FROM_HOME"}
NON_WORKING_STATUSES = {"WEEKLY_OFF", "HOLIDAY"}
EXCEPTION_KINDS = {"absent", "late", "late_or_missed_punch", "missed_punch", "on_leave", "pending_request"}
PENDING_LEAVE_STATUSES = ("PENDING", "CANCELLATION_PENDING")


class OwnerDashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _date_range(from_date: date | None, to_date: date | None) -> tuple[date, date]:
        end = to_date or now_ist().date()
        start = from_date or end - timedelta(days=29)
        if start > end:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="from_date must not be after to_date"
            )
        if (end - start).days > 366:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Date range cannot exceed 366 days"
            )
        return start, end

    async def dashboard(
        self, from_date: date | None, to_date: date | None, unit_id: int | None
    ) -> OwnerDashboardResponse:
        start, end = self._date_range(from_date, to_date)
        if unit_id is not None and await self.session.get(Unit, unit_id) is None:
            raise HTTPException(status_code=404, detail="Unit not found")

        employee_filter = [Employee.status == "ACTIVE"]
        if unit_id is not None:
            employee_filter.append(Employee.unit_id == unit_id)

        headcount = await self.session.scalar(select(func.count(Employee.id)).where(*employee_filter)) or 0
        day_records = (
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceRecord.attendance_date == end, *employee_filter)
            .group_by(AttendanceRecord.status)
        )
        day_status = {row[0]: row[1] for row in (await self.session.execute(day_records)).all()}
        present = sum(day_status.get(value, 0) for value in WORKING_STATUSES)
        absent = day_status.get("ABSENT", 0)
        on_leave = day_status.get("ON_LEAVE", 0)
        weekly_off = sum(day_status.get(value, 0) for value in NON_WORKING_STATUSES)
        denominator = max(headcount - on_leave - weekly_off, 0)
        exceptions = (
            await self.session.scalar(
                select(func.count(AttendanceRecord.id))
                .join(Employee, AttendanceRecord.employee_id == Employee.id)
                .where(AttendanceRecord.attendance_date == end, *employee_filter)
                .where(or_(AttendanceRecord.late_minutes > 0, AttendanceRecord.status == "MISSED_PUNCH"))
            )
            or 0
        )
        pending = await self._pending_requests(unit_id)
        overtime = await self._approved_overtime(start, end, unit_id)

        trend_rows = (
            select(AttendanceRecord.attendance_date, AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceRecord.attendance_date.between(start, end), *employee_filter)
            .group_by(AttendanceRecord.attendance_date, AttendanceRecord.status)
        )
        trend_map: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for record_date, record_status, count in (await self.session.execute(trend_rows)).all():
            trend_map[record_date][record_status] += count
        trend = []
        cursor = start
        while cursor <= end:
            counts = trend_map[cursor]
            trend.append(
                OwnerTrendPoint(
                    date=cursor,
                    present=sum(counts[value] for value in WORKING_STATUSES),
                    absent=counts["ABSENT"],
                    on_leave=counts["ON_LEAVE"],
                    weekly_off_or_holiday=sum(counts[value] for value in NON_WORKING_STATUSES),
                )
            )
            cursor += timedelta(days=1)

        units = await self._org_rows("unit", end, start, unit_id)
        departments = await self._org_rows("department", end, start, unit_id) if unit_id is not None else []
        latest_sync = await self.session.scalar(select(func.max(AttendanceRecord.last_synced_at)))
        return OwnerDashboardResponse(
            from_date=start,
            to_date=end,
            generated_at=now_ist(),
            attendance_last_synced_at=latest_sync,
            summary=OwnerSummary(
                active_headcount=headcount,
                present=present,
                absent=absent,
                on_leave=on_leave,
                weekly_off_or_holiday=weekly_off,
                attendance_rate=round((present / denominator) * 100, 1) if denominator else 0.0,
                late_or_missed_punches=exceptions,
                pending_requests=pending,
                approved_overtime_minutes=overtime,
            ),
            trend=trend,
            units=units,
            departments=departments,
        )

    async def _pending_requests(self, unit_id: int | None) -> int:
        async def count_for(model, employee_column) -> int:
            query = (
                select(func.count(model.id))
                .join(Employee, employee_column == Employee.id)
                .where(
                    model.status.in_(PENDING_LEAVE_STATUSES)
                    if model is LeaveApplication
                    else model.status == "PENDING"
                )
            )
            if unit_id is not None:
                query = query.where(Employee.unit_id == unit_id)
            return await self.session.scalar(query) or 0

        correction_query = (
            select(func.count(AttendanceCorrectionRequest.id))
            .join(AttendanceRecord, AttendanceCorrectionRequest.attendance_record_id == AttendanceRecord.id)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceCorrectionRequest.status == "PENDING")
        )
        if unit_id is not None:
            correction_query = correction_query.where(Employee.unit_id == unit_id)
        correction_count = await self.session.scalar(correction_query) or 0
        return (
            await count_for(LeaveApplication, LeaveApplication.employee_id)
            + await count_for(OvertimeRecord, OvertimeRecord.employee_id)
            + await count_for(WorkArrangementRequest, WorkArrangementRequest.employee_id)
            + correction_count
        )

    async def _approved_overtime(self, start: date, end: date, unit_id: int | None) -> int:
        query = (
            select(func.coalesce(func.sum(OvertimeRecord.approved_minutes), 0))
            .join(AttendanceRecord, OvertimeRecord.attendance_record_id == AttendanceRecord.id)
            .join(Employee, OvertimeRecord.employee_id == Employee.id)
            .where(OvertimeRecord.status == "APPROVED", AttendanceRecord.attendance_date.between(start, end))
        )
        if unit_id is not None:
            query = query.where(Employee.unit_id == unit_id)
        return int(await self.session.scalar(query) or 0)

    async def _org_rows(
        self, level: str, target_date: date, start: date, selected_unit_id: int | None
    ) -> list[OwnerOrgRow]:
        model, foreign_key = (Unit, Employee.unit_id) if level == "unit" else (Department, Employee.department_id)
        entity_filter = [Employee.status == "ACTIVE"]
        if selected_unit_id is not None:
            entity_filter.append(Employee.unit_id == selected_unit_id)
        headcount_rows = (
            select(foreign_key, func.count(Employee.id))
            .where(*entity_filter, foreign_key.is_not(None))
            .group_by(foreign_key)
        )
        headcounts = dict((await self.session.execute(headcount_rows)).all())
        if not headcounts:
            return []
        ids = set(headcounts)
        names = dict((await self.session.execute(select(model.id, model.name).where(model.id.in_(ids)))).all())
        status_rows = (
            select(foreign_key, AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceRecord.attendance_date == target_date, foreign_key.in_(ids), Employee.status == "ACTIVE")
            .group_by(foreign_key, AttendanceRecord.status)
        )
        statuses: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for entity_id, record_status, count in (await self.session.execute(status_rows)).all():
            statuses[entity_id][record_status] += count
        exception_rows = (
            select(foreign_key, func.count(AttendanceRecord.id))
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .where(AttendanceRecord.attendance_date == target_date, foreign_key.in_(ids))
            .where(or_(AttendanceRecord.late_minutes > 0, AttendanceRecord.status == "MISSED_PUNCH"))
            .group_by(foreign_key)
        )
        exception_counts = dict((await self.session.execute(exception_rows)).all())
        overtime_rows = (
            select(foreign_key, func.coalesce(func.sum(OvertimeRecord.approved_minutes), 0))
            .join(Employee, OvertimeRecord.employee_id == Employee.id)
            .join(AttendanceRecord, OvertimeRecord.attendance_record_id == AttendanceRecord.id)
            .where(
                OvertimeRecord.status == "APPROVED",
                AttendanceRecord.attendance_date.between(start, target_date),
                foreign_key.in_(ids),
            )
            .group_by(foreign_key)
        )
        overtime = dict((await self.session.execute(overtime_rows)).all())
        result = []
        for entity_id, count in headcounts.items():
            values = statuses[entity_id]
            p_count = sum(values[value] for value in WORKING_STATUSES)
            leave_count = values["ON_LEAVE"]
            off_count = sum(values[value] for value in NON_WORKING_STATUSES)
            denom = max(count - leave_count - off_count, 0)
            result.append(
                OwnerOrgRow(
                    id=entity_id,
                    name=names.get(entity_id, "Unknown"),
                    headcount=count,
                    present=p_count,
                    absent=values["ABSENT"],
                    on_leave=leave_count,
                    exceptions=exception_counts.get(entity_id, 0),
                    attendance_rate=round((p_count / denom) * 100, 1) if denom else 0.0,
                    approved_overtime_minutes=int(overtime.get(entity_id, 0)),
                )
            )
        return sorted(result, key=lambda row: (row.attendance_rate, row.name))

    async def exceptions(
        self, kind: str, unit_id: int | None, target_date: date, page: int, page_size: int
    ) -> OwnerExceptionResponse:
        if kind not in EXCEPTION_KINDS:
            raise HTTPException(status_code=422, detail=f"kind must be one of: {', '.join(sorted(EXCEPTION_KINDS))}")
        if unit_id is not None and await self.session.get(Unit, unit_id) is None:
            raise HTTPException(status_code=404, detail="Unit not found")
        query = select(Employee.id).where(Employee.status == "ACTIVE")
        if unit_id is not None:
            query = query.where(Employee.unit_id == unit_id)
        if kind == "pending_request":
            pending_employee_ids = (
                select(LeaveApplication.employee_id)
                .where(LeaveApplication.status.in_(PENDING_LEAVE_STATUSES))
                .union(
                    select(OvertimeRecord.employee_id).where(OvertimeRecord.status == "PENDING"),
                    select(WorkArrangementRequest.employee_id).where(WorkArrangementRequest.status == "PENDING"),
                    select(AttendanceRecord.employee_id)
                    .join(
                        AttendanceCorrectionRequest,
                        AttendanceCorrectionRequest.attendance_record_id == AttendanceRecord.id,
                    )
                    .where(AttendanceCorrectionRequest.status == "PENDING"),
                )
            )
            query = query.where(Employee.id.in_(pending_employee_ids))
        else:
            record_query = select(AttendanceRecord.employee_id).where(AttendanceRecord.attendance_date == target_date)
            if kind == "absent":
                record_query = record_query.where(AttendanceRecord.status == "ABSENT")
            elif kind == "late":
                record_query = record_query.where(AttendanceRecord.late_minutes > 0)
            elif kind == "late_or_missed_punch":
                record_query = record_query.where(
                    or_(AttendanceRecord.late_minutes > 0, AttendanceRecord.status == "MISSED_PUNCH")
                )
            elif kind == "missed_punch":
                record_query = record_query.where(AttendanceRecord.status == "MISSED_PUNCH")
            else:
                record_query = record_query.where(AttendanceRecord.status == "ON_LEAVE")
            query = query.where(Employee.id.in_(record_query))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        ids = list(
            (
                await self.session.execute(
                    query.order_by(Employee.employee_code).offset((page - 1) * page_size).limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        repo = EmployeeRepository(self.session)
        service = EmployeeService(self.session)
        employees = [await repo.get_by_id(employee_id) for employee_id in ids]
        return OwnerExceptionResponse(
            items=[service.enrich_directory(employee) for employee in employees if employee],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 1,
        )
