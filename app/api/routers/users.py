import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi_users import exceptions as fu_exceptions
from fastapi_users.router.common import ErrorCode
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import schemas
from core.auth import (
    UserManager,
    fastapi_users,
    get_user_manager,
    get_user_permissions,
    require_permission,
    user_has_permission,
)
from core.database import get_async_session
from core.email import get_email_service
from core.invitation import create_invitation_for_user
from core.pagination import PaginationParams, paginate
from core.settings import get_settings
from db.models import Employee, Role, User, UserRoleAssignment
from schemas import (
    PaginatedUsersResponse,
    UserPermissionsResponse,
    UserRead,
    UserStats,
    UserUpdate,
    RoleAssignmentRead,
)
from schemas.roles import UserRoleAssignmentCreate, UserRoleAssignmentRead
from core.rbac import get_effective_permissions as rbac_get_effective_permissions, has_permission as rbac_has_permission

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
    summary="Create a new user (Authorized Only)",
    description=(
        "Create a new user account. Public registration is disabled.\n\n"
        "Dynamic RBAC is enforced: requires 'user.create' permission to create users "
        "and 'role.assign' permission to assign roles.\n\n"
        "**Password Requirements:**\n"
        "- Minimum 12 characters.\n"
        "- At least 1 uppercase, 1 lowercase, 1 number, and 1 special character.\n"
        "- Must not contain the user's name or email.\n"
        "- Must pass a `zxcvbn` strength score check >= 3."
    ),
    response_description="The newly created user profile.",
)
async def create_user(
    request: Request,
    user_request: schemas.UserCreateRequest,
    user_manager: UserManager = Depends(get_user_manager),
    current_user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
):
    if not await user_has_permission(current_user, "user.create", session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: user.create")

    # Validate role assignments
    role_assignments = user_request.role_assignments
    if role_assignments and not await user_has_permission(current_user, "role.assign", session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: role.assign")
        
    role_ids = {a.role_id for a in role_assignments}
    roles = []
    if role_ids:
        roles = (await session.execute(select(Role).where(Role.role_id.in_(role_ids)))).scalars().all()
        if len(roles) != len(role_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more roles do not exist")

    # Check for SUPER_ADMIN assignment
    has_super_admin_assignment = any(r.role_name == "SUPER_ADMIN" for r in roles)
    if has_super_admin_assignment and not current_user.is_superuser:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Admins can assign the SUPER_ADMIN role.",
        )

    user_dict = user_request.model_dump(exclude={"send_invitation", "role_assignments"}, exclude_unset=True)
    user_dict["created_by"] = current_user.id
    user_dict["is_superuser"] = bool(current_user.is_superuser and has_super_admin_assignment)

    send_invitation = getattr(user_request, "send_invitation", True)
    has_custom_password = bool(user_dict.get("password"))
    if not has_custom_password:
        # Generate a cryptographically strong random password meeting all complexity & zxcvbn requirements
        user_dict["password"] = f"{secrets.token_urlsafe(24)}!Aa9"
    elif not send_invitation:
        # Admin is setting the password directly. Force the user to change it.
        user_dict["must_change_password"] = True

    user_create = schemas.UserCreate(**user_dict)

    try:
        created_user = await user_manager.create(user_create, safe=False, request=request)
    except fu_exceptions.InvalidPasswordException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ErrorCode.REGISTER_INVALID_PASSWORD, "reason": e.reason},
        )
    except fu_exceptions.UserAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.REGISTER_USER_ALREADY_EXISTS,
        )

    # Create scoped role assignments
    if role_assignments:
        assignments_to_add = [
            UserRoleAssignment(
                user_id=created_user.id,
                role_id=a.role_id,
                scope_type=a.scope_type,
                scope_id=a.scope_id,
                assigned_by=current_user.id
            )
            for a in role_assignments
        ]
        session.add_all(assignments_to_add)

    raw_invite_token = None
    if not has_custom_password or send_invitation:
        raw_invite_token = create_invitation_for_user(created_user)
        created_user.is_verified = False

    await session.commit()
    await session.refresh(created_user)

    if raw_invite_token:
        email_svc = get_email_service()
        settings = get_settings()
        frontend_url = (settings.frontend_url or "http://localhost:3000").rstrip("/")
        invite_url = f"{frontend_url}/auth/invitation?token={raw_invite_token}"
        role_names = ", ".join([r.role_name for r in roles]) if roles else "Standard User"
        user_name = created_user.first_name or created_user.username
        asyncio.create_task(
            email_svc.send_user_invitation_email(
                to_email=created_user.email,
                user_name=user_name,
                username=created_user.username,
                role_name=role_names,
                invite_url=invite_url,
            )
        )

    permissions = await get_user_permissions(created_user, session)
    user_read = UserRead.model_validate(created_user)
    user_read.permissions = permissions
    return user_read


