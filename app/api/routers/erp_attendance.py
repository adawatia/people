from datetime import datetime

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_erp_api_key
from core.database import get_async_session
from db.models import AttendanceCorrectionRequest, AttendancePunch, AttendanceRecord, Employee, now_ist
from schemas.attendance import (
    AttendancePunchCreate,
    ErpAttendanceRecordCreate,
    ErpCorrectionCreate,
    ErpSyncResult,
)
from services.attendance_service import AttendanceService

router = APIRouter(prefix="/integrations/erp/attendance", tags=["erp-attendance"])


async def _employee(session: AsyncSession, employee_id: int | None, employee_code: str | None) -> Employee:
    if employee_id is not None:
        employee = await session.get(Employee, employee_id)
    elif employee_code:
        employee = await session.scalar(select(Employee).where(Employee.employee_code == employee_code))
    else:
        employee = None
    if employee is None:
        raise ValueError("Employee not found")
    return employee


@router.post("/punches", response_model=ErpSyncResult, summary="ERP sync attendance punches", description="Idempotent bulk synchronization. Each item must include a unique erp_event_id.", dependencies=[Depends(verify_erp_api_key)])
async def sync_punches(
    punches: list[AttendancePunchCreate],
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    service = AttendanceService(session)
    result = ErpSyncResult()
    for item in punches:
        try:
            if not item.erp_event_id:
                raise ValueError("erp_event_id is required")
            existing = await session.scalar(select(AttendancePunch).where(AttendancePunch.erp_event_id == item.erp_event_id))
            if existing:
                result.duplicates.append({"erp_event_id": item.erp_event_id, "id": existing.id})
                continue
            employee = await _employee(session, item.employee_id, item.employee_code)
            item.employee_id = employee.id
            item.employee_code = None
            item.source = "ERP"
            created = await service.record_punch(item)
            result.accepted.append({"erp_event_id": item.erp_event_id, "id": created.id, "request_id": request_id})
            await session.commit()
        except Exception as exc:
            await session.rollback()
            result.failed.append({"erp_event_id": item.erp_event_id, "error": str(exc)})
    await session.commit()
    return result


@router.post("/records", response_model=ErpSyncResult, summary="ERP sync attendance records", description="Idempotent bulk synchronization keyed by erp_record_id and employee attendance date.", dependencies=[Depends(verify_erp_api_key)])
async def sync_records(
    records: list[ErpAttendanceRecordCreate],
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    result = ErpSyncResult()
    for item in records:
        try:
            employee = await _employee(session, item.employee_id, item.employee_code)
            existing = await session.scalar(select(AttendanceRecord).where(AttendanceRecord.erp_record_id == item.erp_record_id))
            if existing:
                result.duplicates.append({"erp_record_id": item.erp_record_id, "id": existing.id})
                continue
            record = await session.scalar(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.attendance_date == item.attendance_date,
                )
            )
            if record is None:
                record = AttendanceRecord(employee_id=employee.id, attendance_date=item.attendance_date)
                session.add(record)
            record.status = item.status.upper()
            record.punch_in = item.punch_in
            record.punch_out = item.punch_out
            record.worked_minutes = item.worked_minutes
            record.overtime_minutes = item.overtime_minutes
            record.late_minutes = item.late_minutes
            record.early_exit_minutes = item.early_exit_minutes
            record.source = "ERP"
            record.erp_record_id = item.erp_record_id
            record.sync_status = "ERP_CONFIRMED"
            record.last_synced_at = now_ist()
            await session.flush()
            result.accepted.append({"erp_record_id": item.erp_record_id, "id": record.id})
            await session.commit()
        except Exception as exc:
            await session.rollback()
            result.failed.append({"erp_record_id": item.erp_record_id, "error": str(exc)})
    await session.commit()
    return result


@router.post("/corrections", response_model=ErpSyncResult, summary="ERP sync attendance corrections", description="Synchronizes authoritative corrections and preserves correction history.", dependencies=[Depends(verify_erp_api_key)])
async def sync_corrections(
    corrections: list[ErpCorrectionCreate],
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    result = ErpSyncResult()
    for item in corrections:
        try:
            existing = await session.scalar(
                select(AttendanceCorrectionRequest).where(
                    AttendanceCorrectionRequest.erp_correction_id == item.erp_correction_id
                )
            )
            if existing:
                result.duplicates.append({"erp_correction_id": item.erp_correction_id, "id": existing.id})
                continue
            employee = await _employee(session, item.employee_id, item.employee_code)
            record = await session.scalar(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.attendance_date == item.attendance_date,
                )
            )
            if record is None:
                raise ValueError("Attendance record not found")
            correction = AttendanceCorrectionRequest(
                attendance_record_id=record.id,
                requested_punch_in=item.requested_punch_in,
                requested_punch_out=item.requested_punch_out,
                reason=item.reason,
                status="CONFIRMED",
                erp_correction_id=item.erp_correction_id,
                sync_status="ERP_CONFIRMED",
                actioned_at=now_ist(),
            )
            session.add(correction)
            if item.requested_punch_in is not None:
                record.punch_in = item.requested_punch_in
            if item.requested_punch_out is not None:
                record.punch_out = item.requested_punch_out
            record.sync_status = "ERP_CONFIRMED"
            record.last_synced_at = now_ist()
            await session.flush()
            result.accepted.append({"erp_correction_id": item.erp_correction_id, "id": correction.id})
            await session.commit()
        except Exception as exc:
            await session.rollback()
            result.failed.append({"erp_correction_id": item.erp_correction_id, "error": str(exc)})
    await session.commit()
    return result


@router.post("/reconcile", response_model=ErpSyncResult, dependencies=[Depends(verify_erp_api_key)])
async def reconcile(
    records: list[ErpAttendanceRecordCreate],
    session: AsyncSession = Depends(get_async_session),
) -> ErpSyncResult:
    return await sync_records(records, session)
