from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationBase(BaseModel):
    title: str = Field(..., max_length=150, description="Short notification title")
    message: str = Field(..., max_length=1000, description="Notification message details")
    notification_type: str = Field(..., max_length=50, description="Type: e.g. leave_applied, leave_approved, attendance_correction, system")
    reference_id: int | None = Field(default=None, description="Linked entity ID")
    reference_type: str | None = Field(default=None, max_length=50, description="Linked entity type")
    link: str | None = Field(default=None, max_length=255, description="Client route path")

    model_config = ConfigDict(from_attributes=True)


class NotificationCreate(NotificationBase):
    user_id: int | None = None
    target_role: str | None = None


class NotificationRead(NotificationBase):
    notification_id: int
    user_id: int | None = None
    target_role: str | None = None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUnreadCount(BaseModel):
    unread_count: int = Field(default=0, description="Total unread notifications for current user context")


class NotificationMarkRead(BaseModel):
    is_read: bool = True