@router.post(
    "/{user_id}/resend-invitation",
    summary="Resend an invitation email to a user",
    tags=["users"],
)
async def resend_user_invitation(
    user_id: int,
    current_user: User = Depends(require_permission("user.create")),
    session: AsyncSession = Depends(get_async_session),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.invitation_used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user has already accepted their invitation and activated their account.",
        )

    # Get primary role for email context
    role_name = "Standard User"
    if user.role_assignments:
        first_role = await session.get(Role, user.role_assignments[0].role_id)
        if first_role:
            role_name = first_role.role_name

    raw_token = create_invitation_for_user(user)
    await session.commit()

    email_svc = get_email_service()
    settings = get_settings()
    frontend_url = (settings.frontend_url or "http://localhost:3000").rstrip("/")
    invite_url = f"{frontend_url}/auth/invitation?token={raw_token}"
    user_name = user.first_name or user.username

    asyncio.create_task(
        email_svc.send_user_invitation_email(
            to_email=user.email,
            user_name=user_name,
            username=user.username,
            role_name=role_name,
            invite_url=invite_url,
        )
    )

    return {"message": f"Invitation resent successfully to {user.email}."}


@router.get(
    "/stats",
    response_model=UserStats,
    tags=["users"],
    summary="Get user management summary metrics",
)
async def get_user_stats(
    current_user: User = Depends(require_permission("user.view")),
    session: AsyncSession = Depends(get_async_session),
):
    base_filter = []

    # 1. Total users
    total_q = select(func.count(User.id))
    if base_filter:
        total_q = total_q.where(*base_filter)
    total_users = (await session.scalar(total_q)) or 0

    # 2. Active users
    active_q = select(func.count(User.id)).where(User.is_active.is_(True))
    if base_filter:
        active_q = active_q.where(*base_filter)
    active_users = (await session.scalar(active_q)) or 0

    # 3. Inactive users
    inactive_q = select(func.count(User.id)).where(User.is_active.is_(False))
    if base_filter:
        inactive_q = inactive_q.where(*base_filter)
    inactive_users = (await session.scalar(inactive_q)) or 0

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
    }


