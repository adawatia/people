from datetime import date, datetime, time, timedelta
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Employee, Shift, ShiftAssignment, now_ist
from repositories.employee_repo import EmployeeRepository
from repositories.shift_repo import ShiftRepository
from schemas.shifts import (
    BulkShiftAssignmentCreate,
    EmployeeShiftScheduleRead,
    ShiftAssignmentCreate,
    ShiftAssignmentRead,
    ShiftCreate,
    ShiftRead,
    ShiftUpdate,
    ShiftWindowDetail,
)


class ShiftService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ShiftRepository(session)
        self.employee_repo = EmployeeRepository(session)

    @staticmethod
    def parse_time(val: str | time) -> time:
        if isinstance(val, time):
            return val
        parts = val.strip().split(":")
        return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)

    async def list_shifts(self, unit_id: int | None = None, is_active: bool | None = True) -> list[ShiftRead]:
        shifts = await self.repo.list_shifts(unit_id=unit_id, is_active=is_active)
        return [ShiftRead.model_validate(s) for s in shifts]

    async def get_shift(self, shift_id: int) -> Shift:
        shift = await self.repo.get_by_id(shift_id)
        if not shift:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shift with ID {shift_id} not found",
            )
        return shift

    async def create_shift(self, data: ShiftCreate) -> ShiftRead:
        start = self.parse_time(data.start_time)
        end = self.parse_time(data.end_time)
        if start == end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift start time and end time cannot be identical",
            )

        is_cross_midnight = start > end
        payload = data.model_dump()
        payload["start_time"] = start
        payload["end_time"] = end
        payload["is_cross_midnight"] = is_cross_midnight

        shift = Shift(**payload)
        created = await self.repo.create_shift(shift)
        await self.session.commit()
        await self.session.refresh(created)
        return ShiftRead.model_validate(created)

    async def update_shift(self, shift_id: int, data: ShiftUpdate) -> ShiftRead:
        shift = await self.get_shift(shift_id)
        update_data = data.model_dump(exclude_unset=True)

        if "start_time" in update_data:
            update_data["start_time"] = self.parse_time(update_data["start_time"])
        if "end_time" in update_data:
            update_data["end_time"] = self.parse_time(update_data["end_time"])

        start = update_data.get("start_time", shift.start_time)
        end = update_data.get("end_time", shift.end_time)
        if start == end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift start time and end time cannot be identical",
            )
        update_data["is_cross_midnight"] = start > end

        for key, val in update_data.items():
            setattr(shift, key, val)

        await self.session.commit()
        await self.session.refresh(shift)
        return ShiftRead.model_validate(shift)

    # ── Shift Assignment Logic ─────────────────────────────────────────────────

    @staticmethod
    def to_assignment_read(assignment: ShiftAssignment) -> ShiftAssignmentRead:
        r = ShiftAssignmentRead.model_validate(assignment)
        if assignment.shift:
            r.shift_name = assignment.shift.name
            r.shift_code = assignment.shift.code
            r.start_time = assignment.shift.start_time.strftime("%H:%M") if hasattr(assignment.shift.start_time, "strftime") else str(assignment.shift.start_time)
            r.end_time = assignment.shift.end_time.strftime("%H:%M") if hasattr(assignment.shift.end_time, "strftime") else str(assignment.shift.end_time)
        if assignment.employee:
            r.employee_name = f"{assignment.employee.first_name} {assignment.employee.last_name or ''}".strip()
            r.employee_code = assignment.employee.employee_code
        return r

    async def assign_shift(
        self,
        data: ShiftAssignmentCreate,
        assigned_by_user_id: int | None = None,
    ) -> ShiftAssignmentRead:
        emp = await self.employee_repo.get_by_id(data.employee_id)
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee with ID {data.employee_id} not found",
            )
        shift = await self.get_shift(data.shift_id)
        if not shift.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Shift '{shift.name}' is inactive and cannot be assigned",
            )

        if data.effective_to and data.effective_to < data.effective_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="effective_to date must be greater than or equal to effective_from",
            )

        # Overlap check
        overlap = await self.repo.find_overlapping_assignment(
            employee_id=data.employee_id,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
        )
        if overlap:
            shift_info = overlap.shift.name if overlap.shift else f"ID {overlap.shift_id}"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Employee already has an active shift '{shift_info}' overlapping with this period",
            )

        assignment = ShiftAssignment(
            employee_id=data.employee_id,
            shift_id=data.shift_id,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            assigned_by=assigned_by_user_id,
            status="ACTIVE",
        )
        created = await self.repo.create_assignment(assignment)
        # Update default shift_id on employee if not set
        if emp.shift_id is None:
            emp.shift_id = data.shift_id

        await self.session.commit()
        refreshed = await self.repo.get_assignment_by_id(created.id)
        return self.to_assignment_read(refreshed)

    async def bulk_assign_shifts(
        self,
        data: BulkShiftAssignmentCreate,
        assigned_by_user_id: int | None = None,
    ) -> list[ShiftAssignmentRead]:
        shift = await self.get_shift(data.shift_id)
        if not shift.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Shift '{shift.name}' is inactive and cannot be assigned",
            )

        # Resolve employee IDs
        emp_ids = set(data.employee_ids)
        if data.department_id is not None or data.unit_id is not None:
            stmt = select(Employee.id).where(Employee.status == "ACTIVE")
            if data.department_id is not None:
                stmt = stmt.where(Employee.department_id == data.department_id)
            if data.unit_id is not None:
                stmt = stmt.where(Employee.unit_id == data.unit_id)
            matched = (await self.session.execute(stmt)).scalars().all()
            emp_ids.update(matched)

        if not emp_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No employees specified or matched for bulk shift assignment",
            )

        results = []
        for emp_id in emp_ids:
            # Skip or close overlapping
            overlap = await self.repo.find_overlapping_assignment(
                employee_id=emp_id,
                effective_from=data.effective_from,
                effective_to=data.effective_to,
            )
            if overlap:
                # Mark previous assignment as inactive or end it right before new shift
                if overlap.effective_from < data.effective_from:
                    overlap.effective_to = data.effective_from - timedelta(days=1)
                else:
                    overlap.status = "INACTIVE"

            assignment = ShiftAssignment(
                employee_id=emp_id,
                shift_id=data.shift_id,
                effective_from=data.effective_from,
                effective_to=data.effective_to,
                assigned_by=assigned_by_user_id,
                status="ACTIVE",
            )
            created = await self.repo.create_assignment(assignment)
            results.append(created)

        await self.session.commit()
        assigned_reads = []
        for a in results:
            refreshed = await self.repo.get_assignment_by_id(a.id)
            if refreshed:
                assigned_reads.append(self.to_assignment_read(refreshed))
        return assigned_reads

    async def list_assignments(
        self,
        shift_id: int | None = None,
        employee_id: int | None = None,
        status: str | None = None,
    ) -> list[ShiftAssignmentRead]:
        items = await self.repo.list_assignments(shift_id=shift_id, employee_id=employee_id, status=status)
        return [self.to_assignment_read(a) for a in items]

    async def get_assignment(self, assignment_id: int) -> ShiftAssignmentRead:
        assignment = await self.repo.get_assignment_by_id(assignment_id)
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shift assignment with ID {assignment_id} not found",
            )
        return self.to_assignment_read(assignment)

    async def cancel_assignment(
        self,
        assignment_id: int,
        cancelled_by_user_id: int | None = None,
    ) -> ShiftAssignmentRead:
        assignment = await self.repo.get_assignment_by_id(assignment_id)
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shift assignment with ID {assignment_id} not found",
            )
        assignment.status = "CANCELLED"
        assignment.effective_to = now_ist().date()
        await self.session.commit()
        refreshed = await self.repo.get_assignment_by_id(assignment_id)
        return self.to_assignment_read(refreshed)

    # ── Night Shift & Window Calculations ──────────────────────────────────────

    @staticmethod
    def get_shift_window(shift: Shift, shift_date: date) -> ShiftWindowDetail:
        """Calculates actual start and end timestamps for a shift on a given calendar date."""
        is_cross_midnight = shift.start_time > shift.end_time

        shift_start = datetime.combine(shift_date, shift.start_time)
        if is_cross_midnight:
            shift_end = datetime.combine(shift_date + timedelta(days=1), shift.end_time)
        else:
            shift_end = datetime.combine(shift_date, shift.end_time)

        actual_start = shift_start - timedelta(minutes=shift.begin_check_in_before_minutes)
        actual_end = shift_end + timedelta(minutes=shift.allow_check_out_after_minutes)

        return ShiftWindowDetail(
            shift_id=shift.id,
            shift_name=shift.name,
            shift_start=shift_start,
            shift_end=shift_end,
            actual_start=actual_start,
            actual_end=actual_end,
            is_cross_midnight=is_cross_midnight,
        )

    async def resolve_shift_for_timestamp(
        self,
        employee_id: int,
        timestamp: datetime,
    ) -> ShiftWindowDetail | None:
        """
        Determines the shift to which a punch belongs, accurately handling night shifts
        crossing midnight and buffer windows.
        """
        check_date = timestamp.date()
        # Look for active assignments covering yesterday, today, or tomorrow
        candidate_dates = [check_date - timedelta(days=1), check_date, check_date + timedelta(days=1)]

        best_match = None
        for cand_date in candidate_dates:
            assignments = await self.repo.list_active_assignments_for_date(employee_id, cand_date)
            for a in assignments:
                if not a.shift:
                    continue
                window = self.get_shift_window(a.shift, cand_date)
                if window.actual_start <= timestamp <= window.actual_end:
                    return window

        # Fallback to employee's default shift if defined
        emp = await self.employee_repo.get_by_id(employee_id)
        if emp and emp.shift_id:
            default_shift = await self.repo.get_by_id(emp.shift_id)
            if default_shift:
                for cand_date in candidate_dates:
                    window = self.get_shift_window(default_shift, cand_date)
                    if window.actual_start <= timestamp <= window.actual_end:
                        return window

        return None

    async def get_employee_shift_schedule(
        self,
        employee_id: int,
        for_timestamp: datetime | None = None,
    ) -> EmployeeShiftScheduleRead:
        ts = for_timestamp or now_ist()
        curr_window = await self.resolve_shift_for_timestamp(employee_id, ts)

        prev_window = None
        upcoming_window = None

        # Previous shift: look back 1 day
        prev_ts = ts - timedelta(days=1)
        prev_window = await self.resolve_shift_for_timestamp(employee_id, prev_ts)

        # Upcoming shift: look forward 1 day
        next_ts = ts + timedelta(days=1)
        upcoming_window = await self.resolve_shift_for_timestamp(employee_id, next_ts)

        return EmployeeShiftScheduleRead(
            employee_id=employee_id,
            current_shift=curr_window,
            previous_shift=prev_window,
            upcoming_shift=upcoming_window,
        )
