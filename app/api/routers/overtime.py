from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_business_user, require_permission
from core.database import get_async_session
from core.employee_access import get_current_employee, get_permission_scope, require_employee_access
from core.pagination import PaginatedResponse
from core.sorting import OvertimeSort
from db.models import User
from schemas.overtime import (
    OvertimeApprovalCreate,
    OvertimeRecordRead,
    OvertimeRejectionCreate,
    OvertimeSummary,
)
from services.overtime_service import OvertimeService

router = APIRouter(prefix="/overtime", tags=["overtime"])


@router.get("/", response_model=PaginatedResponse[OvertimeRecordRead])
async def list_overtime(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    from_date: date | None = None,
    to_date: date | None = None,
    q: str | None = Query(None, max_length=200),
    search: str | None = Query(None, max_length=200),
    sort_by: OvertimeSort | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[OvertimeRecordRead]:
    service = OvertimeService(session)
    current_user = _
    # Managers have the department-specific permission while organization owners
    # have the organization-wide one. Merge both before choosing the list scope.
    scope = await get_permission_scope(current_user, "overtime.view", session)
    scope.include(await get_permission_scope(current_user, "overtime.view_department", session))
    scope.include(await get_permission_scope(current_user, "overtime.approve", session))
    if employee_id is not None:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(
            current_user,
            employee,
            ("overtime.view", "overtime.view_department", "overtime.approve"),
            session,
            allow_self=True,
        )
    elif scope.self_only:
        employee_id = (await get_current_employee(current_user, session)).id
    return await service.list_overtime(
        employee_id=employee_id,
        status=status_filter,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
        from_date=from_date,
        to_date=to_date,
        q=search if search is not None else q,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get("/{ot_id}", response_model=OvertimeRecordRead)
async def get_overtime(
    ot_id: int,
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    record = await service.repo.get_by_id(ot_id)
    if record is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Overtime record not found")
    employee = await service.employee_repo.get_by_id(record.employee_id)
    if employee is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(
        _, employee, ("overtime.view", "overtime.view_department", "overtime.approve"), session, allow_self=True
    )
    return await service.get_overtime(ot_id)


@router.get("/employee/{emp_id}/summary", response_model=OvertimeSummary)
async def get_overtime_summary(
    emp_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeSummary:
    service = OvertimeService(session)
    employee = await service.employee_repo.get_by_id(emp_id)
    if employee is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(_, employee, ("overtime.view", "overtime.view_department"), session, allow_self=True)
    return await service.get_overtime_summary(employee_id=emp_id, month=month, year=year)


@router.patch("/{ot_id}/approve", response_model=OvertimeRecordRead)
async def approve_overtime(
    ot_id: int,
    data: OvertimeApprovalCreate,
    current_user: User = Depends(require_permission("overtime.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    record = await service.repo.get_by_id(ot_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime record not found")
    employee = await service.employee_repo.get_by_id(record.employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await require_employee_access(current_user, employee, "overtime.approve", session)
    return await service.approve_overtime(ot_id, data, actioned_by_user_id=current_user.id)


@router.patch("/{ot_id}/reject", response_model=OvertimeRecordRead)
async def reject_overtime(
    ot_id: int,
    data: OvertimeRejectionCreate,
    current_user: User = Depends(require_permission("overtime.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    record = await service.repo.get_by_id(ot_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime record not found")
    employee = await service.employee_repo.get_by_id(record.employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await require_employee_access(current_user, employee, "overtime.approve", session)
    return await service.reject_overtime(ot_id, data, actioned_by_user_id=current_user.id)
