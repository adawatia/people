from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import PaginatedResponse
from db.models import (
    AttendanceCorrectionRequest,
    AttendancePunch,
    AttendanceRecord,
    Employee,
    LeaveApplication,
    WorkArrangementRequest,
    now_ist,
)
from repositories.attendance_punch_repo import AttendancePunchRepository
from repositories.attendance_record_repo import AttendanceRecordRepository
from repositories.employee_repo import EmployeeRepository
from schemas.attendance import (
    AttendanceCorrectionCreate,
    AttendanceCorrectionRead,
    AttendancePunchCreate,
    AttendancePunchRead,
    AttendanceRecordRead,
    AttendanceSummaryRead,
    BulkPunchCreate,
    ProcessAttendanceRequest,
    ProcessAttendanceResponse,
)
from services.holiday_service import HolidayService
from services.shift_service import ShiftService


class AttendanceService:
    """Turns raw punches into daily attendance records.

    Pipeline: device/web punches are ingested raw (`record_punch`), then the
    processing engine (`process_attendance_*`) resolves each punch to a
    shift window, computes worked time / late / overtime, and writes one
    AttendanceRecord per employee per day. Corrections flow through an
    approval workflow that rewrites the affected record.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.punch_repo = AttendancePunchRepository(session)
        self.record_repo = AttendanceRecordRepository(session)
        self.employee_repo = EmployeeRepository(session)
        self.shift_service = ShiftService(session)
        self.holiday_service = HolidayService(session)

    # ── Punch Ingestion ────────────────────────────────────────────────────────

    async def record_punch(self, data: AttendancePunchCreate) -> AttendancePunchRead:
        """Ingest a single raw punch (from biometric device, web, or ERP).

        Idempotent: duplicate pushes (same employee/time/type, or the same
        erp_event_id) return the existing punch instead of creating another.
        The matching shift window is resolved now and stored on the punch so
        later processing does not need to re-derive it.
        """
        emp: Employee | None = None
        if data.employee_id:
            emp = await self.employee_repo.get_by_id(data.employee_id)
        elif data.employee_code:
            emp = await self.employee_repo.get_by_code(data.employee_code)

        if not emp:
            ident = data.employee_id or data.employee_code
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee '{ident}' not found",
            )

        # Duplicate check (ignore duplicate biometric pushes within the same second)
        duplicate = await self.punch_repo.find_duplicate(
            employee_id=emp.id,
            punch_time=data.punch_time,
            punch_type=data.punch_type,
        )
        if data.erp_event_id:
            duplicate = (
                await self.session.scalar(
                    select(AttendancePunch).where(AttendancePunch.erp_event_id == data.erp_event_id)
                )
                or duplicate
            )
        if duplicate:
            return AttendancePunchRead.model_validate(duplicate)

        # Resolve shift for this punch timestamp
        shift_window = await self.shift_service.resolve_shift_for_timestamp(
            employee_id=emp.id,
            timestamp=data.punch_time,
        )

        punch = AttendancePunch(
            employee_id=emp.id,
            punch_time=data.punch_time,
            punch_type=data.punch_type.upper(),
            device_id=data.device_id,
            source=data.source.upper(),
            erp_event_id=data.erp_event_id,
            last_synced_at=now_ist() if data.erp_event_id else None,
            latitude=data.latitude,
            longitude=data.longitude,
            shift_id=shift_window.shift_id if shift_window else None,
            shift_start=shift_window.shift_start if shift_window else None,
            shift_end=shift_window.shift_end if shift_window else None,
            is_processed=False,
        )
        created = await self.punch_repo.create(punch)
        await self.session.commit()
        await self.session.refresh(created)
        return AttendancePunchRead.model_validate(created)

    async def record_bulk_punches(self, data: BulkPunchCreate) -> list[AttendancePunchRead]:
        """Ingest many punches at once; individual failures are skipped, not fatal.

        Biometric devices push batches that may contain unknown employees or
        duplicates — those entries are dropped silently so one bad row never
        blocks the rest of the sync.
        """
        results: list[AttendancePunchRead] = []
        for item in data.punches:
            try:
                res = await self.record_punch(item)
                results.append(res)
            except HTTPException:
                continue
        return results

    async def list_punches(
        self,
        employee_id: int | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        is_processed: bool | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[AttendancePunchRead]:
        punches = await self.punch_repo.list_punches(
            employee_id=employee_id,
            from_time=from_time,
            to_time=to_time,
            is_processed=is_processed,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        return [AttendancePunchRead.model_validate(p) for p in punches]

    # ── Daily Attendance Processing Engine ─────────────────────────────────────

    async def process_attendance_for_employee_date(
        self,
        employee: Employee,
        target_date: date,
    ) -> tuple[AttendanceRecord, bool]:
        """
        Processes attendance for a single employee on target_date:
        - Resolves shift assignments and cross-midnight windows.
        - Gathers punches within shift margins.
        - Calculates worked_minutes, overtime, late arrival, early exit.
        - Checks approved leave and holidays before marking absent.
        - Creates or updates AttendanceRecord.
        """
        existing_record = await self.record_repo.get_by_employee_and_date(employee.id, target_date)
        is_created = existing_record is None

        # ERP-finalized records are the source of truth and must not be replaced
        # by the local calculation pass.
        if existing_record and existing_record.sync_status == "ERP_CONFIRMED":
            return existing_record, False

        # 1. Resolve Shift
        assignments = await self.shift_service.repo.list_active_assignments_for_date(employee.id, target_date)
        shift = assignments[0].shift if assignments and assignments[0].shift else None
        if not shift and employee.shift_id:
            shift = await self.shift_service.repo.get_by_id(employee.shift_id)

        # 2. Gather Punches
        if shift:
            window = self.shift_service.get_shift_window(shift, target_date)
            punches = await self.punch_repo.list_punches(
                employee_id=employee.id,
                from_time=window.actual_start,
                to_time=window.actual_end,
            )
        else:
            window = None
            day_start = datetime.combine(target_date, time(0, 0, 0))
            day_end = datetime.combine(target_date, time(23, 59, 59))
            punches = await self.punch_repo.list_punches(
                employee_id=employee.id,
                from_time=day_start,
                to_time=day_end,
            )

        # 3. Check Holiday / Weekly Off
        is_hol_or_off, is_weekly_off, _ = await self.holiday_service.is_holiday_or_weekly_off(employee.id, target_date)

        # 4. Check Approved Leaves
        leave_stmt = select(LeaveApplication).where(
            LeaveApplication.employee_id == employee.id,
            LeaveApplication.status == "APPROVED",
            LeaveApplication.from_date <= target_date,
            LeaveApplication.to_date >= target_date,
        )
        leave_app = (await self.session.execute(leave_stmt)).scalars().first()

        # 4b. Check Approved Work Arrangements (WFH / OD / Field Work)
        wa_stmt = select(WorkArrangementRequest).where(
            WorkArrangementRequest.employee_id == employee.id,
            WorkArrangementRequest.status == "APPROVED",
            WorkArrangementRequest.from_date <= target_date,
            WorkArrangementRequest.to_date >= target_date,
        )
        work_arr = (await self.session.execute(wa_stmt)).scalars().first()

        # 5. Evaluate Status & Times
        punch_in_val: time | None = None
        punch_out_val: time | None = None
        worked_minutes = 0
        overtime_minutes = 0
        late_minutes = 0
        early_exit_minutes = 0
        status_val: str

        if punches:
            in_punches = [p for p in punches if p.punch_type == "IN"]
            out_punches = [p for p in punches if p.punch_type == "OUT"]

            first_in = min((p.punch_time for p in in_punches), default=None)
            if not first_in:
                first_in = min((p.punch_time for p in punches), default=None)

            last_out = max((p.punch_time for p in out_punches), default=None)
            if not last_out and len(punches) > 1:
                last_out = max((p.punch_time for p in punches), default=None)

            if first_in:
                if first_in.tzinfo is not None:
                    # Convert to India wall-clock, then drop the tzinfo so the
                    # result compares cleanly against the shift's naive window.
                    first_in = ShiftService._local_naive(first_in)
                punch_in_val = first_in.time()

            if last_out:
                if last_out.tzinfo is not None:
                    last_out = ShiftService._local_naive(last_out)

            if last_out and first_in and last_out > first_in:
                punch_out_val = last_out.time()
                total_span_minutes = int((last_out - first_in).total_seconds() / 60)
                break_min = shift.break_minutes if (shift and total_span_minutes > shift.break_minutes) else 0
                worked_minutes = max(0, total_span_minutes - break_min)
                worked_hours = worked_minutes / 60.0

                # Thresholds (shift-specific when configured, else sane defaults):
                # below absent_th the employee essentially did not work a day;
                # below half_day_th they worked, but not a full day.
                absent_th = float(shift.absent_threshold_hours) if shift else 2.0
                half_day_th = float(shift.half_day_threshold_hours) if shift else 4.0

                if worked_hours < absent_th:
                    status_val = "ABSENT"
                elif worked_hours < half_day_th:
                    status_val = "HALF_DAY"
                else:
                    status_val = "PRESENT"

                # Late check
                if shift and window:
                    late_cutoff = window.shift_start + timedelta(minutes=shift.late_entry_grace_minutes)
                    if first_in > late_cutoff:
                        late_minutes = max(0, int((first_in - window.shift_start).total_seconds() / 60))

                # Early exit check
                if shift and window:
                    early_cutoff = window.shift_end - timedelta(minutes=shift.early_exit_grace_minutes)
                    if last_out < early_cutoff:
                        early_exit_minutes = max(0, int((window.shift_end - last_out).total_seconds() / 60))

                # Overtime check
                if shift and window:
                    scheduled_minutes = (
                        int((window.shift_end - window.shift_start).total_seconds() / 60) - shift.break_minutes
                    )
                    if worked_minutes > scheduled_minutes:
                        overtime_minutes = worked_minutes - scheduled_minutes
            else:
                # Exactly one punch in the window: we can tell when they
                # arrived or left, but not both — flag for manual correction.
                status_val = "MISSED_PUNCH"
                worked_minutes = 0

        else:
            # No punches at all — fall through the exemption ladder:
            # approved leave beats WFH/OD, which beats holiday/weekly off.
            if leave_app:
                status_val = "ON_LEAVE"
            elif work_arr:
                # On-duty/field work counts as a full standard day (480 min);
                # plain WFH shows no worked time unless punches exist.
                status_val = "WORK_FROM_HOME" if work_arr.arrangement_type == "WORK_FROM_HOME" else "PRESENT"
                worked_minutes = 480 if status_val == "PRESENT" else 0
            elif is_hol_or_off:
                status_val = "WEEKLY_OFF" if is_weekly_off else "HOLIDAY"
            else:
                status_val = "ABSENT"

        # 6. Persist AttendanceRecord
        if existing_record:
            record = existing_record
            record.status = status_val
            record.punch_in = punch_in_val
            record.punch_out = punch_out_val
            record.worked_minutes = worked_minutes
            record.overtime_minutes = overtime_minutes
            record.late_minutes = late_minutes
            record.early_exit_minutes = early_exit_minutes
            record.shift_id = shift.id if shift else None
        else:
            record = AttendanceRecord(
                employee_id=employee.id,
                attendance_date=target_date,
                shift_id=shift.id if shift else None,
                status=status_val,
                punch_in=punch_in_val,
                punch_out=punch_out_val,
                worked_minutes=worked_minutes,
                overtime_minutes=overtime_minutes,
                late_minutes=late_minutes,
                early_exit_minutes=early_exit_minutes,
                source="HRMS",
            )
            record = await self.record_repo.create(record)

        # Mark punches processed and linked so they are not consumed again
        # by a later processing run.
        for p in punches:
            p.attendance_record_id = record.id
            p.is_processed = True

        return record, is_created

    async def process_attendance_batch(
        self,
        req: ProcessAttendanceRequest,
    ) -> ProcessAttendanceResponse:
        """
        Executes attendance processing across employees and dates.
        """
        if req.to_date < req.from_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_date must be greater than or equal to from_date",
            )

        employees: list[Employee] = []
        if req.employee_id:
            emp = await self.employee_repo.get_by_id(req.employee_id)
            if emp:
                employees = [emp]
        else:
            employees = await self.employee_repo.list_employees(
                unit_id=req.unit_id,
                status="ACTIVE",
                page_size=1000,
            )

        total_processed = 0
        created_count = 0
        updated_count = 0

        curr_date = req.from_date
        while curr_date <= req.to_date:
            for emp in employees:
                _, created = await self.process_attendance_for_employee_date(emp, curr_date)
                total_processed += 1
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            curr_date += timedelta(days=1)

        await self.session.commit()

        return ProcessAttendanceResponse(
            message="Attendance batch processing completed successfully",
            from_date=req.from_date,
            to_date=req.to_date,
            processed_records=total_processed,
            created_records=created_count,
            updated_records=updated_count,
        )

    # ── Attendance Correction Workflow ─────────────────────────────────────────

    async def submit_correction(
        self,
        data: AttendanceCorrectionCreate,
    ) -> AttendanceCorrectionRead:
        record = await self.record_repo.get_by_id(data.attendance_record_id)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found",
            )

        def parse_str_time(t: str | None) -> time | None:
            """Parse the 'HH:MM' strings submitted by the correction form."""
            if not t:
                return None
            try:
                parts = t.strip().split(":")
                if len(parts) != 2:
                    raise ValueError
                return time(int(parts[0]), int(parts[1]))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="Time must use HH:MM format") from exc

        requested_in = parse_str_time(data.requested_punch_in)
        requested_out = parse_str_time(data.requested_punch_out)
        if requested_in is None and requested_out is None:
            raise HTTPException(status_code=400, detail="At least one corrected punch time is required")
        if requested_in and requested_out and requested_out <= requested_in:
            raise HTTPException(status_code=400, detail="Punch-out time must be later than punch-in time")

        existing = await self.session.scalar(
            select(AttendanceCorrectionRequest).where(
                AttendanceCorrectionRequest.attendance_record_id == record.id,
                AttendanceCorrectionRequest.status == "PENDING",
            )
        )
        if existing:
            raise HTTPException(
                status_code=409, detail="A correction request is already pending for this attendance record"
            )

        correction = AttendanceCorrectionRequest(
            attendance_record_id=record.id,
            requested_punch_in=requested_in,
            requested_punch_out=requested_out,
            reason=data.reason,
            status="PENDING",
            erp_correction_id=data.erp_correction_id,
            sync_status="PENDING_ERP_RECONCILIATION",
        )
        created = await self.record_repo.create_correction(correction)
        await self.session.commit()
        await self.session.refresh(created)
        return AttendanceCorrectionRead.model_validate(created)

    async def approve_correction(
        self,
        correction_id: int,
        actioned_by_user_id: int,
    ) -> AttendanceCorrectionRead:
        correction = await self.record_repo.get_correction_by_id_for_update(correction_id)
        if not correction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correction request not found")
        if correction.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Correction is not in PENDING state")

        # Self-approval prevention
        record = await self.record_repo.get_by_id(correction.attendance_record_id)
        if record:
            emp = await self.employee_repo.get_by_id(record.employee_id)
            if emp and emp.user_id == actioned_by_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Approvers cannot act on their own attendance corrections",
                )

        correction.status = "APPROVED"
        correction.actioned_by = actioned_by_user_id
        correction.actioned_at = now_ist()

        # Update attendance record: apply the corrected times and recompute
        # worked minutes. Status is simply PRESENT — a human approver has
        # confirmed the employee did attend; threshold logic does not re-run.
        if record:
            if correction.requested_punch_in:
                record.punch_in = correction.requested_punch_in
            if correction.requested_punch_out:
                record.punch_out = correction.requested_punch_out

            if record.punch_in and record.punch_out:
                start_dt = datetime.combine(record.attendance_date, record.punch_in)
                end_dt = datetime.combine(record.attendance_date, record.punch_out)
                if end_dt > start_dt:
                    total_min = int((end_dt - start_dt).total_seconds() / 60)
                    record.worked_minutes = max(0, total_min)
                    record.status = "PRESENT"
                else:
                    record.status = "PRESENT"
            else:
                record.status = "PRESENT"

        await self.session.commit()
        await self.session.refresh(correction)
        return AttendanceCorrectionRead.model_validate(correction)

    async def reject_correction(
        self,
        correction_id: int,
        actioned_by_user_id: int,
        rejection_reason: str | None = None,
    ) -> AttendanceCorrectionRead:
        correction = await self.record_repo.get_correction_by_id_for_update(correction_id)
        if not correction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correction request not found")
        if correction.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Correction is not in PENDING state")

        # Self-approval prevention
        record = await self.record_repo.get_by_id(correction.attendance_record_id)
        if record:
            emp = await self.employee_repo.get_by_id(record.employee_id)
            if emp and emp.user_id == actioned_by_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Approvers cannot act on their own attendance corrections",
                )

        correction.status = "REJECTED"
        correction.actioned_by = actioned_by_user_id
        correction.actioned_at = now_ist()
        correction.rejection_reason = rejection_reason
        await self.session.commit()
        await self.session.refresh(correction)
        return AttendanceCorrectionRead.model_validate(correction)

    # ── Attendance Query Operations ────────────────────────────────────────────

    async def list_attendance(
        self,
        employee_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 50,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[AttendanceRecordRead]:
        records = await self.record_repo.list_records(
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
            status=status_filter,
            page=page,
            page_size=page_size,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        return [AttendanceRecordRead.model_validate(r) for r in records]

    async def list_attendance_page(
        self,
        employee_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> PaginatedResponse[AttendanceRecordRead]:
        if from_date and to_date and from_date > to_date:
            raise HTTPException(422, "Start date must not be after end date")
        result = await self.record_repo.list_records_page(
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
            status=status_filter,
            page=page,
            page_size=page_size,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        pending_ids = await self.record_repo.pending_correction_ids([r.id for r in result["items"]])
        items = [
            AttendanceRecordRead.model_validate(r).model_copy(update={"has_pending_correction": r.id in pending_ids})
            for r in result["items"]
        ]

        return PaginatedResponse[AttendanceRecordRead](**dict(result, items=items))

    async def get_attendance_record(self, record_id: int) -> AttendanceRecordRead:
        record = await self.record_repo.get_by_id(record_id)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attendance record with ID {record_id} not found",
            )
        return AttendanceRecordRead.model_validate(record)

    async def get_employee_calendar(
        self,
        emp_id: int,
        year: int,
        month: int,
    ) -> list[AttendanceRecordRead]:
        from_date = date(year, month, 1)
        if month == 12:
            to_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(year, month + 1, 1) - timedelta(days=1)

        records = await self.record_repo.get_month_records(emp_id, from_date, to_date)
        pending_ids = await self.record_repo.pending_correction_ids([r.id for r in records])
        return [
            AttendanceRecordRead.model_validate(r).model_copy(update={"has_pending_correction": r.id in pending_ids})
            for r in records
        ]

    async def get_attendance_summary(
        self,
        emp_id: int,
        year: int,
        month: int,
    ) -> AttendanceSummaryRead:
        from_date = date(year, month, 1)
        if month == 12:
            to_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(year, month + 1, 1) - timedelta(days=1)

        records = await self.record_repo.get_month_records(emp_id, from_date, to_date)

        total_working_days = sum(1 for r in records if r.status not in ("WEEKLY_OFF", "HOLIDAY"))
        summary = AttendanceSummaryRead(
            employee_id=emp_id,
            month=month,
            year=year,
            total_working_days=total_working_days,
            total_present=sum(1 for r in records if r.status == "PRESENT"),
            total_absent=sum(1 for r in records if r.status == "ABSENT"),
            total_leave=sum(1 for r in records if r.status == "ON_LEAVE"),
            total_half_day=sum(1 for r in records if r.status == "HALF_DAY"),
            total_holiday=sum(1 for r in records if r.status == "HOLIDAY"),
            total_weekly_off=sum(1 for r in records if r.status == "WEEKLY_OFF"),
            total_late=sum(1 for r in records if r.status == "LATE" or (r.late_minutes and r.late_minutes > 0)),
            total_early_exit=sum(1 for r in records if r.early_exit_minutes and r.early_exit_minutes > 0),
            total_missed_punch=sum(1 for r in records if r.status == "MISSED_PUNCH"),
            total_overtime_minutes=sum(r.overtime_minutes for r in records),
        )
        present = summary.total_present + sum(1 for r in records if r.status == "HALF_DAY") * 0.5
        if total_working_days > 0:
            summary.attendance_percentage = round(present / total_working_days * 100, 1)
        return summary

    async def list_corrections(
        self,
        status: str | None = None,
        employee_id: int | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[AttendanceCorrectionRead]:
        corrections = await self.record_repo.list_corrections(
            status=status,
            employee_id=employee_id,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        return [AttendanceCorrectionRead.model_validate(c) for c in corrections]

    async def list_corrections_page(
        self,
        status: str | None = None,
        employee_id: int | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> PaginatedResponse[AttendanceCorrectionRead]:
        result = await self.record_repo.list_corrections_page(
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            status=status,
            employee_id=employee_id,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        items = [AttendanceCorrectionRead.model_validate(c) for c in result["items"]]

        return PaginatedResponse[AttendanceCorrectionRead](**dict(result, items=items))

    async def list_punches_page(self, **filters):
        return await self.punch_repo.list_punches_page(**filters)
