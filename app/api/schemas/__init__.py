"""HRMS - Pydantic Schemas Package (reusable foundation).

Kept for attached HRMS project:
- schemas.roles: dynamic RBAC roles
- schemas.users: user profile, management, invitation and auth schemas
- schemas.notifications: in-app notifications
- schemas.common: common pagination primitives

Removed (BSL vendor-portal domain, not usable for HRMS):
- schemas.parties / bsl_units / challans / sub_challans
"""

from schemas.common import PaginatedResponse
from schemas.roles import (
    PaginatedRolesResponse,
    PermissionRead,
    RoleAssignment,
    RoleBase,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)
from schemas.users import (
    PaginatedUsersResponse,
    RoleAssignmentCreate,
    RoleAssignmentRead,
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
    "RoleBase",
    "RoleRead",
    "RoleCreate",
    "RoleUpdate",
    "PaginatedRolesResponse",
    "PermissionRead",
    "RoleAssignment",
    "UserRead",
    "UserPermissionsResponse",
    "UserCreate",
    "UserCreateRequest",
    "UserUpdate",
    "RoleAssignmentRead",
    "RoleAssignmentCreate",
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

from .org import OrganizationBase, OrganizationRead, UnitBase, UnitCreate, UnitUpdate, UnitRead, DepartmentBase, DepartmentCreate, DepartmentUpdate, DepartmentRead
