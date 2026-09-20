from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import fastapi_users, require_permission
from core.database import get_async_session
from db.models import Permission, Role, RolePermission, User, UserRoleAssignment
from schemas import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from schemas.roles import FIXED_BUSINESS_ROLES

router = APIRouter(prefix="/roles", tags=["roles"])


async def _role_response(role: Role, session: AsyncSession) -> RoleRead:
    permission_query = (
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
        .where(RolePermission.role_id == role.role_id)
        .order_by(Permission.permission_code)
    )
    permissions = (await session.execute(permission_query)).scalars().all()
    return RoleRead(
        role_id=role.role_id,
        role_name=role.role_name,
        description=role.description,
        is_system_role=role.is_system_role,
        permissions=[PermissionRead.model_validate(permission) for permission in permissions],
    )


@router.get("/permissions", response_model=list[PermissionRead])
async def list_permissions(
    _: User = Depends(require_permission("role.view")),
    session: AsyncSession = Depends(get_async_session),
) -> list[PermissionRead]:
    permissions = (await session.execute(select(Permission).order_by(Permission.permission_code))).scalars().all()
    return [PermissionRead.model_validate(permission) for permission in permissions]


@router.get("/", response_model=list[RoleRead])
async def list_roles(
    _: User = Depends(require_permission("role.view")),
    session: AsyncSession = Depends(get_async_session),
) -> list[RoleRead]:
    roles = (await session.execute(
        select(Role).where(Role.role_name.in_(FIXED_BUSINESS_ROLES)).order_by(Role.role_name)
    )).scalars().all()
    return [await _role_response(role, session) for role in roles]


@router.post("/", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    _: User = Depends(require_permission("role.create")),
    session: AsyncSession = Depends(get_async_session),
) -> RoleRead:
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Business roles are fixed")
    existing = await session.scalar(select(Role).where(Role.role_name == payload.role_name))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")

    permissions = (await session.execute(
        select(Permission).where(Permission.permission_code.in_(payload.permission_codes))
    )).scalars().all()
    found_codes = {permission.permission_code for permission in permissions}
    missing_codes = sorted(set(payload.permission_codes) - found_codes)
    if missing_codes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"unknown_permissions": missing_codes})

    role = Role(
        role_name=payload.role_name,
        description=payload.description,
        is_system_role=False,
    )
    session.add(role)
    await session.flush()
    session.add_all([RolePermission(role_id=role.role_id, permission_id=permission.permission_id) for permission in permissions])
    await session.commit()
    await session.refresh(role)
    return await _role_response(role, session)


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: int,
    payload: RoleUpdate,
    current_user: User = Depends(require_permission("role.update")),
    session: AsyncSession = Depends(get_async_session),
) -> RoleRead:
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Business roles are fixed")
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system_role and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super administrators can modify system roles",
        )
    if role.is_system_role and payload.role_name is not None and payload.role_name != role.role_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System role name cannot be changed")

    update_data = payload.model_dump(exclude_unset=True, exclude={"permission_codes"})
    for field, value in update_data.items():
        setattr(role, field, value)

    if payload.permission_codes is not None:
        permissions = (await session.execute(
            select(Permission).where(Permission.permission_code.in_(payload.permission_codes))
        )).scalars().all()
        found_codes = {permission.permission_code for permission in permissions}
        missing_codes = sorted(set(payload.permission_codes) - found_codes)
        if missing_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"unknown_permissions": missing_codes})
        await session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        session.add_all([RolePermission(role_id=role_id, permission_id=permission.permission_id) for permission in permissions])

    await session.commit()
    await session.refresh(role)
    return await _role_response(role, session)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    _: User = Depends(require_permission("role.delete")),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Business roles are fixed")
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System roles cannot be deleted")
    assigned = await session.scalar(select(UserRoleAssignment.role_id).where(UserRoleAssignment.role_id == role_id).limit(1))
    if assigned is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete role because it is currently assigned to one or more users.",
        )
    await session.delete(role)
    await session.commit()
