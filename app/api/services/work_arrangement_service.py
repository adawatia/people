from datetime import date, datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AttendanceRecord, WorkArrangementRequest
from repositories.attendance_record_repo import AttendanceRecordRepository
from repositories.employee_repo import EmployeeRepository
from repositories.work_arrangement_repo import WorkArrangementRepository
from schemas.work_arrangements import (
    WorkArrangementAction,
    WorkArrangementCreate,
    WorkArrangementRead,
)


class WorkArrangementService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = WorkArrangementRepository(session)
        self.employee_repo = EmployeeRepository(session)
        self.attendance_record_repo = AttendanceRecordRepository(session)

    async def create_request(self, data: WorkArrangementCreate) -> WorkArrangementRead:
        if data.to_date < data.from_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_date must be greater than or equal to from_date",
            )

        emp = await self.employee_repo.get_by_id(data.employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        valid_types = {"WORK_FROM_HOME", "OUT_DUTY", "FIELD_WORK", "OFFICE"}
        arr_type = data.arrangement_type.upper()
        if arr_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid arrangement type '{arr_type}'. Must be one of: {valid_types}",
            )

        overlap = await self.repo.find_overlapping(data.employee_id, data.from_date, data.to_date)
        if overlap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee already has an active work arrangement request for these dates",
            )

        # Check for overlapping pending or approved leave applications
        from db.models import LeaveApplication
        from sqlalchemy import select
        leave_stmt = select(LeaveApplication).where(
            LeaveApplication.employee_id == data.employee_id,
            LeaveApplication.status.in_(["PENDING", "APPROVED"]),
            LeaveApplication.from_date <= data.to_date,
            LeaveApplication.to_date >= data.from_date,
        )
        existing_leave = (await self.session.execute(leave_stmt)).scalars().first()
        if existing_leave:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee already has a pending or approved leave overlapping with these dates",
            )

        req = WorkArrangementRequest(
            employee_id=data.employee_id,
            arrangement_type=arr_type,
            from_date=data.from_date,
            to_date=data.to_date,
            reason=data.reason,
            destination_location=data.destination_location,
            contact_phone=data.contact_phone,
            status="PENDING",
        )
        created = await self.repo.create(req)
        await self.session.commit()
        await self.session.refresh(created)
        return WorkArrangementRead.model_validate(created)

    async def approve_request(
        self,
        request_id: int,
        actioned_by_user_id: int,
    ) -> WorkArrangementRead:
        req = await self.repo.get_by_id(request_id)
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work arrangement request not found")
        if req.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request is not in PENDING state")

        # Self-approval prevention
        emp = await self.employee_repo.get_by_id(req.employee_id)
        if emp and emp.user_id == actioned_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approvers cannot approve their own work arrangement requests",
            )

        req.status = "APPROVED"
        req.actioned_by = actioned_by_user_id
        req.actioned_at = datetime.now()

        # Update attendance records accordingly
        status_to_set = "WORK_FROM_HOME" if req.arrangement_type == "WORK_FROM_HOME" else "PRESENT"

        curr = req.from_date
        while curr <= req.to_date:
            rec = await self.attendance_record_repo.get_by_employee_and_date(req.employee_id, curr)
            if rec:
                rec.status = status_to_set
            else:
                new_rec = AttendanceRecord(
                    employee_id=req.employee_id,
                    attendance_date=curr,
                    status=status_to_set,
                    worked_minutes=480 if status_to_set == "PRESENT" else 0,
                    late_minutes=0,
                    early_exit_minutes=0,
                    overtime_minutes=0,
                )
                await self.attendance_record_repo.create(new_rec)
            curr += timedelta(days=1)

        await self.session.commit()
        await self.session.refresh(req)
        return WorkArrangementRead.model_validate(req)

    async def reject_request(
        self,
        request_id: int,
        actioned_by_user_id: int,
        rejection_reason: str | None = None,
    ) -> WorkArrangementRead:
        req = await self.repo.get_by_id(request_id)
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work arrangement request not found")
        if req.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request is not in PENDING state")

        # Self-approval prevention
        emp = await self.employee_repo.get_by_id(req.employee_id)
        if emp and emp.user_id == actioned_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approvers cannot act on their own work arrangement requests",
            )

        req.status = "REJECTED"
        req.actioned_by = actioned_by_user_id
        req.actioned_at = datetime.now()
        req.rejection_reason = rejection_reason
        await self.session.commit()
        await self.session.refresh(req)
        return WorkArrangementRead.model_validate(req)

    async def cancel_request(
        self,
        request_id: int,
        cancelled_by_user_id: int,
    ) -> WorkArrangementRead:
        req = await self.repo.get_by_id(request_id)
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work arrangement request not found")
        if req.status not in ("PENDING", "APPROVED"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PENDING or APPROVED requests can be cancelled")

        was_approved = req.status == "APPROVED"
        req.status = "CANCELLED"
        req.actioned_by = cancelled_by_user_id
        req.actioned_at = datetime.now()

        # Revert attendance records if previously approved
        if was_approved:
            status_to_check = "WORK_FROM_HOME" if req.arrangement_type == "WORK_FROM_HOME" else "PRESENT"
            curr = req.from_date
            while curr <= req.to_date:
                rec = await self.attendance_record_repo.get_by_employee_and_date(req.employee_id, curr)
                if rec and rec.status == status_to_check:
                    if not (rec.punch_in or rec.punch_out):
                        await self.attendance_record_repo.delete(rec)
                curr += timedelta(days=1)

        await self.session.commit()
        await self.session.refresh(req)
        return WorkArrangementRead.model_validate(req)


    async def get_request(self, request_id: int) -> WorkArrangementRead:
        req = await self.repo.get_by_id(request_id)
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work arrangement request not found")
        return WorkArrangementRead.model_validate(req)

    async def list_requests(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        arrangement_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[WorkArrangementRead]:
        requests = await self.repo.list_requests(
            employee_id=employee_id,
            status=status,
            arrangement_type=arrangement_type,
            from_date=from_date,
            to_date=to_date,
            unit_ids=unit_ids,
            department_ids=department_ids,
        )
        return [WorkArrangementRead.model_validate(r) for r in requests]
