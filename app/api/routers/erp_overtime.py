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
    status: str = "PENDING"


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
    for start in range(0, len(records), 500):
        chunk = records[start:start + 500]
        requested_ids = {item.employee_id for item in chunk if item.employee_id is not None}
        requested_codes = {item.employee_code for item in chunk if item.employee_code}
        employee_ids = set(await session.scalars(select(Employee.id).where(Employee.id.in_(requested_ids))))
        employee_codes = dict((await session.execute(
            select(Employee.employee_code, Employee.id).where(Employee.employee_code.in_(requested_codes))
        )).all())
        attendance_owners = dict((await session.execute(
            select(AttendanceRecord.id, AttendanceRecord.employee_id).where(
                AttendanceRecord.id.in_({item.attendance_record_id for item in chunk})
            )
        )).all())
        existing_events = dict((await session.execute(
            select(OvertimeRecord.erp_event_id, OvertimeRecord.id).where(
                OvertimeRecord.erp_event_id.in_({item.erp_event_id for item in chunk})
            )
        )).all())

        for item in chunk:
            try:
                if existing_id := existing_events.get(item.erp_event_id):
                    duplicates.append({"erp_event_id": item.erp_event_id, "id": existing_id})
                    continue
                employee_id = item.employee_id if item.employee_id in employee_ids else employee_codes.get(item.employee_code)
                if employee_id is None or attendance_owners.get(item.attendance_record_id) != employee_id:
                    raise ValueError("Employee or attendance record not found, or they do not match")
                if item.status.upper() != "PENDING" or item.approved_minutes != 0:
                    raise ValueError("ERP overtime must be pending with zero approved minutes; HRMS owns approval")
                if item.approved_minutes > item.calculated_minutes:
                    raise ValueError("approved_minutes cannot exceed calculated_minutes")
                async with session.begin_nested():
                    record = OvertimeRecord(
                        employee_id=employee_id,
                        attendance_record_id=item.attendance_record_id,
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
                existing_events[item.erp_event_id] = record.id
                accepted.append({"erp_event_id": item.erp_event_id, "id": record.id})
            except Exception as exc:
                failed.append({"erp_event_id": item.erp_event_id, "error": str(exc)})
    await session.commit()
    return {"accepted": accepted, "duplicates": duplicates, "failed": failed}
