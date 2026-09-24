import asyncio
import selectors
import sys

from core.auth import FIXED_ROLE_PERMISSIONS, setup_rate_limits


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


def test_setup_rate_limits_initializes_limiter():
    from fastapi import FastAPI

    app = FastAPI()
    setup_rate_limits(app)
    assert hasattr(app.state, "limiter")


def test_user_create_dict_contains_only_current_fields():
    from schemas import UserCreate, UserUpdate

    uc = UserCreate(
        email="employee@company.com",
        username="employee",
        password="EmployeePass123!",
        first_name="Employee",
        last_name="User",
    )
    d_user = uc.create_update_dict()
    assert "party_id" not in d_user
    assert "assigned_location_ids" not in d_user

    d_super = uc.create_update_dict_superuser()
    assert "party_id" not in d_super
    assert "assigned_location_ids" not in d_super

    uu = UserUpdate(first_name="Jane")
    d_up = uu.create_update_dict()
    assert d_up["first_name"] == "Jane"
    assert "party_id" not in d_up

    d_up_super = uu.create_update_dict_superuser()
    assert d_up_super["first_name"] == "Jane"
    assert "party_id" not in d_up_super


def test_user_read_schema_includes_permissions_and_role_properties():
    from schemas import UserRead

    user_data = {
        "id": 1,
        "email": "employee@hrms.com",
        "username": "employee",
        "is_active": True,
        "is_superuser": False,
        "is_verified": True,
        "permissions": ["attendance.view_self", "leave.apply"],
    }
    user_read = UserRead.model_validate(user_data)
    assert user_read.permissions == ["attendance.view_self", "leave.apply"]


def test_organization_owner_has_analytics_but_no_operational_approval_permissions():
    permissions = FIXED_ROLE_PERMISSIONS["ORGANIZATION_OWNER"]
    assert "dashboard.view_organization" in permissions
    assert "reports.attendance" in permissions
    assert "leave.approve" not in permissions
    assert "overtime.approve" not in permissions
    assert "employee.update" not in permissions


def test_login_invalid_user_does_not_crash():
    """Ensure non-existent user login returns 400 and does NOT crash with 500 UnknownHashError."""
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/employee/login",
        data={"username": "9999999999", "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid login credentials"


def test_cors_preflight_allows_expo_web_origin():
    """Ensure OPTIONS preflight from Expo Web (localhost:8081) succeeds with 200."""
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.options(
        "/api/v1/dashboard/metrics",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8081"
