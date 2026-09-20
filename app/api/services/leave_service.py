from datetime import date, datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AttendanceRecord,
    LeaveAllocation,
    LeaveApplication,
    LeaveLedgerEntry,
    LeavePeriod,
    LeaveType,
)
from repositories.attendance_record_repo import AttendanceRecordRepository
from repositories.employee_repo import EmployeeRepository
from repositories.leave_repo import LeaveRepository
from schemas.leaves import (
    LeaveAllocationCreate,
    LeaveAllocationRead,
    LeaveApplicationAction,
    LeaveApplicationCreate,
    LeaveApplicationRead,
    LeaveBalanceRead,
    LeavePeriodCreate,
    LeavePeriodRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
)
from services.holiday_service import HolidayService


class LeaveService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LeaveRepository(session)
        self.employee_repo = EmployeeRepository(session)
        self.holiday_service = HolidayService(session)
        self.attendance_record_repo = AttendanceRecordRepository(session)

    # ── Leave Periods ──────────────────────────────────────────────────────────

    async def create_period(self, data: LeavePeriodCreate) -> LeavePeriodRead:
        if data.to_date < data.from_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_date must be greater than or equal to from_date",
            )
        period = LeavePeriod(**data.model_dump())
        created = await self.repo.create_period(period)
        await self.session.commit()
        await self.session.refresh(created)
        return LeavePeriodRead.model_validate(created)

    async def list_periods(self) -> list[LeavePeriodRead]:
        periods = await self.repo.list_periods()
        return [LeavePeriodRead.model_validate(p) for p in periods]

    # ── Leave Types ────────────────────────────────────────────────────────────

    async def create_type(self, data: LeaveTypeCreate) -> LeaveTypeRead:
        existing = await self.repo.get_type_by_code(data.code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Leave type code '{data.code}' already exists",
            )
        leave_type = LeaveType(**data.model_dump())
        leave_type.code = leave_type.code.strip().upper()
        created = await self.repo.create_type(leave_type)
        await self.session.commit()
        await self.session.refresh(created)
        return LeaveTypeRead.model_validate(created)

    async def list_types(self, is_active: bool | None = None) -> list[LeaveTypeRead]:
        types = await self.repo.list_types(is_active=is_active)
        return [LeaveTypeRead.model_validate(t) for t in types]

    async def get_type(self, type_id: int) -> LeaveType:
        lt = await self.repo.get_type_by_id(type_id)
        if not lt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Leave type with ID {type_id} not found",
            )
        return lt

    async def update_type(self, type_id: int, data: LeaveTypeUpdate) -> LeaveTypeRead:
        lt = await self.get_type(type_id)
        update_data = data.model_dump(exclude_unset=True)
        if "code" in update_data and update_data["code"]:
            update_data["code"] = update_data["code"].strip().upper()
            existing = await self.repo.get_type_by_code(update_data["code"])
            if existing and existing.id != type_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Leave type code '{update_data['code']}' already exists",
                )
        for key, val in update_data.items():
            setattr(lt, key, val)
        await self.session.commit()
        await self.session.refresh(lt)
        return LeaveTypeRead.model_validate(lt)

    # ── Leave Allocations & Ledger ─────────────────────────────────────────────

    async def allocate_leaves(self, data: LeaveAllocationCreate) -> LeaveAllocationRead:
        emp = await self.employee_repo.get_by_id(data.employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        leave_type = await self.get_type(data.leave_type_id)
        period = await self.repo.get_period_by_id(data.leave_period_id)
        if not period:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave period not found")

        existing = await self.repo.find_allocation(data.employee_id, data.leave_type_id, data.leave_period_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leaves have already been allocated to this employee for this period",
            )

        total = float(data.new_leaves_allocated + data.carry_forwarded_leaves)
        alloc = LeaveAllocation(
            employee_id=data.employee_id,
            leave_type_id=data.leave_type_id,
            leave_period_id=data.leave_period_id,
            new_leaves_allocated=data.new_leaves_allocated,
            carry_forwarded_leaves=data.carry_forwarded_leaves,
            total_leaves_allocated=total,
            notes=data.notes,
        )
        created_alloc = await self.repo.create_allocation(alloc)

        # Credit double-entry ledger
        credit_entry = LeaveLedgerEntry(
            employee_id=data.employee_id,
            leave_type_id=data.leave_type_id,
            transaction_type="ALLOCATION",
            transaction_id=created_alloc.id,
            leaves=total,
            from_date=period.from_date,
            to_date=period.to_date,
            is_carry_forward=data.carry_forwarded_leaves > 0,
            is_expired=False,
        )
        await self.repo.create_ledger_entry(credit_entry)

        await self.session.commit()
        refreshed = await self.repo.get_allocation(created_alloc.id)
        read_obj = LeaveAllocationRead.model_validate(refreshed)
        if refreshed:
            if refreshed.employee:
                read_obj.employee_name = f"{refreshed.employee.first_name} {refreshed.employee.last_name or ''}".strip()
                read_obj.employee_code = refreshed.employee.employee_code
            if refreshed.leave_type:
                read_obj.leave_type_name = refreshed.leave_type.name
            if refreshed.leave_period:
                read_obj.leave_period_name = refreshed.leave_period.name
        return read_obj

    async def list_allocations(
        self,
        employee_id: int | None = None,
        leave_period_id: int | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[LeaveAllocationRead]:
        allocs = await self.repo.list_allocations(
            employee_id=employee_id,
            leave_period_id=leave_period_id,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        reads = []
        for a in allocs:
            r = LeaveAllocationRead.model_validate(a)
            if a.employee:
                r.employee_name = f"{a.employee.first_name} {a.employee.last_name or ''}".strip()
                r.employee_code = a.employee.employee_code
            if a.leave_type:
                r.leave_type_name = a.leave_type.name
            if a.leave_period:
                r.leave_period_name = a.leave_period.name
            reads.append(r)
        return reads

    async def get_employee_leave_balances(
        self,
        employee_id: int,
        for_date: date | None = None,
    ) -> list[LeaveBalanceRead]:
        target_date = for_date or date.today()
        balances = await self.repo.list_balances(employee_id, target_date.year)
        results: list[LeaveBalanceRead] = []
        for balance in balances:
            lt = balance.leave_type
            results.append(
                LeaveBalanceRead(
                    employee_id=employee_id,
                    leave_type_id=lt.id,
                    leave_type_name=lt.name,
                    leave_type_code=lt.code,
                    allocated=float(balance.allocated),
                    used=float(balance.used),
                    pending=float(balance.pending),
                    available=max(0.0, float(balance.allocated) - float(balance.used) - float(balance.pending)),
                )
            )

        return results

    # ── Leave Application Workflow ─────────────────────────────────────────────

    async def calculate_leave_days(
        self,
        employee_id: int,
        leave_type: LeaveType,
        from_date: date,
        to_date: date,
        half_day: bool = False,
    ) -> float:
        if half_day:
            return 0.5

        if leave_type.include_holidays:
            return float((to_date - from_date).days + 1)

        # Exclude holidays and weekly offs
        holidays_set = await self.holiday_service.get_holidays_in_range(
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
            skip_weekly_offs=False,
        )

        effective_days = 0
        curr = from_date
        while curr <= to_date:
            if curr not in holidays_set:
                effective_days += 1
            curr += timedelta(days=1)

        return float(effective_days)

    async def apply_leave(self, data: LeaveApplicationCreate) -> LeaveApplicationRead:
        if data.to_date < data.from_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_date must be greater than or equal to from_date",
            )

        emp = await self.employee_repo.get_by_id(data.employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        leave_type = await self.get_type(data.leave_type_id)

        # Overlap check
        overlap = await self.repo.find_overlapping_application(
            employee_id=data.employee_id,
            from_date=data.from_date,
            to_date=data.to_date,
        )
        if overlap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee already has a pending or approved leave overlapping with these dates",
            )

        period = await self.repo.get_active_period_for_date(data.from_date)
        period_id = period.id if period else None

        days_count = await self.calculate_leave_days(
            employee_id=data.employee_id,
            leave_type=leave_type,
            from_date=data.from_date,
            to_date=data.to_date,
            half_day=data.half_day,
        )
        if days_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected date range falls entirely on non-working holidays/weekly offs",
            )

        if leave_type.max_consecutive_days and days_count > leave_type.max_consecutive_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested leave of {days_count} days exceeds maximum consecutive allowed ({leave_type.max_consecutive_days} days)",
            )

        app = LeaveApplication(
            employee_id=data.employee_id,
            leave_type_id=data.leave_type_id,
            leave_period_id=period_id,
            from_date=data.from_date,
            to_date=data.to_date,
            half_day=data.half_day,
            half_day_date=data.half_day_date if data.half_day else None,
            days_count=days_count,
            reason=data.reason,
            status="PENDING",
        )
        created = await self.repo.create_application(app)
        await self.session.commit()
        refreshed = await self.repo.get_application_by_id(created.id)
        read_obj = LeaveApplicationRead.model_validate(refreshed)
        read_obj.leave_type_name = leave_type.name
        read_obj.leave_type_code = leave_type.code
        if refreshed and refreshed.employee:
            read_obj.employee_name = f"{refreshed.employee.first_name} {refreshed.employee.last_name or ''}".strip()
            read_obj.employee_code = refreshed.employee.employee_code
        return read_obj

    async def get_application(self, application_id: int) -> LeaveApplicationRead:
        app = await self.repo.get_application_by_id(application_id)
        if not app:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave application not found")
        read_obj = LeaveApplicationRead.model_validate(app)
        if app.leave_type:
            read_obj.leave_type_name = app.leave_type.name
            read_obj.leave_type_code = app.leave_type.code
        if app.employee:
            read_obj.employee_name = f"{app.employee.first_name} {app.employee.last_name or ''}".strip()
            read_obj.employee_code = app.employee.employee_code
        return read_obj

    async def approve_leave(
        self,
        application_id: int,
        actioned_by_user_id: int,
    ) -> LeaveApplicationRead:
        app = await self.repo.get_application_by_id(application_id)
        if not app:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave application not found")
        if app.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Application is not in PENDING state")

        # Self-approval prevention
        emp = await self.employee_repo.get_by_id(app.employee_id)
        if emp and emp.user_id == actioned_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approvers cannot approve their own leave applications",
            )

        # Cache relationship data before any commit/expire
        leave_type_name = app.leave_type.name if app.leave_type else ""
        leave_type_code = app.leave_type.code if app.leave_type else ""
        include_holidays = app.leave_type.include_holidays if app.leave_type else False
        app_employee_id = app.employee_id
        app_from_date = app.from_date
        app_to_date = app.to_date
        app_half_day = app.half_day
        app_days_count = float(app.days_count)
        app_leave_type_id = app.leave_type_id
        app_id = app.id

        app.status = "APPROVED"
        app.erp_event_id = f"LEAVE-{app.id}-APPROVED"
        app.erp_sync_status = "PENDING"
        app.actioned_by = actioned_by_user_id
        app.actioned_at = datetime.now()

        # Debit double-entry ledger
        debit_entry = LeaveLedgerEntry(
            employee_id=app_employee_id,
            leave_type_id=app_leave_type_id,
            transaction_type="APPLICATION",
            transaction_id=app_id,
            leaves=-app_days_count,  # Debit
            from_date=app_from_date,
            to_date=app_to_date,
            is_carry_forward=False,
            is_expired=False,
        )
        await self.repo.create_ledger_entry(debit_entry)

        # Update or create AttendanceRecord for the approved days
        holidays_set: set = set()
        if not include_holidays:
            holidays_set = await self.holiday_service.get_holidays_in_range(
                employee_id=app_employee_id,
                from_date=app_from_date,
                to_date=app_to_date,
            )

        curr = app_from_date
        while curr <= app_to_date:
            if curr not in holidays_set:
                rec = await self.attendance_record_repo.get_by_employee_and_date(app_employee_id, curr)
                status_to_set = "HALF_DAY" if app_half_day else "ON_LEAVE"
                if rec:
                    rec.status = status_to_set
                else:
                    new_rec = AttendanceRecord(
                        employee_id=app_employee_id,
                        attendance_date=curr,
                        status=status_to_set,
                        worked_minutes=0,
                        late_minutes=0,
                        early_exit_minutes=0,
                        overtime_minutes=0,
                    )
                    await self.attendance_record_repo.create(new_rec)
            curr += timedelta(days=1)

        await self.session.commit()
        refreshed = await self.repo.get_application_by_id(app_id)
        read_obj = LeaveApplicationRead.model_validate(refreshed)
        read_obj.leave_type_name = leave_type_name
        read_obj.leave_type_code = leave_type_code
        if refreshed and refreshed.employee:
            read_obj.employee_name = f"{refreshed.employee.first_name} {refreshed.employee.last_name or ''}".strip()
            read_obj.employee_code = refreshed.employee.employee_code
        return read_obj

    async def reject_leave(
        self,
        application_id: int,
        actioned_by_user_id: int,
        rejection_reason: str | None = None,
    ) -> LeaveApplicationRead:
        app = await self.repo.get_application_by_id(application_id)
        if not app:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave application not found")
        if app.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Application is not in PENDING state")

        # Cache relationship data before commit/expire
        leave_type_name = app.leave_type.name if app.leave_type else ""
        leave_type_code = app.leave_type.code if app.leave_type else ""
        app_id = app.id

        app.status = "REJECTED"
        app.erp_event_id = f"LEAVE-{app.id}-REJECTED"
        app.erp_sync_status = "PENDING"
        app.actioned_by = actioned_by_user_id
        app.actioned_at = datetime.now()
        app.rejection_reason = rejection_reason
        await self.session.commit()
        refreshed = await self.repo.get_application_by_id(app_id)
        read_obj = LeaveApplicationRead.model_validate(refreshed)
        read_obj.leave_type_name = leave_type_name
        read_obj.leave_type_code = leave_type_code
        if refreshed and refreshed.employee:
            read_obj.employee_name = f"{refreshed.employee.first_name} {refreshed.employee.last_name or ''}".strip()
            read_obj.employee_code = refreshed.employee.employee_code
        return read_obj

    async def cancel_leave(
        self,
        application_id: int,
        cancelled_by_user_id: int,
    ) -> LeaveApplicationRead:
        app = await self.repo.get_application_by_id(application_id)
        if not app:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave application not found")
        if app.status not in ("PENDING", "APPROVED"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PENDING or APPROVED leave can be cancelled")

        # Cache relationship data before commit/expire
        leave_type_name = app.leave_type.name if app.leave_type else ""
        leave_type_code = app.leave_type.code if app.leave_type else ""
        app_employee_id = app.employee_id
        app_leave_type_id = app.leave_type_id
        app_days_count = float(app.days_count)
        app_from_date = app.from_date
        app_to_date = app.to_date
        app_id = app.id

        was_approved = app.status == "APPROVED"
        app.status = "CANCELLED"
        app.erp_event_id = f"LEAVE-{app.id}-CANCELLED"
        app.erp_sync_status = "PENDING"
        app.actioned_by = cancelled_by_user_id
        app.actioned_at = datetime.now()

        # Reversal ledger entry and attendance cleanup if it was previously approved
        if was_approved:
            reversal_entry = LeaveLedgerEntry(
                employee_id=app_employee_id,
                leave_type_id=app_leave_type_id,
                transaction_type="REVERSAL",
                transaction_id=app_id,
                leaves=app_days_count,  # Credit back
                from_date=app_from_date,
                to_date=app_to_date,
                is_carry_forward=False,
                is_expired=False,
            )
            await self.repo.create_ledger_entry(reversal_entry)

            # Revert attendance records for the cancelled leave days
            curr = app_from_date
            while curr <= app_to_date:
                rec = await self.attendance_record_repo.get_by_employee_and_date(app_employee_id, curr)
                if rec and rec.status in ("ON_LEAVE", "HALF_DAY"):
                    if rec.punch_in or rec.punch_out or rec.worked_minutes > 0:
                        rec.status = "PRESENT"
                    else:
                        await self.attendance_record_repo.delete(rec)
                curr += timedelta(days=1)

        await self.session.commit()
        refreshed = await self.repo.get_application_by_id(app_id)
        read_obj = LeaveApplicationRead.model_validate(refreshed)
        read_obj.leave_type_name = leave_type_name
        read_obj.leave_type_code = leave_type_code
        if refreshed and refreshed.employee:
            read_obj.employee_name = f"{refreshed.employee.first_name} {refreshed.employee.last_name or ''}".strip()
            read_obj.employee_code = refreshed.employee.employee_code
        return read_obj

    async def list_applications(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[LeaveApplicationRead]:
        apps = await self.repo.list_applications(
            employee_id=employee_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        reads = []
        for a in apps:
            r = LeaveApplicationRead.model_validate(a)
            if a.leave_type:
                r.leave_type_name = a.leave_type.name
                r.leave_type_code = a.leave_type.code
            if a.employee:
                r.employee_name = f"{a.employee.first_name} {a.employee.last_name or ''}".strip()
                r.employee_code = a.employee.employee_code
            reads.append(r)
        return reads
