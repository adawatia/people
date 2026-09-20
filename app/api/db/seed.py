import os

from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from core.database import async_session_maker
from core.database import auth_engine as engine
from db.models import Base, Permission, Role, RolePermission, User, UserRoleAssignment


async def create_db_and_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


ROLE_DEFINITIONS = {
    "SUPER_ADMIN": {
        "description": "Platform-wide technical administrator. Owns RBAC shape and system config.",
        "is_system_role": True,
    },
    "ADMIN": {
        "description": "Org-level administrator. Manages people, units, and role assignments.",
        "is_system_role": False,
    },
    "HR_OWNER": {
        "description": "Head of HR. Full HR access org-wide (payroll, compliance, reports).",
        "is_system_role": False,
    },
    "HR_MANAGER": {
        "description": "Unit-level HR operations: leave, attendance, onboarding.",
        "is_system_role": False,
    },
    "UNIT_HEAD": {
        "description": "Manages all departments and employees within one Unit.",
        "is_system_role": False,
    },
    "DEPARTMENT_HEAD": {
        "description": "Department-level manager. Approves leave, reviews performance.",
        "is_system_role": False,
    },
    "EMPLOYEE": {
        "description": "Standard employee with self-service access. Everyone gets this base role.",
        "is_system_role": False,
    },
}

PERMISSION_DEFINITIONS = {
    # Roles & Users RBAC
    "role.view": "View roles and permissions",
    "role.create": "Create roles",
    "role.update": "Update roles and permissions",
    "role.delete": "Delete roles",
    "role.assign": "Assign roles to users",
    "user.view": "View user accounts",
    "user.create": "Create user accounts",
    "user.update": "Update user accounts",
    "user.deactivate": "Activate or deactivate users",

    # Employees
    "employee.view_self": "View own employee profile",
    "employee.view": "View employee records",
    "employee.create": "Create employee records",
    "employee.update": "Update employee records",
    "employee.deactivate": "Deactivate employee records",

    # Designations
    "designation.view": "View designations",
    "designation.create": "Create designations",
    "designation.update": "Update designations",
    "designation.delete": "Delete designations",

    # Attendance & Punches
    "attendance.view_self": "View own attendance",
    "attendance.view": "View organization-wide attendance records",
    "attendance.view_department": "View department attendance records",
    "attendance.view_unit": "View unit attendance records",
    "attendance.correct": "Submit or enter attendance corrections",
    "attendance.dispute": "Raise attendance dispute or complaint",
    "attendance.approve_correction": "Approve attendance corrections",
    "attendance.process": "Execute automated attendance processing",

    # Leaves
    "leave.apply": "Apply for leave",
    "leave.view_self": "View own leave",
    "leave.approve": "Approve leave requests",
    "leave.reject": "Reject leave requests",
    "leave.cancel": "Cancel or withdraw leave requests",
    "leave.manage": "Manage leave policies and configuration",

    # Shifts
    "shift.view_self": "View own shifts",
    "shift.assign": "Assign employee shifts",
    "shift.update": "Update shift configurations",

    # Overtime
    "overtime.view_self": "View own overtime",
    "overtime.view_department": "View department overtime",
    "overtime.approve": "Approve overtime hours",

    # Salary & Workforce Costs
    "salary_cost.view_department": "View department salary and overtime cost",
    "salary_cost.view_unit": "View unit salary and overtime cost",

    # Reports
    "reports.view": "View HR reports",
    "reports.attendance": "View attendance reports",
    "reports.leave": "View leave reports",
    "reports.overtime": "View overtime reports",
    "reports.salary_cost": "View salary and overtime cost reports",

    # Audit & System
    "audit.view": "View audit logs",
    "system.configure": "Manage system configuration",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "SUPER_ADMIN": set(PERMISSION_DEFINITIONS),
    "ADMIN": {
        "role.view", "role.assign",
        "user.view", "user.create", "user.update", "user.deactivate",
        "employee.view", "employee.create", "employee.update", "employee.deactivate",
        "designation.view", "designation.create", "designation.update", "designation.delete",
        "attendance.view", "attendance.view_unit", "attendance.view_department",
        "leave.manage", "leave.approve", "leave.reject",
        "shift.assign", "shift.update",
        "overtime.approve", "overtime.view_department",
        "salary_cost.view_unit", "salary_cost.view_department",
        "reports.view", "reports.attendance", "reports.leave", "reports.overtime", "reports.salary_cost",
        "audit.view",
    },
    "HR_OWNER": {
        "role.view", "user.view",
        "employee.view", "employee.create", "employee.update", "employee.deactivate",
        "designation.view", "designation.create", "designation.update",
        "attendance.view", "attendance.view_unit", "attendance.view_department",
        "attendance.correct", "attendance.approve_correction", "attendance.process",
        "leave.manage", "leave.approve", "leave.reject", "leave.cancel",
        "shift.assign", "shift.update",
        "overtime.approve", "overtime.view_department",
        "salary_cost.view_unit", "salary_cost.view_department",
        "reports.view", "reports.attendance", "reports.leave", "reports.overtime", "reports.salary_cost",
        "audit.view",
    },
    "HR_MANAGER": {
        "user.view", "employee.view", "employee.create", "employee.update",
        "designation.view",
        "attendance.view_unit", "attendance.view_department",
        "attendance.correct", "attendance.approve_correction", "attendance.process",
        "leave.manage", "leave.approve", "leave.reject", "leave.cancel",
        "shift.assign", "shift.update",
        "overtime.approve", "overtime.view_department",
        "salary_cost.view_unit", "salary_cost.view_department",
        "reports.view", "reports.attendance", "reports.leave", "reports.overtime", "reports.salary_cost",
    },
    "UNIT_HEAD": {
        "user.view", "employee.view",
        "designation.view",
        "attendance.view_unit", "attendance.view_department", "attendance.approve_correction",
        "leave.approve", "leave.reject",
        "overtime.view_department", "overtime.approve",
        "salary_cost.view_unit", "salary_cost.view_department",
        "reports.view", "reports.attendance", "reports.leave", "reports.overtime",
    },
    "DEPARTMENT_HEAD": {
        "employee.view",
        "designation.view",
        "attendance.view_department", "attendance.approve_correction",
        "leave.approve", "leave.reject",
        "overtime.view_department", "overtime.approve",
        "salary_cost.view_department",
        "reports.view", "reports.attendance", "reports.leave", "reports.overtime",
    },
    "EMPLOYEE": {
        "employee.view_self",
        "attendance.view_self", "attendance.dispute",
        "leave.apply", "leave.view_self", "leave.cancel",
        "shift.view_self",
        "overtime.view_self",
    },
}


