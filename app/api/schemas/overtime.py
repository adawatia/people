from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OvertimeRecordRead(BaseModel):
    id: int
    employee_id: int
    employee_name: str | None = None
    employee_code: str | None = None
    attendance_date: date | None = None
    attendance_record_id: int
    calculated_minutes: int
    approved_minutes: int
    status: str
    actioned_by: int | None = None
    actioned_at: datetime | None = None
    rejection_reason: str | None = None
    erp_event_id: str | None = None
    overtime_start: datetime | None = None
    overtime_end: datetime | None = None
    source: str = "ERP"
    model_config = ConfigDict(from_attributes=True)


class OvertimeApprovalCreate(BaseModel):
    approved_minutes: int = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=500)


class OvertimeRejectionCreate(BaseModel):
    remarks: str = Field(min_length=3, max_length=500)

    @field_validator("remarks")
    @classmethod
    def strip_and_validate_remarks(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Rejection reason must contain at least 3 non-whitespace characters")
        return value


class OvertimeSummary(BaseModel):
    employee_id: int
    month: int
    year: int
    total_calculated_minutes: int = 0
    total_approved_minutes: int = 0
    pending_count: int = 0
