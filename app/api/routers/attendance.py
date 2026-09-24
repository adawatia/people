from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from core.employee_access import (
    EmployeeAccessScope,
    get_current_employee,
    get_permission_scope,
    require_employee_access,
)
from core.pagination import PaginatedResponse
from db.models import User
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
from services.attendance_service import AttendanceService

router = APIRouter(prefix="/attendance", tags=["attendance"])

ATTENDANCE_READ_PERMISSIONS = (
    "attendance.view",
    "attendance.view_unit",
    "attendance.view_department",
)


async def _attendance_read_scope(user: User, session: AsyncSession) -> EmployeeAccessScope:
    scope = EmployeeAccessScope()
    for permission in ATTENDANCE_READ_PERMISSIONS:
        scope.include(await get_permission_scope(user, permission, session))
    return scope


# ── Raw Biometric / Mobile Punch Ingestion ────────────────────────────────────

@router.post("/checkins", response_model=AttendancePunchRead, status_code=status.HTTP_201_CREATED)
async def record_checkin(
    data: AttendancePunchCreate,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendancePunchRead:
    raise HTTPException(status_code=403, detail="Attendance punches are supplied by ERP")


@router.post("/checkins/bulk", response_model=list[AttendancePunchRead], status_code=status.HTTP_201_CREATED)
async def record_bulk_checkins(
    data: BulkPunchCreate,
    _: User = Depends(require_permission("attendance.process")),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendancePunchRead]:
    raise HTTPException(status_code=403, detail="Attendance punches are supplied by ERP")


@router.get("/checkins", response_model=PaginatedResponse[AttendancePunchRead])
async def list_checkins(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    employee_id: int | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    is_processed: bool | None = None,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[AttendancePunchRead]:
    service = AttendanceService(session)
    scope = await _attendance_read_scope(current_user, session)
    if employee_id is not None:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(
            current_user,
            employee,
            ATTENDANCE_READ_PERMISSIONS,
            session,
            allow_self=True,
        )
    elif scope.self_only:
        employee_id = (await get_current_employee(current_user, session)).id
    return await service.list_punches_page(
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        employee_id=employee_id,
        from_time=from_time,
        to_time=to_time,
        is_processed=is_processed,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


@router.get("/", response_model=PaginatedResponse[AttendanceRecordRead])
async def list_attendance(
    employee_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[AttendanceRecordRead]:
    service = AttendanceService(session)
    scope = await _attendance_read_scope(current_user, session)
    if employee_id is not None:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(
            current_user,
            employee,
            ATTENDANCE_READ_PERMISSIONS,
            session,
            allow_self=True,
        )
    elif scope.self_only:
        employee_id = (await get_current_employee(current_user, session)).id
    return await service.list_attendance_page(
        search=search, sort_by=sort_by, sort_order=sort_order,
        employee_id=employee_id,
        from_date=from_date,
        to_date=to_date,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


@router.get("/records/{record_id}", response_model=AttendanceRecordRead)
async def get_attendance_record(
    record_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceRecordRead:
    service = AttendanceService(session)
    record = await service.record_repo.get_by_id(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    await require_employee_access(
        current_user,
        record.employee,
        ATTENDANCE_READ_PERMISSIONS,
        session,
        allow_self=True,
    )
    return AttendanceRecordRead.model_validate(record)


@router.get("/employee/{emp_id}/calendar", response_model=list[AttendanceRecordRead])
async def get_employee_calendar(
    emp_id: int,
    year: int = Query(...),
    month: int = Query(...),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[AttendanceRecordRead]:
    """Return all attendance records for an employee in a given month — for calendar view."""
    service = AttendanceService(session)
    employee = await service.employee_repo.get_by_id(emp_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(current_user, employee, ATTENDANCE_READ_PERMISSIONS, session, allow_self=True)
    return await service.get_employee_calendar(emp_id=emp_id, year=year, month=month)


@router.get("/employee/{emp_id}/summary", response_model=AttendanceSummaryRead)
async def get_attendance_summary(
    emp_id: int,
    year: int = Query(...),
    month: int = Query(...),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceSummaryRead:
    service = AttendanceService(session)
    employee = await service.employee_repo.get_by_id(emp_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(current_user, employee, ATTENDANCE_READ_PERMISSIONS, session, allow_self=True)
    return await service.get_attendance_summary(emp_id=emp_id, year=year, month=month)


# ── Automated Attendance Processing Engine ───────────────────────────────────

@router.post("/process", response_model=ProcessAttendanceResponse)
async def process_attendance(
    req: ProcessAttendanceRequest,
    current_user: User = Depends(require_permission("attendance.process")),
    session: AsyncSession = Depends(get_async_session),
) -> ProcessAttendanceResponse:
    """Executes the daily automated attendance calculation engine."""
    service = AttendanceService(session)
    scope = await get_permission_scope(current_user, "attendance.process", session)
    if req.employee_id is not None:
        employee = await service.employee_repo.get_by_id(req.employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(current_user, employee, "attendance.process", session)
    elif req.unit_id is not None:
        if not scope.organization and req.unit_id not in scope.unit_ids:
            raise HTTPException(status_code=403, detail="You cannot process attendance for this unit")
    elif not scope.organization:
        raise HTTPException(status_code=403, detail="A scoped attendance run must specify an authorized unit or employee")
    return await service.process_attendance_batch(req)


# ── Attendance Correction Workflow ─────────────────────────────────────────

@router.post("/corrections", response_model=AttendanceCorrectionRead, status_code=status.HTTP_201_CREATED)
async def submit_correction(
    data: AttendanceCorrectionCreate,
    current_user: User = Depends(require_permission("attendance.correct")),
    session: AsyncSession = Depends(get_async_session),
) -> AttendanceCorrectionRead:
    """HR submits a correction for ERP reconciliation; ERP remains authoritative.

    Gated on the HR permission plus the caller's row scope, so unit HR can
    correct their own unit while organization HR covers every unit.
    """
    service = AttendanceService(session)
    record = await service.record_repo.get_by_id(data.attendance_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    await require_employee_access(current_user, record.employee, "attendance.correct", session)
    return await service.submit_correction(data)


@router.get("/corrections", response_model=PaginatedResponse[AttendanceCorrectionRead])
async def list_corrections(
    status: str | None = Query(None),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[AttendanceCorrectionRead]:
    """List attendance correction requests.

    HR sees their unit, everyone else sees only their own requests.
    """
    service = AttendanceService(session)
    scope = await get_permission_scope(current_user, "attendance.correct", session)
    employee_id = None
    if scope.self_only:
        employee_id = (await get_current_employee(current_user, session)).id
    return await service.list_corrections_page(
        page=page, page_size=page_size,
        search=search, sort_by=sort_by, sort_order=sort_order,
        status=status,
        employee_id=employee_id,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


# Attendance corrections are raised here but confirmed by ERP, so no approve/reject
# endpoints are exposed: a correction request stays PENDING and the ERP-confirmed
# attendance record remains the source of truth.
