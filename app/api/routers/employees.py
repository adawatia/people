from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import current_business_user
from core.database import get_async_session
from core.employee_access import get_employee_scope, require_employee_access
from core.pagination import PaginatedResponse
from core.sorting import EmployeeHistorySort, EmployeeSort
from db.models import User
from schemas.employees import (
    EmployeeDirectoryRead,
    EmployeeRead,
    EmployeeWorkHistoryRead,
    PaginatedEmployeesResponse,
)
from services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/", response_model=PaginatedEmployeesResponse)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    sort_by: EmployeeSort | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    unit_id: int | None = None,
    department_id: int | None = None,
    designation_id: int | None = None,
    status: str | None = None,
    reporting_manager_id: int | None = None,
    _: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedEmployeesResponse:
    current_user = _
    allowed_employee_ids: set[int] | None = None
    allowed_unit_ids: set[int] | None = None
    allowed_department_ids: set[int] | None = None
    if not current_user.is_superuser:
        # The directory is readable by any authenticated user, but only within
        # the row scope of their business role: an employee sees themselves, a
        # manager their department, HR their unit or the organization.
        scope = await get_employee_scope(current_user, session)
        if scope.organization:
            pass
        elif scope.employee_ids:
            allowed_employee_ids = set(scope.employee_ids)
        elif scope.unit_ids:
            allowed_unit_ids = scope.unit_ids
        elif scope.department_ids:
            allowed_department_ids = scope.department_ids
        else:
            # Elevated role without a usable scope (e.g. unit HR with no unit)
            # must not degrade into an unrestricted listing.
            allowed_employee_ids = set()
    service = EmployeeService(session)
    return await service.list_employees(
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        unit_id=unit_id,
        department_id=department_id,
        designation_id=designation_id,
        status_filter=status,
        reporting_manager_id=reporting_manager_id,
        allowed_employee_ids=allowed_employee_ids,
        allowed_unit_ids=allowed_unit_ids,
        allowed_department_ids=allowed_department_ids,
    )


@router.get("/{emp_id}", response_model=EmployeeDirectoryRead)
async def get_employee(
    emp_id: int,
    current_user: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> EmployeeRead:
    service = EmployeeService(session)
    emp = await service.get_employee(emp_id)
    await require_employee_access(current_user, emp, "employee.view", session, allow_self=True)
    return service.enrich_directory(emp)


@router.get("/{emp_id}/work-history", response_model=PaginatedResponse[EmployeeWorkHistoryRead])
async def get_employee_work_history(
    emp_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    sort_by: EmployeeHistorySort | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse[EmployeeWorkHistoryRead]:
    service = EmployeeService(session)
    employee = await service.get_employee(emp_id)
    await require_employee_access(current_user, employee, "employee.view", session, allow_self=True)
    return await service.work_history_page(
        emp_id,
        page,
        page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
