from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import employee_access


@pytest.mark.asyncio
async def test_permission_scope_uses_fixed_employee_role(monkeypatch):
    employee = SimpleNamespace(role="DEPARTMENT_MANAGER", unit_id=7, department_id=12)
    monkeypatch.setattr(employee_access, "get_current_employee", AsyncMock(return_value=employee))
    monkeypatch.setattr(employee_access, "get_user_permissions", AsyncMock(return_value=["work_arrangement.approve"]))

    scope = await employee_access.get_permission_scope(
        SimpleNamespace(id=3, is_superuser=False),
        "work_arrangement.approve",
        AsyncMock(),
    )

    assert scope.organization is False
    assert scope.unit_ids == set()
    assert scope.department_ids == {12}
    assert scope.allows(SimpleNamespace(unit_id=None, department_id=12))
    assert not scope.allows(SimpleNamespace(unit_id=8, department_id=13))


@pytest.mark.asyncio
async def test_organization_owner_has_organization_scope(monkeypatch):
    employee = SimpleNamespace(role="ORGANIZATION_OWNER", unit_id=None, department_id=None)
    monkeypatch.setattr(employee_access, "get_current_employee", AsyncMock(return_value=employee))
    monkeypatch.setattr(employee_access, "get_user_permissions", AsyncMock(return_value=["dashboard.view_organization"]))

    scope = await employee_access.get_permission_scope(
        SimpleNamespace(id=9, is_superuser=False),
        "dashboard.view_organization",
        AsyncMock(),
    )

    assert scope.organization is True
    assert scope.allows(SimpleNamespace(unit_id=999, department_id=999))


@pytest.mark.asyncio
async def test_employee_can_access_own_record_without_management_permission():
    await employee_access.require_employee_access(
        SimpleNamespace(id=4, is_superuser=False),
        SimpleNamespace(user_id=4, unit_id=8, department_id=13),
        "work_arrangement.manage",
        AsyncMock(),
        allow_self=True,
    )


@pytest.mark.asyncio
async def test_out_of_scope_employee_is_rejected(monkeypatch):
    employee = SimpleNamespace(role="HR_ADMIN", unit_id=7, department_id=None)
    monkeypatch.setattr(employee_access, "get_current_employee", AsyncMock(return_value=employee))
    monkeypatch.setattr(employee_access, "get_user_permissions", AsyncMock(return_value=["work_arrangement.approve"]))

    with pytest.raises(HTTPException) as exc_info:
        await employee_access.require_employee_access(
            SimpleNamespace(id=4, is_superuser=False),
            SimpleNamespace(user_id=9, unit_id=8, department_id=13),
            "work_arrangement.approve",
            AsyncMock(),
        )

    assert exc_info.value.status_code == 403
