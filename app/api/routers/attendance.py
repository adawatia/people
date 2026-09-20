from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.attendance import (
    AttendanceCorrectionAction,
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
from services.attendance_service import AttendanceService

router = APIRouter(prefix="/attendance", tags=["attendance"])


# ── Raw Biometric / Mobile Punch Ingestion ────────────────────────────────────

@router.post("/checkins", response_model=AttendancePunchRead, status_code=status.HTTP_201_CREATED)
async def record_checkin(
    data: AttendancePunchCreate,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendancePunchRead:
    """Ingests a single biometric/mobile attendance punch and associates it with the active shift."""
    service = AttendanceService(session)
    return await service.record_punch(data)


@router.post("/checkins/bulk", response_model=list[AttendancePunchRead], status_code=status.HTTP_201_CREATED)
async def record_bulk_checkins(
    data: BulkPunchCreate,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendancePunchRead]:
    """Bulk records attendance punches from biometric devices or sync tools."""
    service = AttendanceService(session)
    return await service.record_bulk_punches(data)


@router.get("/checkins", response_model=list[AttendancePunchRead])
async def list_checkins(
    employee_id: int | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    is_processed: bool | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendancePunchRead]:
    service = AttendanceService(session)
    return await service.list_punches(
        employee_id=employee_id,
        from_time=from_time,
        to_time=to_time,
        is_processed=is_processed,
    )


@router.get("/", response_model=list[AttendanceRecordRead])
async def list_attendance(
    employee_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = 1,
    page_size: int = 50,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendanceRecordRead]:
    service = AttendanceService(session)
    return await service.list_attendance(
        employee_id=employee_id,
        from_date=from_date,
        to_date=to_date,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/records/{record_id}", response_model=AttendanceRecordRead)
async def get_attendance_record(
    record_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceRecordRead:
    service = AttendanceService(session)
    return await service.get_attendance_record(record_id)


@router.get("/employee/{emp_id}/calendar", response_model=list[AttendanceRecordRead])
async def get_employee_calendar(
    emp_id: int,
    year: int = Query(...),
    month: int = Query(...),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendanceRecordRead]:
    """Return all attendance records for an employee in a given month — for calendar view."""
    service = AttendanceService(session)
    return await service.get_employee_calendar(emp_id=emp_id, year=year, month=month)


@router.get("/employee/{emp_id}/summary", response_model=AttendanceSummaryRead)
async def get_attendance_summary(
    emp_id: int,
    year: int = Query(...),
    month: int = Query(...),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceSummaryRead:
    service = AttendanceService(session)
    return await service.get_attendance_summary(emp_id=emp_id, year=year, month=month)


# ── Automated Attendance Processing Engine ───────────────────────────────────

@router.post("/process", response_model=ProcessAttendanceResponse)
async def process_attendance(
    req: ProcessAttendanceRequest,
    _: User = Depends(require_permission("attendance.process")),
    session: AsyncSession = Depends(get_async_session),
) -> ProcessAttendanceResponse:
    """Executes the daily automated attendance calculation engine."""
    service = AttendanceService(session)
    return await service.process_attendance_batch(req)


# ── Attendance Correction Workflow ─────────────────────────────────────────

@router.post("/corrections", response_model=AttendanceCorrectionRead, status_code=status.HTTP_201_CREATED)
async def submit_correction(
    data: AttendanceCorrectionCreate,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceCorrectionRead:
    """Employee submits an attendance correction request."""
    service = AttendanceService(session)
    return await service.submit_correction(data)


@router.get("/corrections", response_model=list[AttendanceCorrectionRead])
async def list_corrections(
    status: str | None = Query(None),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendanceCorrectionRead]:
    service = AttendanceService(session)
    return await service.list_corrections(status=status)


@router.patch("/corrections/{correction_id}/approve", response_model=AttendanceCorrectionRead)
async def approve_correction(
    correction_id: int,
    current_user: User = Depends(require_permission("attendance.approve_correction")),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceCorrectionRead:
    service = AttendanceService(session)
    return await service.approve_correction(correction_id, current_user.id)


@router.patch("/corrections/{correction_id}/reject", response_model=AttendanceCorrectionRead)
async def reject_correction(
    correction_id: int,
    action: AttendanceCorrectionAction | None = None,
    current_user: User = Depends(require_permission("attendance.approve_correction")),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceCorrectionRead:
    service = AttendanceService(session)
    return await service.reject_correction(
        correction_id,
        current_user.id,
        action.rejection_reason if action else None,
    )

