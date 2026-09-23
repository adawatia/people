"""Authenticated account profile endpoints.

Employee provisioning and lifecycle management belong to ``/employees``. The
``users`` table is the authentication identity behind each employee, so this
router intentionally exposes no standalone user CRUD API.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users, get_user_permissions
from core.business_roles import SCOPE_ORGANIZATION, resolve_business_access
from core.database import get_async_session
from db.models import Employee, User
from schemas import UserPermissionsResponse, UserRead

router = APIRouter(prefix="/users", tags=["account"])


@router.get("/me", response_model=UserRead, summary="Get the authenticated account")
async def get_current_user_me(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UserRead:
    target_user = await session.scalar(select(User).where(User.id == user.id)) or user
    user_read = UserRead.model_validate(target_user)
    user_read.permissions = await get_user_permissions(target_user, session)
    employee = await session.scalar(select(Employee).where(Employee.user_id == target_user.id).limit(1))
    if employee:
        user_read.employee_id = employee.id
        user_read.employee_code = employee.employee_code
        user_read.role = employee.role
        # Resolved (not raw) role/scope, so rows written before the scope
        # columns existed report the access they actually have.
        access = resolve_business_access(employee)
        user_read.business_role = access.business_role
        user_read.scope_type = access.scope_type
    elif target_user.is_superuser:
        user_read.role = "SUPER_ADMIN"
    if target_user.is_superuser:
        # Break-glass technical administrator: not an employee, organization wide.
        user_read.scope_type = SCOPE_ORGANIZATION
    return user_read


@router.get("/me/permissions", response_model=UserPermissionsResponse, summary="Get account permissions")
async def get_current_user_permissions(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UserPermissionsResponse:
    return UserPermissionsResponse(permissions=await get_user_permissions(user, session))
