from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import fastapi_users
from core.database import get_async_session
from db.models import Employee, User


async def get_fixed_role(user: User, session: AsyncSession) -> str | None:
    if user.is_superuser:
        return "HR_ADMIN"
    employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
    return employee.role if employee else None


async def require_hr_admin(
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    if await get_fixed_role(current_user, session) != "HR_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="HR Admin access required")
    return current_user


async def require_hr_unit_access(user: User, employee: Employee, session: AsyncSession) -> None:
    if await get_fixed_role(user, session) == "HR_ADMIN":
        linked = await session.scalar(select(Employee).where(Employee.user_id == user.id))
        if linked and linked.unit_id is not None and linked.unit_id != employee.unit_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee is outside your unit")
