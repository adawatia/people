from datetime import datetime
from typing import Literal

from fastapi_users.schemas import BaseUser, BaseUserCreate, BaseUserUpdate
from pydantic import BaseModel, ConfigDict, Field

from core.pagination import PaginatedResponse


# ---------------------------------------------------------------------------
# Role Assignment schemas (Dynamic RBAC — sole mechanism, no legacy role_id)
# ---------------------------------------------------------------------------

class RoleAssignmentRead(BaseModel):
    id: int
    role_id: int
    role_name: str | None = None
    scope_type: str = "organization"  # organization | unit | department
    scope_id: int | None = None
    assigned_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RoleAssignmentCreate(BaseModel):
    role_id: int = Field(..., description="ID of the role to assign")
    scope_type: Literal["organization", "unit", "department"] = Field(
        default="organization", description="Scope level for the assignment"
    )
    scope_id: int | None = Field(
        default=None, description="Unit or Department ID; null for org-wide assignments"
    )


# ---------------------------------------------------------------------------
# User schemas — clean, no legacy role_id fields
# ---------------------------------------------------------------------------

class UserPermissionsResponse(BaseModel):
    permissions: list[str] = Field(default_factory=list, description="List of granted permission codes")


class UserRead(BaseUser[int]):
    id: int
    username: str
    first_name: str | None = None
    last_name: str | None = None
    mobile_number: str | None = None
    must_change_password: bool = False
    # Scoped RBAC assignments (the only role mechanism)
    assignments: list[RoleAssignmentRead] = Field(default_factory=list, description="Scoped role assignments")
    permissions: list[str] = Field(default_factory=list, description="Aggregated permissions for the user")
    created_by: int | None = None
    invitation_sent_at: datetime | None = None
    invitation_used_at: datetime | None = None
    employee_id: int | None = Field(default=None, description="Linked Employee ID if profile exists")
    employee_code: str | None = Field(default=None, description="Linked Employee Code if profile exists")

    @property
    def is_invitation_pending(self) -> bool:
        return bool(self.invitation_sent_at and not self.invitation_used_at)

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseUserCreate):
    username: str = Field(..., min_length=3, max_length=50, examples=["johndoe"], description="Unique login username")
    password: str | None = Field(default=None, min_length=8, examples=["SecurePass123!"], description="Password")
    email: str = Field(..., max_length=255, examples=["john.doe@example.com"], description="User email address")
    first_name: str = Field(..., min_length=1, max_length=100, examples=["John"], description="User first name")
    last_name: str | None = Field(default=None, max_length=100, examples=["Doe"], description="User last name")
    mobile_number: str | None = Field(default=None, max_length=20, examples=["+919876543210"], description="E.164 mobile number (optional, usable for login)")
    must_change_password: bool = Field(default=False, description="Force password change on first login")
    # Scoped role assignments at creation time
    role_assignments: list[RoleAssignmentCreate] = Field(
        default_factory=list, description="Scoped role+scope assignments for this user"
    )
    created_by: int | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "john.doe@example.com",
                "username": "johndoe",
                "password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe",
                "mobile_number": "+919876543210",
                "is_active": True,
                "role_assignments": [
                    {"role_id": 1, "scope_type": "organization"}
                ],
            }
        },
    )


class UserCreateRequest(UserCreate):
    """Request body for admin-created users. Extends UserCreate with invitation flow options."""
    send_invitation: bool = Field(
        default=True,
        description="If True, sends invitation email so user sets their own password. If False with password provided, admin sets password directly and must_change_password is auto-set True."
    )


class UserUpdate(BaseUserUpdate):
    username: str | None = Field(default=None, examples=["johndoe"])
    first_name: str | None = Field(default=None, examples=["John"])
    last_name: str | None = Field(default=None, examples=["Doe"])
    mobile_number: str | None = Field(default=None, examples=["+919876543210"])
    must_change_password: bool | None = Field(default=None)
    created_by: int | None = None

    model_config = ConfigDict(from_attributes=True)


class SetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, description="Invitation token")
    password: str = Field(..., min_length=12, description="New password")


class ValidateInvitationResponse(BaseModel):
    valid: bool
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    role_name: str | None = None
    detail: str | None = None


class UserStats(BaseModel):
    total_users: int = Field(default=0, description="Total number of users in scope")
    active_users: int = Field(default=0, description="Active user count")
    inactive_users: int = Field(default=0, description="Inactive user count")

    model_config = ConfigDict(from_attributes=True)


PaginatedUsersResponse = PaginatedResponse[UserRead]
