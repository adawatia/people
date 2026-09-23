from datetime import datetime
from typing import Literal

from fastapi_users.schemas import BaseUser, BaseUserCreate, BaseUserUpdate
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.pagination import PaginatedResponse
from core.mobile import normalize_indian_mobile


# User schemas. Business role and scope are ERP-owned fields on Employee.

# Elevated business role and the scope it applies to. The frontend uses these
# for role-specific experiences and scope-aware copy; authorization itself
# always comes from ``permissions`` plus the server-side row scope.
BusinessRoleName = Literal["DEPARTMENT_MANAGER", "HR_ADMIN", "ORGANIZATION_OWNER"]
AccessScopeName = Literal["SELF", "DEPARTMENT", "UNIT", "ORGANIZATION"]


class UserPermissionsResponse(BaseModel):
    permissions: list[str] = Field(default_factory=list, description="List of granted permission codes")


class UserRead(BaseUser[int]):
    id: int
    username: str
    first_name: str | None = None
    last_name: str | None = None
    mobile_number: str | None = None
    must_change_password: bool = False
    permissions: list[str] = Field(default_factory=list, description="Aggregated permissions for the user")
    created_by: int | None = None
    invitation_sent_at: datetime | None = None
    invitation_used_at: datetime | None = None
    employee_id: int | None = Field(default=None, description="Linked Employee ID if profile exists")
    employee_code: str | None = Field(default=None, description="Linked Employee Code if profile exists")
    role: Literal["EMPLOYEE", "DEPARTMENT_MANAGER", "HR_ADMIN", "ORGANIZATION_OWNER", "SUPER_ADMIN"] = "EMPLOYEE"
    business_role: BusinessRoleName | None = Field(
        default=None, description="Elevated business role; null means base employee access"
    )
    scope_type: AccessScopeName = Field(
        default="SELF", description="Where the business role applies (scope identifier is intentionally not exposed)"
    )

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
    role: Literal["EMPLOYEE", "DEPARTMENT_MANAGER", "HR_ADMIN", "ORGANIZATION_OWNER"] = Field(
        default="EMPLOYEE", description="Fixed business role"
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
            }
        },
    )

    @field_validator("mobile_number")
    @classmethod
    def normalize_mobile(cls, value: str | None) -> str | None:
        return normalize_indian_mobile(value)


class UserCreateRequest(UserCreate):
    """Legacy user payload; accounts use a supplied temporary password."""


class UserUpdate(BaseUserUpdate):
    username: str | None = Field(default=None, examples=["johndoe"])
    first_name: str | None = Field(default=None, examples=["John"])
    last_name: str | None = Field(default=None, examples=["Doe"])
    mobile_number: str | None = Field(default=None, examples=["+919876543210"])
    must_change_password: bool | None = Field(default=None)
    created_by: int | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("mobile_number")
    @classmethod
    def normalize_mobile(cls, value: str | None) -> str | None:
        return normalize_indian_mobile(value)


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
