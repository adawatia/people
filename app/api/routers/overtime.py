from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from core.employee_access import get_current_employee, get_permission_scope, require_employee_access
from db.models import User
from schemas.overtime import (
    OvertimeRecordRead,
    OvertimeSummary,
)
from services.overtime_service import OvertimeService

router = APIRouter(prefix="/overtime", tags=["overtime"])


@router.get("/", response_model=list[OvertimeRecordRead])
async def list_overtime(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[OvertimeRecordRead]:
    service = OvertimeService(session)
    current_user = _
    # Managers have the department-specific permission while organization owners
    # have the organization-wide one. Merge both before choosing the list scope.
    scope = await get_permission_scope(current_user, "overtime.view", session)
    scope.include(await get_permission_scope(current_user, "overtime.view_department", session))
    if employee_id is not None:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(current_user, employee, ("overtime.view", "overtime.view_department"), session, allow_self=True)
    elif not scope.organization and not scope.unit_ids and not scope.department_ids:
        employee_id = (await get_current_employee(current_user, session)).id
    return await service.list_overtime(
        employee_id=employee_id,
        status=status_filter,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


@router.get("/{ot_id}", response_model=OvertimeRecordRead)
async def get_overtime(
    ot_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeRecordRead:
    service = OvertimeService(session)
    record = await service.repo.get_by_id(ot_id)
    if record is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Overtime record not found")
    employee = await service.employee_repo.get_by_id(record.employee_id)
    await require_employee_access(_, employee, ("overtime.view", "overtime.view_department"), session, allow_self=True)
    return await service.get_overtime(ot_id)


@router.get("/employee/{emp_id}/summary", response_model=OvertimeSummary)
async def get_overtime_summary(
    emp_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> OvertimeSummary:
    service = OvertimeService(session)
    employee = await service.employee_repo.get_by_id(emp_id)
    if employee is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(_, employee, ("overtime.view", "overtime.view_department"), session, allow_self=True)
    return await service.get_overtime_summary(employee_id=emp_id, month=month, year=year)
