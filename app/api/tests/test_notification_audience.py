from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.business_roles import DEPARTMENT_MANAGER, HR_ADMIN, ORGANIZATION_OWNER
from routers.notifications import build_notification_filter, can_read_notification, notification_target_roles


def test_role_broadcast_audiences_are_specific():
    assert notification_target_roles(HR_ADMIN) == {"ALL", "STAFF", "HR"}
    assert notification_target_roles(DEPARTMENT_MANAGER) == {"ALL", "STAFF", "MANAGER"}
    assert notification_target_roles(ORGANIZATION_OWNER) == {"ALL", "STAFF", "OWNER"}
    assert notification_target_roles(None) == {"ALL", "STAFF", "EMPLOYEE"}
    assert notification_target_roles(None, employee_linked=False) == {"ALL", "STAFF"}


def test_notification_visibility_respects_direct_role_and_global_targets():
    employee = SimpleNamespace(id=10, is_superuser=False)
    manager = SimpleNamespace(id=20, is_superuser=False)
    admin = SimpleNamespace(id=1, is_superuser=True)
    employee_roles = notification_target_roles(None)
    manager_roles = notification_target_roles(DEPARTMENT_MANAGER)

    hr_notice = SimpleNamespace(user_id=None, target_role="HR", notification_type="workflow")
    direct_notice = SimpleNamespace(user_id=10, target_role=None, notification_type="workflow")
    other_direct_notice = SimpleNamespace(user_id=20, target_role=None, notification_type="workflow")
    global_notice = SimpleNamespace(user_id=None, target_role=None, notification_type="system")
    unscoped_workflow = SimpleNamespace(user_id=None, target_role=None, notification_type="workflow")
    staff_notice = SimpleNamespace(user_id=None, target_role="staff", notification_type="workflow")

    assert can_read_notification(employee, hr_notice, employee_roles) is False
    assert can_read_notification(manager, hr_notice, manager_roles) is False
    assert can_read_notification(admin, hr_notice, set()) is True
    assert can_read_notification(employee, direct_notice, employee_roles) is True
    assert can_read_notification(employee, other_direct_notice, employee_roles) is False
    assert can_read_notification(employee, global_notice, employee_roles) is True
    assert can_read_notification(employee, unscoped_workflow, employee_roles) is False
    assert can_read_notification(employee, staff_notice, employee_roles) is True


@pytest.mark.asyncio
async def test_database_filter_includes_only_the_users_role_broadcasts():
    user = SimpleNamespace(id=14, is_superuser=False)
    employee = SimpleNamespace(role=HR_ADMIN, business_role=HR_ADMIN)
    session = SimpleNamespace(scalar=AsyncMock(return_value=employee))

    expression = await build_notification_filter(user, session)
    sql = str(expression.compile(compile_kwargs={"literal_binds": True}))

    assert "'HR'" in sql
    assert "'MANAGER'" not in sql
    assert "notifications.user_id = 14" in sql
    session.scalar.assert_awaited_once()
