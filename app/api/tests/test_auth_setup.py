import asyncio
import selectors
import sys

from sqlalchemy import func, select

from core.auth import setup_rate_limits
from db.models import Role, User, UserRoleAssignment
from db.seed import ensure_seed_data


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


def test_ensure_seed_data_creates_roles_and_super_admin(monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "seedadmin@hrms.com")
    monkeypatch.setenv("SUPER_ADMIN_USERNAME", "seedadmin")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "SeedAdmin@123")
    monkeypatch.setenv("SUPER_ADMIN_FIRST_NAME", "Seed")
    monkeypatch.setenv("SUPER_ADMIN_LAST_NAME", "Admin")

    run_async(ensure_seed_data())

    from core.database import async_session_maker

    async def _read_seed() -> None:
        async with async_session_maker() as session:
            from sqlalchemy.orm import selectinload
            role_count = await session.scalar(select(func.count()).select_from(Role))
            user = await session.scalar(
                select(User)
                .options(selectinload(User.role_assignments))
                .where(User.email == "seedadmin@hrms.com")
            )
            assert role_count >= 1
            assert user is not None
            assert user.is_superuser is True
            assert len(user.role_assignments) >= 1

    run_async(_read_seed())


def test_ensure_seed_data_keeps_only_one_super_admin(monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "admin@hrms.com")
    monkeypatch.setenv("SUPER_ADMIN_USERNAME", "superadmin")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "SuperAdmin@123")
    monkeypatch.setenv("SUPER_ADMIN_FIRST_NAME", "Super")
    monkeypatch.setenv("SUPER_ADMIN_LAST_NAME", "Admin")

    from core.database import async_session_maker

    async def _seed_duplicate_users() -> None:
        async with async_session_maker() as session:
            super_role = await session.scalar(select(Role).where(Role.role_name == "SUPER_ADMIN"))
            if super_role is None:
                raise AssertionError("SUPER_ADMIN role missing")

            helper = __import__("fastapi_users.password", fromlist=["PasswordHelper"]).PasswordHelper()
            session.add_all(
                [
                    User(
                        email="legacy-admin@hrms.com",
                        username="legacyadmin",
                        first_name="Legacy",
                        last_name="Admin",
                        hashed_password=helper.hash("LegacyAdmin@123"),
                        is_active=True,
                        is_verified=True,
                        is_superuser=True,
                        role_assignments=[UserRoleAssignment(role_id=super_role.role_id, scope_type="organization")],
                    ),
                    User(
                        email="admin@hrms.com",
                        username="superadmin",
                        first_name="Super",
                        last_name="Admin",
                        hashed_password=helper.hash("SuperAdmin@123"),
                        is_active=True,
                        is_verified=True,
                        is_superuser=True,
                        role_assignments=[UserRoleAssignment(role_id=super_role.role_id, scope_type="organization")],
                    ),
                ]
            )
            await session.commit()

    run_async(_seed_duplicate_users())
    run_async(ensure_seed_data())

    async def _read_result() -> None:
        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(User).where(
                        (User.is_superuser.is_(True))
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].email == "admin@hrms.com"
            assert rows[0].username == "superadmin"

    run_async(_read_result())


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
        "assignments": [
            {
                "id": 1,
                "role_id": 5,
                "role_name": "EMPLOYEE",
                "scope_type": "organization"
            }
        ]
    }
    user_read = UserRead.model_validate(user_data)
    assert user_read.permissions == ["attendance.view_self", "leave.apply"]
    assert len(user_read.assignments) == 1
    assert user_read.assignments[0].role_name == "EMPLOYEE"


def test_seed_definitions_cover_srs_permissions():
    from db.seed import PERMISSION_DEFINITIONS, ROLE_PERMISSIONS

    # Ensure SRS key permissions are present
    assert "attendance.view_self" in PERMISSION_DEFINITIONS
    assert "attendance.view_department" in PERMISSION_DEFINITIONS
    assert "attendance.view_unit" in PERMISSION_DEFINITIONS
    assert "attendance.dispute" in PERMISSION_DEFINITIONS
    assert "leave.apply" in PERMISSION_DEFINITIONS
    assert "leave.reject" in PERMISSION_DEFINITIONS
    assert "leave.cancel" in PERMISSION_DEFINITIONS
    assert "salary_cost.view_department" in PERMISSION_DEFINITIONS
    assert "salary_cost.view_unit" in PERMISSION_DEFINITIONS
    assert "employee.view_self" in PERMISSION_DEFINITIONS
    assert "employee.deactivate" in PERMISSION_DEFINITIONS

    # Ensure SUPER_ADMIN gets all defined permissions
    assert ROLE_PERMISSIONS["SUPER_ADMIN"] == set(PERMISSION_DEFINITIONS)


def test_login_invalid_user_does_not_crash():
    """Ensure non-existent user login returns 400 and does NOT crash with 500 UnknownHashError."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "nonexistent@example.com", "password": "WrongPassword123!"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"


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

