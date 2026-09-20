from datetime import date, datetime, time
from pydantic import BaseModel, ConfigDict


class ShiftBase(BaseModel):
    name: str
    code: str | None = None
    start_time: time | str  # "HH:MM" or time object
    end_time: time | str    # "HH:MM" or time object
    grace_minutes: int = 10
    break_minutes: int = 30
    is_cross_midnight: bool = False
    is_active: bool = True

    # Margins and thresholds matching Frappe HR
    begin_check_in_before_minutes: int = 60
    allow_check_out_after_minutes: int = 60
    late_entry_grace_minutes: int = 10
    early_exit_grace_minutes: int = 10
    half_day_threshold_hours: float = 4.0
    absent_threshold_hours: float = 2.0
    enable_auto_attendance: bool = True


class ShiftCreate(ShiftBase):
    unit_id: int | None = None


class ShiftUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    start_time: time | str | None = None
    end_time: time | str | None = None
    grace_minutes: int | None = None
    break_minutes: int | None = None
    is_cross_midnight: bool | None = None
    is_active: bool | None = None
    begin_check_in_before_minutes: int | None = None
    allow_check_out_after_minutes: int | None = None
    late_entry_grace_minutes: int | None = None
    early_exit_grace_minutes: int | None = None
    half_day_threshold_hours: float | None = None
    absent_threshold_hours: float | None = None
    enable_auto_attendance: bool | None = None


class ShiftRead(ShiftBase):
    id: int
    unit_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class ShiftAssignmentCreate(BaseModel):
    employee_id: int
    shift_id: int
    effective_from: date
    effective_to: date | None = None


class BulkShiftAssignmentCreate(BaseModel):
    shift_id: int
    effective_from: date
    effective_to: date | None = None
    employee_ids: list[int] = []
    department_id: int | None = None
    unit_id: int | None = None


class ShiftAssignmentRead(BaseModel):
    id: int
    employee_id: int
    shift_id: int
    effective_from: date
    effective_to: date | None = None
    status: str = "ACTIVE"
    created_at: datetime | None = None

    # Nested info
    shift_name: str | None = None
    shift_code: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    employee_name: str | None = None
    employee_code: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ShiftWindowDetail(BaseModel):
    shift_id: int
    shift_name: str
    shift_start: datetime
    shift_end: datetime
    actual_start: datetime
    actual_end: datetime
    is_cross_midnight: bool


class EmployeeShiftScheduleRead(BaseModel):
    employee_id: int
    current_shift: ShiftWindowDetail | None = None
    previous_shift: ShiftWindowDetail | None = None
    upcoming_shift: ShiftWindowDetail | None = None
