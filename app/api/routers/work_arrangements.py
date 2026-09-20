from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from core.employee_access import (
    get_current_employee,
    get_permission_scope,
    require_employee_access,
)
from db.models import User
from schemas.work_arrangements import (
    WorkArrangementAction,
    WorkArrangementCreate,
    WorkArrangementRead,
)
from services.work_arrangement_service import WorkArrangementService

router = APIRouter(prefix="/work-arrangements", tags=["work-arrangements"])


@router.get("/", response_model=list[WorkArrangementRead])
async def list_work_arrangements(
    employee_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    arrangement_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkArrangementRead]:
    service = WorkArrangementService(session)
    current_employee = await get_current_employee(current_user, session)
    scope = await get_permission_scope(current_user, "work_arrangement.manage", session)
    scope.include(
        await get_permission_scope(current_user, "work_arrangement.approve", session)
    )
    scope.include(
        await get_permission_scope(current_user, "work_arrangement.reject", session)
    )
    if employee_id is not None:
        employee = await service.employee_repo.get_by_id(employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await require_employee_access(
            current_user,
            employee,
            (
                "work_arrangement.manage",
                "work_arrangement.approve",
                "work_arrangement.reject",
            ),
            session,
            allow_self=True,
        )
    elif not scope.organization and not scope.unit_ids and not scope.department_ids:
        employee_id = current_employee.id

    return await service.list_requests(
        employee_id=employee_id,
        status=status_filter,
        arrangement_type=arrangement_type,
        from_date=from_date,
        to_date=to_date,
        unit_ids=None if scope.organization else scope.unit_ids,
        department_ids=None if scope.organization else scope.department_ids,
    )


@router.get("/{req_id}", response_model=WorkArrangementRead)
async def get_work_arrangement(
    req_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    request = await service.repo.get_by_id(req_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Work arrangement request not found")
    await require_employee_access(
        current_user,
        request.employee,
        (
            "work_arrangement.manage",
            "work_arrangement.approve",
            "work_arrangement.reject",
        ),
        session,
        allow_self=True,
    )
    return WorkArrangementRead.model_validate(request)


@router.post("/", response_model=WorkArrangementRead, status_code=status.HTTP_201_CREATED)
async def create_work_arrangement(
    data: WorkArrangementCreate,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    employee = await service.employee_repo.get_by_id(data.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await require_employee_access(
        current_user,
        employee,
        "work_arrangement.manage",
        session,
        allow_self=True,
    )
    return await service.create_request(data)


@router.patch("/{req_id}/approve", response_model=WorkArrangementRead)
async def approve_work_arrangement(
    req_id: int,
    current_user: User = Depends(require_permission("work_arrangement.approve")),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    request = await service.get_request(req_id)
    employee = await service.employee_repo.get_by_id(request.employee_id)
    await require_employee_access(current_user, employee, "work_arrangement.approve", session)
    return await service.approve_request(req_id, current_user.id)


@router.patch("/{req_id}/reject", response_model=WorkArrangementRead)
async def reject_work_arrangement(
    req_id: int,
    action: WorkArrangementAction,
    current_user: User = Depends(require_permission("work_arrangement.reject")),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    request = await service.get_request(req_id)
    employee = await service.employee_repo.get_by_id(request.employee_id)
    await require_employee_access(current_user, employee, "work_arrangement.reject", session)
    return await service.reject_request(req_id, current_user.id, action.rejection_reason)


@router.patch("/{req_id}/cancel", response_model=WorkArrangementRead)
async def cancel_work_arrangement(
    req_id: int,
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> WorkArrangementRead:
    service = WorkArrangementService(session)
    request = await service.get_request(req_id)
    employee = await service.employee_repo.get_by_id(request.employee_id)
    await require_employee_access(
        current_user,
        employee,
        "work_arrangement.cancel",
        session,
        allow_self=True,
    )
    return await service.cancel_request(req_id, current_user.id)
