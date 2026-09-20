from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import employee_access


def _assignment(permission: str, scope_type: str, scope_id: int | None):
    link = SimpleNamespace(permission=SimpleNamespace(permission_code=permission))
    role = SimpleNamespace(permission_links=[link])
    return SimpleNamespace(role=role, scope_type=scope_type, scope_id=scope_id)


@pytest.mark.asyncio
async def test_permission_scope_collects_only_matching_assignments(monkeypatch):
    assignments = [
        _assignment("work_arrangement.approve", "unit", 7),
        _assignment("work_arrangement.approve", "department", 12),
        _assignment("leave.approve", "organization", None),
    ]
    monkeypatch.setattr(
        employee_access,
        "get_user_role_assignments",
        AsyncMock(return_value=assignments),
    )

    scope = await employee_access.get_permission_scope(
        SimpleNamespace(id=3, is_superuser=False),
        "work_arrangement.approve",
        AsyncMock(),
    )

    assert scope.organization is False
    assert scope.unit_ids == {7}
    assert scope.department_ids == {12}
    assert scope.allows(SimpleNamespace(unit_id=7, department_id=None))
    assert not scope.allows(SimpleNamespace(unit_id=8, department_id=13))


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
    monkeypatch.setattr(
        employee_access,
        "get_user_role_assignments",
        AsyncMock(return_value=[_assignment("work_arrangement.approve", "unit", 7)]),
    )

    with pytest.raises(HTTPException) as exc_info:
        await employee_access.require_employee_access(
            SimpleNamespace(id=4, is_superuser=False),
            SimpleNamespace(user_id=9, unit_id=8, department_id=13),
            "work_arrangement.approve",
            AsyncMock(),
        )

    assert exc_info.value.status_code == 403
