"""Pydantic schemas exposed by the fixed-role HRMS API."""

from schemas.common import PaginatedResponse
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
from schemas.notifications import (
    NotificationBase,
    NotificationCreate,
    NotificationMarkRead,
    NotificationRead,
    NotificationUnreadCount,
)

__all__ = [
    "PaginatedResponse",
    "UserRead",
    "UserPermissionsResponse",
    "UserCreate",
    "UserCreateRequest",
    "UserUpdate",
    "SetPasswordRequest",
    "ValidateInvitationResponse",
    "UserStats",
    "PaginatedUsersResponse",
    "NotificationBase",
    "NotificationCreate",
    "NotificationRead",
    "NotificationUnreadCount",
    "NotificationMarkRead",
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
