from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OvertimeRecordRead(BaseModel):
    id: int
    employee_id: int
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
    approved_minutes: int
    remarks: str | None = None


class OvertimeRejectionCreate(BaseModel):
    remarks: str | None = None


class OvertimeSummary(BaseModel):
    employee_id: int
    month: int
    year: int
    total_calculated_minutes: int = 0
    total_approved_minutes: int = 0
    pending_count: int = 0
