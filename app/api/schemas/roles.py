from pydantic import BaseModel, ConfigDict, Field

from core.pagination import PaginatedResponse


class PermissionRead(BaseModel):
    permission_id: int
    permission_code: str
    name: str
    description: str | None = None
    is_system_permission: bool = True

    model_config = ConfigDict(from_attributes=True)


class RoleBase(BaseModel):
    role_name: str = Field(..., min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    is_system_role: bool = False


class RoleCreate(RoleBase):
    """Only callable by Super Admin. Defines a new generic role and its permission set."""
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    """Only callable by Super Admin. Modifies a role's name, description, or permissions."""
    role_name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] | None = None


class RoleAssignment(BaseModel):
    """Legacy: assign role_ids to a user (flat, no scope). Prefer UserRoleAssignment for new code."""
    role_ids: list[int] = Field(default_factory=list, min_length=1)


class UserRoleAssignmentCreate(BaseModel):
    """
    Admin-callable: assign an *existing* role to a user with a scope.
    Only Super Admin can create new role definitions (RoleCreate).
    Admin can only assign roles that already exist.
    """
    role_id: int = Field(..., description="ID of an existing role to assign")
    scope_type: str = Field(default="organization", description="organization | unit | department")
    scope_id: int | None = Field(default=None, description="Unit or Department ID; null for org-wide")


class UserRoleAssignmentRead(BaseModel):
    id: int
    user_id: int
    role_id: int
    role_name: str | None = None
    scope_type: str
    scope_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class RoleRead(RoleBase):
    role_id: int
    permissions: list[PermissionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


PaginatedRolesResponse = PaginatedResponse[RoleRead]
