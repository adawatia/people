import calendar
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import PaginatedResponse
from db.models import OvertimeApproval, now_ist
from repositories.employee_repo import EmployeeRepository
from repositories.overtime_repo import OvertimeRepository
from schemas.overtime import (
    OvertimeApprovalCreate,
    OvertimeRecordRead,
    OvertimeRejectionCreate,
    OvertimeSummary,
)


class OvertimeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = OvertimeRepository(session)
        self.employee_repo = EmployeeRepository(session)

    async def list_overtime(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> list[OvertimeRecordRead] | PaginatedResponse[OvertimeRecordRead]:
        if from_date and to_date and from_date > to_date:
            raise HTTPException(status_code=422, detail="Start date must not be after end date")
        filters = {
            "employee_id": employee_id, "status": status, "unit_ids": unit_ids, "department_ids": department_ids,
            "from_date": from_date, "to_date": to_date, "search": search, "sort_by": sort_by, "sort_order": sort_order,
        }
        def serialize(record):
            return OvertimeRecordRead.model_validate(record).model_copy(update={
                "employee_name": " ".join(filter(None, [record.employee.first_name, record.employee.last_name])),
                "employee_code": record.employee.employee_code,
                "attendance_date": record.attendance_record.attendance_date,
            })

        result = await self.repo.list_page(page=page, page_size=page_size, **filters)
        result["items"] = [serialize(record) for record in result["items"]]
        return PaginatedResponse[OvertimeRecordRead](**result)

    async def get_overtime(self, ot_id: int) -> OvertimeRecordRead:
        ot = await self.repo.get_by_id(ot_id)
        if not ot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime record not found")
        return OvertimeRecordRead.model_validate(ot)

    async def approve_overtime(
        self,
        ot_id: int,
        data: OvertimeApprovalCreate,
        actioned_by_user_id: int,
    ) -> OvertimeRecordRead:
        ot = await self.repo.get_by_id_for_update(ot_id)
        if not ot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime record not found")
        if ot.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Overtime is not in PENDING state")
        if data.approved_minutes <= 0 or data.approved_minutes > ot.calculated_minutes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Approved minutes must be positive and cannot exceed calculated overtime",
            )

        # Self-approval prevention
        emp = await self.employee_repo.get_by_id(ot.employee_id)
        if emp and emp.user_id == actioned_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approvers cannot approve their own overtime requests",
            )

        ot.approved_minutes = data.approved_minutes
        ot.status = "APPROVED"
        ot.actioned_by = actioned_by_user_id
        ot.actioned_at = now_ist()

        approval = OvertimeApproval(
            overtime_record_id=ot_id,
            approved_minutes=data.approved_minutes,
            actioned_by=actioned_by_user_id,
            remarks=data.remarks,
        )
        await self.repo.create_approval(approval)
        await self.session.commit()
        await self.session.refresh(ot)
        return OvertimeRecordRead.model_validate(ot)

    async def reject_overtime(
        self,
        ot_id: int,
        data: OvertimeRejectionCreate,
        actioned_by_user_id: int,
    ) -> OvertimeRecordRead:
        ot = await self.repo.get_by_id_for_update(ot_id)
        if not ot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime record not found")
        if ot.status != "PENDING":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Overtime is not in PENDING state")

        # Self-approval prevention
        emp = await self.employee_repo.get_by_id(ot.employee_id)
        if emp and emp.user_id == actioned_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approvers cannot act on their own overtime requests",
            )

        ot.status = "REJECTED"
        ot.actioned_by = actioned_by_user_id
        ot.actioned_at = now_ist()
        ot.rejection_reason = data.remarks
        await self.session.commit()
        await self.session.refresh(ot)
        return OvertimeRecordRead.model_validate(ot)

    async def get_overtime_summary(
        self,
        employee_id: int,
        month: int,
        year: int,
    ) -> OvertimeSummary:
        _, last_day = calendar.monthrange(year, month)
        from_date = date(year, month, 1)
        to_date = date(year, month, last_day)

        records = await self.repo.get_records_for_period(
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
        )

        return OvertimeSummary(
            employee_id=employee_id,
            month=month,
            year=year,
            total_calculated_minutes=sum((r.calculated_minutes or 0) for r in records),
            total_approved_minutes=sum((r.approved_minutes or 0) for r in records),
            pending_count=sum(1 for r in records if r.status == "PENDING"),
        )