async def ensure_seed_data() -> None:
    await create_db_and_tables()

    async with async_session_maker() as session:
        for role_name, payload in ROLE_DEFINITIONS.items():
            existing_role = await session.scalar(
                select(Role).where(Role.role_name == role_name)
            )
            if existing_role is None:
                session.add(
                    Role(
                        role_name=role_name,
                        description=payload["description"],
                        **{k: v for k, v in payload.items() if k != "description"},
                    )
                )
            else:
                existing_role.description = payload["description"]
                for k, v in payload.items():
                    if k != "description":
                        setattr(existing_role, k, v)

        await session.flush()

        permissions: dict[str, Permission] = {}
        for permission_code, description in PERMISSION_DEFINITIONS.items():
            permission = await session.scalar(
                select(Permission).where(Permission.permission_code == permission_code)
            )
            if permission is None:
                permission = Permission(
                    permission_code=permission_code,
                    name=permission_code.replace(".", " ").title(),
                    description=description,
                    is_system_permission=True,
                )
                session.add(permission)
                await session.flush()
            permissions[permission_code] = permission

        for role_name, permission_codes in ROLE_PERMISSIONS.items():
            role = await session.scalar(select(Role).where(Role.role_name == role_name))
            if role is None:
                continue
            existing_links = {
                link.permission_id
                for link in (await session.execute(select(RolePermission).where(RolePermission.role_id == role.role_id))).scalars()
            }
            for permission_code in permission_codes:
                permission = permissions[permission_code]
                if permission.permission_id not in existing_links:
                    session.add(RolePermission(role_id=role.role_id, permission_id=permission.permission_id))

        super_admin_email = os.getenv("SUPER_ADMIN_EMAIL", "admin@hrms.com")
        super_admin_username = os.getenv("SUPER_ADMIN_USERNAME", "superadmin")
        super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD", "SuperAdmin@123")
        super_admin_first_name = os.getenv("SUPER_ADMIN_FIRST_NAME", "Super")
        super_admin_last_name = os.getenv("SUPER_ADMIN_LAST_NAME", "Admin")

        super_role = await session.scalar(select(Role).where(Role.role_name == "SUPER_ADMIN"))
        if super_role is None:
            raise RuntimeError("Super Admin role not found after seeding")

        canonical_user = await session.scalar(
            select(User).where(
                (User.email == super_admin_email)
                | (User.username == super_admin_username)
            )
        )

        if canonical_user is None:
            canonical_user = await session.scalar(
                select(User).where(User.is_superuser.is_(True)).order_by(User.id.asc())
            )

        if canonical_user is None:
            helper = PasswordHelper()
            canonical_user = User(
                email=super_admin_email,
                username=super_admin_username,
                first_name=super_admin_first_name,
                last_name=super_admin_last_name,
                hashed_password=helper.hash(super_admin_password),
                created_by=None,
                is_active=True,
                is_verified=True,
                is_superuser=True,
            )
            session.add(canonical_user)
            await session.flush()
        else:
            canonical_user.email = super_admin_email
            canonical_user.username = super_admin_username
            canonical_user.must_change_password = False
            canonical_user.is_superuser = True
            canonical_user.is_active = True
            canonical_user.is_verified = True
            canonical_user.first_name = super_admin_first_name
            canonical_user.last_name = super_admin_last_name
            helper = PasswordHelper()
            canonical_user.hashed_password = helper.hash(super_admin_password)

        legacy_users = await session.execute(
            select(User).where(
                User.id != canonical_user.id if canonical_user is not None else False
            )
        )
        for legacy in legacy_users.scalars().all():
            if legacy.is_superuser:
                await session.delete(legacy)
        await session.flush()
        
        # 3. Handle assignments
        # Ensure Super Admin has a scoped UserRoleAssignment (org-wide)
        if canonical_user is not None:
            existing_dyn = await session.scalar(
                select(UserRoleAssignment).where(
                    UserRoleAssignment.user_id == canonical_user.id,
                    UserRoleAssignment.role_id == super_role.role_id,
                    UserRoleAssignment.scope_type == "organization",
                )
            )
            if existing_dyn is None:
                session.add(
                    UserRoleAssignment(
                        user_id=canonical_user.id,
                        role_id=super_role.role_id,
                        scope_type="organization",
                        scope_id=None,
                        assigned_by=None,
                    )
                )

        await session.commit()
