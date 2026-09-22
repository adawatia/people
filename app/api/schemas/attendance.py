from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class AttendancePunchCreate(BaseModel):
    employee_id: int | None = None
    employee_code: str | None = None
    punch_time: datetime
    punch_type: str = "IN"  # "IN" | "OUT"
    device_id: str | None = None
    source: str = "BIOMETRIC"  # "BIOMETRIC" | "MOBILE" | "WEB" | "MANUAL"
    latitude: float | None = None
    longitude: float | None = None
    erp_event_id: str | None = None
    model_config = ConfigDict(json_schema_extra={"example": {"employee_code": "EMP001", "punch_time": "2026-09-20T09:15:00+05:30", "punch_type": "IN", "device_id": "BIO-01", "erp_event_id": "ERP-PUNCH-1001"}})


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
    erp_event_id: str | None = None
    last_synced_at: datetime | None = None
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
    source: str = "HRMS"
    erp_record_id: str | None = None
    sync_status: str = "LOCAL"
    last_synced_at: datetime | None = None
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
    erp_correction_id: str | None = None


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
    erp_correction_id: str | None = None
    sync_status: str = "PENDING_ERP_RECONCILIATION"
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


class ErpAttendanceRecordCreate(BaseModel):
    employee_id: int | None = None
    employee_code: str | None = None
    erp_record_id: str
    attendance_date: date
    shift_id: int | None = None
    status: str
    punch_in: time | None = None
    punch_out: time | None = None
    worked_minutes: int = 0
    overtime_minutes: int = 0
    late_minutes: int = 0
    early_exit_minutes: int = 0
    model_config = ConfigDict(json_schema_extra={"example": {"employee_code": "EMP001", "erp_record_id": "ERP-ATT-20260920-EMP001", "attendance_date": "2026-09-20", "shift_id": 1, "status": "PRESENT", "punch_in": "09:15:00", "punch_out": "18:05:00", "worked_minutes": 530}})


class ErpAttendanceRecordBulkCreate(BaseModel):
    """Bulk daily records for any mix of past, current, or planned dates."""

    records: list[ErpAttendanceRecordCreate] = Field(..., min_length=1, max_length=5000)
    model_config = ConfigDict(json_schema_extra={"example": {"records": [{"employee_code": "EMP001", "erp_record_id": "ERP-ATT-20260920-EMP001", "attendance_date": "2026-09-20", "shift_id": 1, "status": "PRESENT", "punch_in": "09:15:00", "punch_out": "18:05:00", "worked_minutes": 530}]}})


class ErpCorrectionCreate(BaseModel):
    erp_correction_id: str
    employee_id: int | None = None
    employee_code: str | None = None
    attendance_date: date
    requested_punch_in: time | None = None
    requested_punch_out: time | None = None
    reason: str
    model_config = ConfigDict(json_schema_extra={"example": {"employee_code": "EMP001", "erp_correction_id": "ERP-CORR-5001", "attendance_date": "2026-09-20", "requested_punch_in": "09:00:00", "reason": "Biometric device correction"}})


class ErpSyncResult(BaseModel):
    accepted: list[dict] = Field(default_factory=list)
    duplicates: list[dict] = Field(default_factory=list)
    failed: list[dict] = Field(default_factory=list)
