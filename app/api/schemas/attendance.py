from datetime import date, datetime, time
from pydantic import BaseModel, ConfigDict


class AttendancePunchCreate(BaseModel):
    employee_id: int | None = None
    employee_code: str | None = None
    punch_time: datetime
    punch_type: str = "IN"  # "IN" | "OUT"
    device_id: str | None = None
    source: str = "BIOMETRIC"  # "BIOMETRIC" | "MOBILE" | "WEB" | "MANUAL"
    latitude: float | None = None
    longitude: float | None = None


class BulkPunchCreate(BaseModel):
    punches: list[AttendancePunchCreate]


class AttendancePunchRead(BaseModel):
    id: int
    employee_id: int
    punch_time: datetime
    punch_type: str
    source: str
    device_id: str | None = None
    shift_id: int | None = None
    shift_start: datetime | None = None
    shift_end: datetime | None = None
    attendance_record_id: int | None = None
    is_processed: bool = False
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AttendanceRecordRead(BaseModel):
    id: int
    employee_id: int
    attendance_date: date
    shift_id: int | None
    status: str
    punch_in: time | None
    punch_out: time | None
    worked_minutes: int
    overtime_minutes: int
    late_minutes: int
    early_exit_minutes: int
    model_config = ConfigDict(from_attributes=True)


class AttendanceSummaryRead(BaseModel):
    """Monthly summary stats for an employee."""
    employee_id: int
    month: int
    year: int
    total_working_days: int = 0
    total_present: int = 0
    total_absent: int = 0
    total_leave: int = 0
    total_half_day: int = 0
    total_holiday: int = 0
    total_weekly_off: int = 0
    total_late: int = 0
    total_early_exit: int = 0
    total_missed_punch: int = 0
    total_overtime_minutes: int = 0
    attendance_percentage: float = 0.0


class AttendanceCorrectionCreate(BaseModel):
    attendance_record_id: int
    requested_punch_in: str | None = None   # HH:MM
    requested_punch_out: str | None = None  # HH:MM
    reason: str


class AttendanceCorrectionRead(BaseModel):
    id: int
    attendance_record_id: int
    requested_punch_in: time | None
    requested_punch_out: time | None
    reason: str
    status: str
    requested_at: datetime | None = None
    actioned_by: int | None = None
    actioned_at: datetime | None = None
    rejection_reason: str | None = None
    model_config = ConfigDict(from_attributes=True)

    def __getitem__(self, item: str):
        if item == "correction_id":
            return self.id
        val = getattr(self, item, None)
        if item == "status" and isinstance(val, str):
            return val.lower()
        if val is not None:
            return val
        raise KeyError(item)


class AttendanceCorrectionAction(BaseModel):
    rejection_reason: str | None = None


class ProcessAttendanceRequest(BaseModel):
    from_date: date
    to_date: date
    unit_id: int | None = None
    employee_id: int | None = None


class ProcessAttendanceResponse(BaseModel):
    message: str
    from_date: date
    to_date: date
    processed_records: int
    created_records: int
    updated_records: int

