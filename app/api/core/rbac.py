"""Fixed-role dashboard visibility helpers.

Effective permissions are resolved in ``core.auth`` (base employee set plus the
optional elevated business role) and row scope in ``core.employee_access``.
This module intentionally contains no role-assignment tables or dynamic-RBAC
behaviour: it only maps a widget key to the permission that unlocks it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_user_permissions
from db.models import User

DASHBOARD_WIDGETS: list[dict[str, str | None]] = [
    {"key": "my_profile", "permission": None},
    {"key": "my_leave_balance", "permission": None},
    {"key": "pending_approvals", "permission": "leave.approve"},
    {"key": "team_leave_requests", "permission": "leave.approve"},
    {"key": "attendance_overview", "permission": "attendance.view_department"},
    {"key": "unit_overview", "permission": "employee.view"},
    {"key": "organization_overview", "permission": "dashboard.view_organization"},
    {"key": "system_health", "permission": "system.configure"},
]


async def get_visible_widgets(user: User, session: AsyncSession) -> list[str]:
    if user.is_superuser:
        return [widget["key"] for widget in DASHBOARD_WIDGETS]
    permissions = set(await get_user_permissions(user, session))
    return [
        widget["key"]
        for widget in DASHBOARD_WIDGETS
        if widget["permission"] is None or widget["permission"] in permissions
    ]
