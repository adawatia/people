from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import ordered, paginate
from db.models import Employee, User


class UserAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def account_page(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str | None,
        sort_order: str,
    ) -> tuple[dict, dict[int, Employee]]:
        query = select(User).outerjoin(Employee, Employee.user_id == User.id).where(User.is_superuser.is_(False))
        if search and search.strip():
            value = search.strip()
            name = func.coalesce(User.first_name, "") + " " + func.coalesce(User.last_name, "")
            query = query.where(
                or_(
                    User.username.icontains(value, autoescape=True),
                    User.email.icontains(value, autoescape=True),
                    User.mobile_number.icontains(value, autoescape=True),
                    name.icontains(value, autoescape=True),
                    Employee.employee_code.icontains(value, autoescape=True),
                )
            )
        query = ordered(
            query,
            {
                "username": User.username,
                "email": User.email,
                "created_at": User.created_at,
                "is_active": User.is_active,
                "id": User.id,
            },
            sort_by,
            sort_order,
            "username",
            User.id,
        )
        result = await paginate(self.session, query, page, page_size)
        user_ids = [user.id for user in result["items"]]
        employees = []
        if user_ids:
            employees = list(await self.session.scalars(select(Employee).where(Employee.user_id.in_(user_ids))))
        return result, {employee.user_id: employee for employee in employees if employee.user_id is not None}

    async def get_workforce_user(self, user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(User.id == user_id, User.is_superuser.is_(False)).with_for_update()
        )
