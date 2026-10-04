"""ERP-owned overtime synchronization."""

from datetime import datetime

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.erp_auth import require_erp_scope
from db.models import AttendanceRecord, Employee, OvertimeRecord

router = APIRouter(prefix="/integrations/erp/overtime", tags=["erp-overtime"])


class ErpOvertimeRecord(BaseModel):
    erp_event_id: str
    employee_id: int | None = None
    employee_code: str | None = None
    attendance_record_id: int
    overtime_start: datetime | None = None
    overtime_end: datetime | None = None
    calculated_minutes: int = Field(..., ge=0)
    approved_minutes: int = Field(default=0, ge=0)
    status: str = "APPROVED"


class ErpOvertimeSyncAccepted(BaseModel):
    erp_event_id: str
    id: int


class ErpOvertimeSyncFailure(BaseModel):
    erp_event_id: str
    error: str


class ErpOvertimeSyncResult(BaseModel):
    accepted: list[ErpOvertimeSyncAccepted] = Field(default_factory=list)
    duplicates: list[ErpOvertimeSyncAccepted] = Field(default_factory=list)
    failed: list[ErpOvertimeSyncFailure] = Field(default_factory=list)


@router.post(
    "/records/bulk",
    response_model=ErpOvertimeSyncResult,
    dependencies=[Depends(require_erp_scope("overtime:write"))],
)
async def sync_overtime_bulk(
    records: list[ErpOvertimeRecord] = Body(..., min_length=1, max_length=5000),
    session: AsyncSession = Depends(get_async_session),
) -> ErpOvertimeSyncResult:
    accepted: list[dict] = []
    duplicates: list[dict] = []
    failed: list[dict] = []
    for item in records:
        try:
            existing = await session.scalar(
                select(OvertimeRecord).where(OvertimeRecord.erp_event_id == item.erp_event_id)
            )
            if existing:
                duplicates.append({"erp_event_id": item.erp_event_id, "id": existing.id})
                continue
            employee = await session.get(Employee, item.employee_id) if item.employee_id else None
            if employee is None and item.employee_code:
                employee = await session.scalar(select(Employee).where(Employee.employee_code == item.employee_code))
            attendance = await session.get(AttendanceRecord, item.attendance_record_id)
            if employee is None or attendance is None or attendance.employee_id != employee.id:
                raise ValueError("Employee or attendance record not found, or they do not match")
            if item.approved_minutes > item.calculated_minutes:
                raise ValueError("approved_minutes cannot exceed calculated_minutes")
            record = OvertimeRecord(
                employee_id=employee.id,
                attendance_record_id=attendance.id,
                calculated_minutes=item.calculated_minutes,
                approved_minutes=item.approved_minutes,
                status=item.status.upper(),
                erp_event_id=item.erp_event_id,
                overtime_start=item.overtime_start,
                overtime_end=item.overtime_end,
                source="ERP",
            )
            session.add(record)
            await session.flush()
            accepted.append({"erp_event_id": item.erp_event_id, "id": record.id})
        except Exception as exc:
            failed.append({"erp_event_id": item.erp_event_id, "error": str(exc)})
    await session.commit()
    return {"accepted": accepted, "duplicates": duplicates, "failed": failed}
