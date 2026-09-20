from datetime import date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import User
from schemas.employees import (
    EmployeeCreate,
    EmployeeDeactivateRequest,
    EmployeeRead,
    EmployeeUpdate,
    EmployeeWorkHistoryRead,
    PaginatedEmployeesResponse,
)
from services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/", response_model=PaginatedEmployeesResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = None,
    unit_id: int | None = None,
    department_id: int | None = None,
    designation_id: int | None = None,
    status: str | None = None,
    reporting_manager_id: int | None = None,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedEmployeesResponse:
    service = EmployeeService(session)
    return await service.list_employees(
        page=page,
        page_size=page_size,
        q=q,
        unit_id=unit_id,
        department_id=department_id,
        designation_id=designation_id,
        status_filter=status,
        reporting_manager_id=reporting_manager_id,
    )


@router.post("/", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    data: EmployeeCreate,
    _: User = Depends(require_permission("employee.create")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    return await service.create_employee(data)


@router.get("/{emp_id}", response_model=EmployeeRead)
async def get_employee(
    emp_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    emp = await service.get_employee(emp_id)
    return service.enrich(emp)


@router.patch("/{emp_id}", response_model=EmployeeRead)
async def update_employee(
    emp_id: int,
    data: EmployeeUpdate,
    _: User = Depends(require_permission("employee.update")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    return await service.update_employee(emp_id, data)


@router.patch("/{emp_id}/deactivate", response_model=EmployeeRead)
async def deactivate_employee(
    emp_id: int,
    payload: EmployeeDeactivateRequest | None = None,
    _: User = Depends(require_permission("employee.deactivate")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    exit_date = payload.exit_date if payload else None
    exit_reason = payload.exit_reason if payload else None
    return await service.deactivate_employee(emp_id, exit_date=exit_date, exit_reason=exit_reason)


@router.patch("/{emp_id}/activate", response_model=EmployeeRead)
async def activate_employee(
    emp_id: int,
    _: User = Depends(require_permission("employee.update")),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    return await service.activate_employee(emp_id)


@router.get("/{emp_id}/work-history", response_model=list[EmployeeWorkHistoryRead])
async def get_employee_work_history(
    emp_id: int,
    _: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> list[EmployeeWorkHistoryRead]:
    service = EmployeeService(session)
    return await service.get_work_history(emp_id)