@router.get(
    "/",
    response_model=PaginatedUsersResponse,
    tags=["users"],
    summary="List users (Paginated with search & filters)",
)
async def list_users(
    request: Request,
    pagination: PaginationParams = Depends(),
    search: str | None = Query(None, description="Search by name, email, or username"),
    role_id: int | None = Query(None, description="Filter by role ID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_user: User = Depends(require_permission("user.view")),
    session: AsyncSession = Depends(get_async_session),
):
    query = select(User).options(
        selectinload(User.role_assignments).selectinload(UserRoleAssignment.role),
    )

    # 2. Server-side search filter
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.where(
            or_(
                User.email.ilike(search_term),
                User.username.ilike(search_term),
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
            )
        )

    if role_id is not None:
        query = query.join(UserRoleAssignment).where(UserRoleAssignment.role_id == role_id)

    # 4. Server-side active status filter
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    return await paginate(
        session=session,
        query=query.order_by(User.id),
        page=pagination.page,
        page_size=pagination.page_size,
        all_records=pagination.all,
    )


@router.get("/me", response_model=UserRead, tags=["users"], summary="Get current user profile with dynamic permissions")
async def get_current_user_me(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UserRead:
    refreshed_user = await session.scalar(
        select(User)
        .options(
            selectinload(User.role_assignments).selectinload(UserRoleAssignment.role),
        )
        .where(User.id == user.id)
    )
    target_user = refreshed_user or user
    permissions = await get_user_permissions(target_user, session)

    user_read = UserRead.model_validate(target_user)
    user_read.permissions = permissions

    employee = await session.scalar(
        select(Employee).where(Employee.user_id == target_user.id).limit(1)
    )
    if employee:
        user_read.employee_id = employee.id
        user_read.employee_code = employee.employee_code

    return user_read


@router.get("/me/permissions", response_model=UserPermissionsResponse, tags=["users"], summary="Get current user permissions list")
async def get_current_user_permissions(
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(get_async_session),
) -> UserPermissionsResponse:
    permissions = await get_user_permissions(user, session)
    return UserPermissionsResponse(permissions=permissions)


# ---------------------------------------------------------------------------
# Scoped Role Assignment endpoints (Dynamic RBAC)
# ---------------------------------------------------------------------------

@router.get(
    "/{user_id}/assignments",
    response_model=list[UserRoleAssignmentRead],
    summary="List a user's scoped role assignments",
    tags=["users", "rbac"],
)
async def list_user_assignments(
    user_id: int,
    current_user: User = Depends(require_permission("user.view")),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(UserRoleAssignment)
        .options(selectinload(UserRoleAssignment.role))
        .where(UserRoleAssignment.user_id == user_id)
    )
    assignments = result.scalars().all()
    return [
        UserRoleAssignmentRead(
            id=a.id,
            user_id=a.user_id,
            role_id=a.role_id,
            role_name=a.role.role_name if a.role else None,
            scope_type=a.scope_type,
            scope_id=a.scope_id,
        )
        for a in assignments
    ]


@router.post(
    "/{user_id}/assignments",
    response_model=UserRoleAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a scoped role to a user (Admin+ required)",
    description=(
        "Requires `role.assign` permission. **Admins** can assign existing roles with scopes. "
        "They cannot create new roles — only Super Admin can do that via `POST /roles`."
    ),
    tags=["users", "rbac"],
)
async def create_user_assignment(
    user_id: int,
    payload: UserRoleAssignmentCreate,
    current_user: User = Depends(require_permission("role.assign")),
    session: AsyncSession = Depends(get_async_session),
):
    target_user = await session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    target_role = await session.get(Role, payload.role_id)
    if not target_role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not found.")

    # Prevent granting a system role (SUPER_ADMIN) unless caller is superuser
    if target_role.role_name == "SUPER_ADMIN" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Admins can assign the SUPER_ADMIN role.",
        )

    assignment = UserRoleAssignment(
        user_id=user_id,
        role_id=payload.role_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        assigned_by=current_user.id,
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)

    return UserRoleAssignmentRead(
        id=assignment.id,
        user_id=assignment.user_id,
        role_id=assignment.role_id,
        role_name=target_role.role_name,
        scope_type=assignment.scope_type,
        scope_id=assignment.scope_id,
    )


@router.delete(
    "/{user_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a scoped role assignment from a user",
    tags=["users", "rbac"],
)
async def delete_user_assignment(
    user_id: int,
    assignment_id: int,
    current_user: User = Depends(require_permission("role.assign")),
    session: AsyncSession = Depends(get_async_session),
):
    assignment = await session.get(UserRoleAssignment, assignment_id)
    if not assignment or assignment.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    await session.delete(assignment)
    await session.commit()

