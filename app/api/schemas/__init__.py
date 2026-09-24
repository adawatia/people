"""Pydantic schemas exposed by the fixed-role HRMS API."""

from schemas.common import PaginatedResponse
from schemas.notifications import (
    NotificationBase,
    NotificationCreate,
    NotificationMarkRead,
    NotificationRead,
    NotificationUnreadCount,
)
from schemas.users import (
    PaginatedUsersResponse,
    SetPasswordRequest,
    UserCreate,
    UserCreateRequest,
    UserPermissionsResponse,
    UserRead,
    UserStats,
    UserUpdate,
    ValidateInvitationResponse,
)

__all__ = [
    "NotificationBase",
    "NotificationCreate",
    "NotificationMarkRead",
    "NotificationRead",
    "NotificationUnreadCount",
    "PaginatedResponse",
    "PaginatedUsersResponse",
    "SetPasswordRequest",
    "UserCreate",
    "UserCreateRequest",
    "UserPermissionsResponse",
    "UserRead",
    "UserStats",
    "UserUpdate",
    "ValidateInvitationResponse",
]

from .org import (
    DepartmentBase,
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    OrganizationBase,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    UnitBase,
    UnitCreate,
    UnitRead,
    UnitUpdate,
)

__all__ += ['DepartmentBase', 'DepartmentCreate', 'DepartmentRead', 'DepartmentUpdate', 'OrganizationBase', 'OrganizationCreate', 'OrganizationRead', 'OrganizationUpdate', 'UnitBase', 'UnitCreate', 'UnitRead', 'UnitUpdate']
