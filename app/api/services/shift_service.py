from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.erp_sync import acquire_erp_upsert_lock
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


@dataclass
class ShiftScheduleContext:
    """In-memory shift-resolution context for one employee over a date range.

    ``load_schedule_context`` fills this from a single batched query, after
    which per-date and per-timestamp window resolution is pure computation.
    """

    start_date: date
    end_date: date
    assignments: list[ShiftAssignment]
    default_shift: Shift | None

    def assignments_for_date(self, target: date) -> list[ShiftAssignment]:
        """Active assignments effective on ``target``, newest first."""
        if not (self.start_date <= target <= self.end_date):
            return []
        return [
            assignment
            for assignment in self.assignments
            if assignment.effective_from <= target
            and (assignment.effective_to is None or assignment.effective_to >= target)
        ]

    def dates(self) -> list[date]:
        """Every calendar date covered by the context, in order."""
        day_count = (self.end_date - self.start_date).days + 1
        return [self.start_date + timedelta(days=offset) for offset in range(day_count)]


class ShiftService:
    """Shift definitions, employee assignments and punch-to-shift matching.

    The trickiest concept here is the "shift window": a shift on calendar
    date D starts at its configured start_time on D and ends at end_time —
    on D+1 when it crosses midnight (night shift). Check-in/check-out buffer
    margins extend the window so punches slightly outside the shift still
    match it.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ShiftRepository(session)
        self.employee_repo = EmployeeRepository(session)

    @staticmethod
    def _local_naive(value: datetime) -> datetime:
        """Convert an incoming timestamp to the application's India wall-clock time."""
        if value.tzinfo is not None:
            value = value.astimezone(ZoneInfo("Asia/Kolkata"))
            return value.replace(tzinfo=None)
        return value

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
        """Create a shift; start > end (e.g. 22:00 → 06:00) means a night shift."""
        payload = self._shift_payload(data)
        shift = Shift(**payload)
        created = await self.repo.create_shift(shift)
        await self.session.commit()
        await self.session.refresh(created)
        return ShiftRead.model_validate(created)

    def _shift_payload(self, data: ShiftCreate) -> dict:
        start = self.parse_time(data.start_time)
        end = self.parse_time(data.end_time)
        if start == end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift start time and end time cannot be identical",
            )

        # start_time > end_time is the convention for a shift that crosses
        # midnight; get_shift_window uses this to push the end into the next day.
        is_cross_midnight = start > end
        payload = data.model_dump()
        payload["start_time"] = start
        payload["end_time"] = end
        payload["is_cross_midnight"] = is_cross_midnight
        return payload

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

    async def upsert_shift(self, erp_id: str, data: ShiftCreate) -> ShiftRead:
        await acquire_erp_upsert_lock(self.session, "shift", erp_id)
        shift = await self.repo.get_by_erp_id(erp_id)
        if shift is None:
            shift = Shift(erp_id=erp_id, **self._shift_payload(data))
            await self.repo.create_shift(shift)
        else:
            payload = self._shift_payload(data)
            for key, value in payload.items():
                setattr(shift, key, value)
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
            r.start_time = (
                assignment.shift.start_time.strftime("%H:%M")
                if hasattr(assignment.shift.start_time, "strftime")
                else str(assignment.shift.start_time)
            )
            r.end_time = (
                assignment.shift.end_time.strftime("%H:%M")
                if hasattr(assignment.shift.end_time, "strftime")
                else str(assignment.shift.end_time)
            )
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

        # Overlap check: an employee may hold only one shift assignment at a
        # time — two active windows would make punch resolution ambiguous.
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
        # Backfill the employee's default shift so punches outside any
        # assignment window still have a sensible fallback.
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
            # Bulk assignment closes overlapping assignments instead of
            # failing: HR reassigning a whole department should succeed.
            overlap = await self.repo.find_overlapping_assignment(
                employee_id=emp_id,
                effective_from=data.effective_from,
                effective_to=data.effective_to,
            )
            if overlap:
                if overlap.effective_from < data.effective_from:
                    # Existing assignment started earlier: end it the day
                    # before the new one begins, preserving its history.
                    overlap.effective_to = data.effective_from - timedelta(days=1)
                else:
                    # Existing assignment starts inside the new period:
                    # deactivate it entirely in favour of the new shift.
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
        """Calculates actual start and end timestamps for a shift on a given calendar date.

        For a night shift (start 22:00, end 06:00) on D, the end lands on D+1.
        `actual_start`/`actual_end` add the check-in/check-out buffers, giving
        the range in which a punch is attributed to this shift.
        """
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
        # Shift windows are deliberately represented as local wall-clock values
        # because the company operates in India. Normalize aware API timestamps
        # before comparing them with those windows.
        naive_ts = self._local_naive(timestamp)
        check_date = naive_ts.date()
        # A punch at 01:00 may belong to the previous day's night shift, and a
        # punch just before a shift may belong to tomorrow's — so the context
        # covers yesterday, today, and tomorrow in one batched query.
        context = await self.load_schedule_context(
            employee_id,
            start_date=check_date - timedelta(days=1),
            end_date=check_date + timedelta(days=1),
        )
        return self._window_for_timestamp(context, naive_ts)

    async def get_shift_window_for_date(
        self,
        employee_id: int,
        shift_date: date,
    ) -> ShiftWindowDetail | None:
        """Return the employee's effective scheduled shift for a calendar date.

        A dated assignment takes precedence over the employee's ERP-synchronised
        default shift.  Unlike ``resolve_shift_for_timestamp``, this method does
        not require the current time to be inside the check-in/out window, so it
        is suitable for displaying an assigned or future shift.
        """
        context = await self.load_schedule_context(employee_id, shift_date)
        return self._window_for_date(context, shift_date)

    async def get_employee_shift_schedule(
        self,
        employee_id: int,
        for_timestamp: datetime | None = None,
    ) -> EmployeeShiftScheduleRead:
        """Resolve previous/current/upcoming shift windows for an employee.

        All dated assignments for the whole window (yesterday through the
        15-day upcoming horizon) are fetched in a single query; the rest is
        pure in-memory window math. The upcoming search looks for the next
        scheduled *start* after now rather than checking the same clock time
        tomorrow, which previously missed ordinary day shifts after working
        hours and left the employee dashboard empty.
        """
        ts = for_timestamp or now_ist()
        local_ts = self._local_naive(ts)
        today = local_ts.date()

        context = await self.load_schedule_context(
            employee_id,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=14),
        )
        previous_shift = self._window_for_date(context, today - timedelta(days=1))
        assigned_shift = self._window_for_date(context, today)

        # A punch "now" only counts as the current shift when it falls inside
        # a shift's actual (buffered) window — otherwise the next start wins.
        curr_window = self._window_for_timestamp(context, local_ts)
        upcoming_window = None
        for offset in range(15):
            candidate = self._window_for_date(context, today + timedelta(days=offset))
            if candidate and candidate.shift_start > local_ts:
                upcoming_window = candidate
                break

        return EmployeeShiftScheduleRead(
            employee_id=employee_id,
            assigned_shift=assigned_shift,
            current_shift=curr_window,
            previous_shift=previous_shift,
            upcoming_shift=upcoming_window,
        )

    async def load_schedule_context(
        self,
        employee_id: int,
        start_date: date,
        end_date: date | None = None,
    ) -> ShiftScheduleContext:
        """Load everything needed to resolve shift windows for a date range.

        One query returns every active assignment overlapping the range (with
        the shift rows eagerly loaded) plus the employee's default shift and
        one shared copy of that default's unbuffered window. Callers then
        resolve windows purely in memory instead of issuing per-date queries.
        """
        end_date = end_date or start_date
        assignments = await self.repo.list_active_assignments_between(employee_id, start_date, end_date)
        employee = await self.employee_repo.get_by_id(employee_id)
        default_shift = None
        if employee and employee.shift_id:
            default_shift = await self.repo.get_by_id(employee.shift_id)
        return ShiftScheduleContext(
            start_date=start_date,
            end_date=end_date,
            assignments=assignments,
            default_shift=default_shift,
        )

    @classmethod
    def _window_for_date(cls, context: ShiftScheduleContext, shift_date: date) -> ShiftWindowDetail | None:
        """Resolve the effective scheduled shift on a calendar date from a loaded context.

        A dated assignment wins over the employee's default shift. Outside the
        loaded range the default shift is the only sensible answer; within the
        range an absent assignment still falls back to the default, matching
        the behaviour before batching.
        """
        if context.start_date <= shift_date <= context.end_date:
            for assignment in context.assignments_for_date(shift_date):
                if assignment.shift and assignment.shift.is_active:
                    return cls.get_shift_window(assignment.shift, shift_date)
        if context.default_shift and context.default_shift.is_active:
            return cls.get_shift_window(context.default_shift, shift_date)
        return None

    @classmethod
    def _window_for_timestamp(cls, context: ShiftScheduleContext, timestamp: datetime) -> ShiftWindowDetail | None:
        """Find the buffered shift window that contains a timestamp, if any.

        A punch at 01:00 may belong to the previous day's night shift, and a
        punch just before a shift may belong to tomorrow's — so every date in
        the loaded context is considered. Dated assignments win over the
        default shift across all dates; the default is the final fallback.
        """
        for shift_date in context.dates():
            for assignment in context.assignments_for_date(shift_date):
                if assignment.shift and assignment.shift.is_active:
                    window = cls.get_shift_window(assignment.shift, shift_date)
                    if window.actual_start <= timestamp <= window.actual_end:
                        return window
        if context.default_shift and context.default_shift.is_active:
            for shift_date in context.dates():
                window = cls.get_shift_window(context.default_shift, shift_date)
                if window.actual_start <= timestamp <= window.actual_end:
                    return window
        return None

    async def assignments_page(self, scope, **filters):
        page = await self.repo.assignments_page(scope, **filters)
        page["items"] = [self.to_assignment_read(assignment) for assignment in page["items"]]
        return page

    async def definitions_page(self, **filters):
        return await self.repo.definitions_page(**filters)
