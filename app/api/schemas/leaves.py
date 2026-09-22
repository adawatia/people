from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Leave Periods ─────────────────────────────────────────────────────────────

class LeavePeriodCreate(BaseModel):
    name: str
    from_date: date
    to_date: date
    is_active: bool = True


class LeavePeriodRead(BaseModel):
    id: int
    name: str
    from_date: date
    to_date: date
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Leave Types ───────────────────────────────────────────────────────────────

class LeaveTypeBase(BaseModel):
    name: str
    code: str
    is_paid: bool = True
    annual_allocation: int = 0
    max_consecutive_days: int | None = None
    requires_approval: bool = True
    carry_forward: bool = False
    include_holidays: bool = False
    is_active: bool = True


class LeaveTypeCreate(LeaveTypeBase):
    pass


class LeaveTypeUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    is_paid: bool | None = None
    annual_allocation: int | None = None
    max_consecutive_days: int | None = None
    requires_approval: bool | None = None
    carry_forward: bool | None = None
    include_holidays: bool | None = None
    is_active: bool | None = None


class LeaveTypeRead(LeaveTypeBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ── Leave Allocation ──────────────────────────────────────────────────────────

class LeaveAllocationCreate(BaseModel):
    employee_id: int
    leave_type_id: int
    leave_period_id: int
    new_leaves_allocated: float = 0.0
    carry_forwarded_leaves: float = 0.0
    notes: str | None = None


class LeaveAllocationRead(BaseModel):
    id: int
    employee_id: int
    leave_type_id: int
    leave_period_id: int
    new_leaves_allocated: float
    carry_forwarded_leaves: float
    total_leaves_allocated: float
    notes: str | None
    created_at: datetime
    employee_name: str | None = None
    employee_code: str | None = None
    leave_type_name: str | None = None
    leave_period_name: str | None = None
    model_config = ConfigDict(from_attributes=True)


# ── Leave Ledger Entries ──────────────────────────────────────────────────────

class LeaveLedgerEntryRead(BaseModel):
    id: int
    employee_id: int
    leave_type_id: int
    transaction_type: str
    transaction_id: int | None
    leaves: float
    from_date: date
    to_date: date
    is_carry_forward: bool
    is_expired: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Leave Balance ─────────────────────────────────────────────────────────────

class LeaveBalanceRead(BaseModel):
    employee_id: int
    leave_type_id: int
    leave_type_name: str
    leave_type_code: str
    leave_period_id: int | None = None
    allocated: float = 0.0
    used: float = 0.0
    pending: float = 0.0
    available: float = 0.0
    model_config = ConfigDict(from_attributes=True)


# ── Leave Application ─────────────────────────────────────────────────────────

class LeaveApplicationCreate(BaseModel):
    employee_id: int
    leave_type_id: int
    from_date: date
    to_date: date
    half_day: bool = False
    half_day_date: date | None = None
    reason: str | None = None


class LeaveApplicationAction(BaseModel):
    rejection_reason: str | None = None


class LeaveCancellationRequest(BaseModel):
    """Request early return from leave that has already started."""

    effective_date: date | None = None
    reason: str = Field(min_length=3, max_length=500)


class LeaveCancellationAction(BaseModel):
    rejection_reason: str = Field(min_length=3, max_length=500)


class LeaveApplicationRead(BaseModel):
    id: int
    employee_id: int
    leave_type_id: int
    leave_period_id: int | None = None
    leave_type_name: str | None = None
    leave_type_code: str | None = None
    employee_name: str | None = None
    employee_code: str | None = None
    from_date: date
    to_date: date
    half_day: bool
    half_day_date: date | None
    days_count: float
    reason: str | None
    status: str
    applied_at: datetime
    actioned_by: int | None
    actioned_at: datetime | None
    rejection_reason: str | None
    cancellation_requested_by: int | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_effective_date: date | None = None
    cancellation_reason: str | None = None
    cancellation_actioned_by: int | None = None
    cancellation_actioned_at: datetime | None = None
    cancellation_rejection_reason: str | None = None
    erp_event_id: str | None = None
    erp_sync_status: str = "PENDING"
    erp_synced_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)
