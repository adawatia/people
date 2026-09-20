from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class WorkArrangementCreate(BaseModel):
    employee_id: int
    arrangement_type: str  # "WORK_FROM_HOME" | "OUT_DUTY" | "FIELD_WORK" | "OFFICE"
    from_date: date
    to_date: date
    reason: str
    destination_location: str | None = None
    contact_phone: str | None = None


class WorkArrangementAction(BaseModel):
    rejection_reason: str | None = None


class WorkArrangementRead(BaseModel):
    id: int
    employee_id: int
    employee_name: str | None = None
    employee_code: str | None = None
    arrangement_type: str
    from_date: date
    to_date: date
    reason: str
    destination_location: str | None = None
    contact_phone: str | None = None
    status: str
    actioned_by: int | None = None
    actioned_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
