from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTable[int], Base):
    """HRMS portal user. Login via email or mobile_number + password."""

    __tablename__ = "users"
    __table_args__ = {"comment": "HRMS portal users"}

    id: Mapped[int] = mapped_column("user_id", Integer, primary_key=True, autoincrement=True, index=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # E.164 format, e.g. +919876543210. Used as a secondary login identifier.
    mobile_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)
    invitation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invitation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invitation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invitation_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_super_admin(self) -> bool:
        """Technical administrator flag; business roles are stored on Employee."""
        return bool(self.is_superuser)


class AuthSession(Base):
    """Server-side refresh session; raw refresh tokens are never stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("auth_sessions.id", ondelete="SET NULL"), nullable=True)

    user: Mapped[User] = relationship("User")
    replaced_by: Mapped[AuthSession | None] = relationship("AuthSession", remote_side=[id], uselist=False)


class Notification(Base):
    """HRMS in-app notification."""

    __tablename__ = "notifications"
    __table_args__ = {"comment": "In-app notifications for HRMS users"}

    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True, index=True)
    target_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, index=True)

    user: Mapped[User | None] = relationship("User", foreign_keys=[user_id])


class AuditLog(Base):
    """Append-only security audit events for privileged analytics access."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, nullable=False, index=True)

    actor: Mapped[User | None] = relationship("User")


# -----------------------------------------------------------------------------
# Org Structure
# -----------------------------------------------------------------------------

class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("singleton_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    singleton_key: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)

    units: Mapped[list[Unit]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)

    organization: Mapped[Organization] = relationship(back_populates="units")
    departments: Mapped[list[Department]] = relationship(back_populates="unit", cascade="all, delete-orphan")
    shifts: Mapped[list[Shift]] = relationship(back_populates="unit", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)

    unit: Mapped[Unit] = relationship(back_populates="departments")
    employees: Mapped[list[Employee]] = relationship(back_populates="department")
    approvers: Mapped[list[DepartmentApprover]] = relationship(back_populates="department", cascade="all, delete-orphan")


class Designation(Base):
    __tablename__ = "designations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)

    employees: Mapped[list[Employee]] = relationship(back_populates="designation_rel")


class DepartmentApprover(Base):
    """Links a department to designated approvers for leaves, shifts, expenses, and work arrangements."""
    __tablename__ = "department_approvers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    approver_type: Mapped[str] = mapped_column(String(30), nullable=False)  # LEAVE | SHIFT | EXPENSE | WORK_ARRANGEMENT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    department: Mapped[Department] = relationship(back_populates="approvers")
    user: Mapped[User] = relationship()


# -----------------------------------------------------------------------------
# Employees
# -----------------------------------------------------------------------------

class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(30), default="EMPLOYEE", nullable=False, index=True)

    # Basic Profile
    first_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    official_email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    personal_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Emergency Contact
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Address
    current_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    permanent_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Identity & Statutory
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aadhaar_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Bank Details
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Organization & Hierarchy
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True, index=True)
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id", ondelete="SET NULL"), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(150), nullable=True)  # cached title for backwards compatibility
    reporting_manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)

    # Employment Details
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[str] = mapped_column(String(30), default="PERMANENT", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    biometric_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    monthly_salary: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    overtime_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Separation Details
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist, onupdate=now_ist)

    user: Mapped[User | None] = relationship("User")
    department: Mapped[Department | None] = relationship(back_populates="employees")
    unit: Mapped[Unit | None] = relationship()
    designation_rel: Mapped[Designation | None] = relationship(back_populates="employees")
    shift: Mapped[Shift | None] = relationship()
    reporting_manager: Mapped[Employee | None] = relationship("Employee", remote_side=[id], back_populates="direct_reports")
    direct_reports: Mapped[list[Employee]] = relationship("Employee", back_populates="reporting_manager")
    work_history: Mapped[list[EmployeeWorkHistory]] = relationship(back_populates="employee", cascade="all, delete-orphan")


class EmployeeWorkHistory(Base):
    """Records internal movements: transfer between units/departments, promotions, designation changes."""
    __tablename__ = "employee_work_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id", ondelete="SET NULL"), nullable=True)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    employee: Mapped[Employee] = relationship(back_populates="work_history")
    unit: Mapped[Unit | None] = relationship()
    department: Mapped[Department | None] = relationship()
    designation: Mapped[Designation | None] = relationship()


# -----------------------------------------------------------------------------
# Shifts, Holidays, Weekly Offs
# -----------------------------------------------------------------------------

class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    grace_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_cross_midnight: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Shift margins & auto-attendance thresholds (Frappe HR matching)
    begin_check_in_before_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    allow_check_out_after_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    late_entry_grace_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    early_exit_grace_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    half_day_threshold_hours: Mapped[float] = mapped_column(Numeric(4, 2), default=4.0, nullable=False)
    absent_threshold_hours: Mapped[float] = mapped_column(Numeric(4, 2), default=2.0, nullable=False)
    enable_auto_attendance: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    unit: Mapped[Unit | None] = relationship(back_populates="shifts")


class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    employee: Mapped[Employee] = relationship()
    shift: Mapped[Shift] = relationship()


class HolidayList(Base):
    __tablename__ = "holiday_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    weekly_off_day: Mapped[str] = mapped_column(String(20), default="Sunday", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    unit: Mapped[Unit | None] = relationship()
    holidays: Mapped[list[Holiday]] = relationship(back_populates="holiday_list", cascade="all, delete-orphan")


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    erp_holiday_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    holiday_list_id: Mapped[int | None] = mapped_column(ForeignKey("holiday_lists.id", ondelete="CASCADE"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_weekly_off: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_organization_wide: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    holiday_list: Mapped[HolidayList | None] = relationship(back_populates="holidays")


# -----------------------------------------------------------------------------
# Leaves
# -----------------------------------------------------------------------------

class LeavePeriod(Base):
    __tablename__ = "leave_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    annual_allocation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_consecutive_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    carry_forward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    include_holidays: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LeaveAllocation(Base):
    __tablename__ = "leave_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False)
    leave_period_id: Mapped[int] = mapped_column(ForeignKey("leave_periods.id"), nullable=False)
    new_leaves_allocated: Mapped[float] = mapped_column(Numeric(5, 1), default=0.0, nullable=False)
    carry_forwarded_leaves: Mapped[float] = mapped_column(Numeric(5, 1), default=0.0, nullable=False)
    total_leaves_allocated: Mapped[float] = mapped_column(Numeric(5, 1), default=0.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    employee: Mapped[Employee] = relationship()
    leave_type: Mapped[LeaveType] = relationship()
    leave_period: Mapped[LeavePeriod] = relationship()


class LeaveLedgerEntry(Base):
    """Frappe HR double-entry ledger record for immutable leave transaction tracking."""
    __tablename__ = "leave_ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)  # "ALLOCATION" | "APPLICATION" | "REVERSAL" | "EXPIRY"
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leaves: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)  # Positive for credit, negative for debit
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_carry_forward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    employee: Mapped[Employee] = relationship()
    leave_type: Mapped[LeaveType] = relationship()


class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    leave_type: Mapped[LeaveType] = relationship()


class LeaveApplication(Base):
    __tablename__ = "leave_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False)
    leave_period_id: Mapped[int | None] = mapped_column(ForeignKey("leave_periods.id", ondelete="SET NULL"), nullable=True)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    half_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    half_day_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days_count: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    actioned_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_actioned_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    cancellation_actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    erp_event_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    erp_sync_status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False, index=True)
    erp_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship()
    leave_type: Mapped[LeaveType] = relationship()
    leave_period: Mapped[LeavePeriod | None] = relationship()


class WorkArrangementRequest(Base):
    """WFH, On-Duty, Field Work arrangement requests."""
    __tablename__ = "work_arrangement_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    arrangement_type: Mapped[str] = mapped_column(String(30), nullable=False)  # "WORK_FROM_HOME", "OUT_DUTY", "FIELD_WORK", "OFFICE"
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    destination_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    actioned_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    employee: Mapped[Employee] = relationship()

    @property
    def employee_name(self) -> str | None:
        if self.employee is None:
            return None
        return f"{self.employee.first_name} {self.employee.last_name or ''}".strip()

    @property
    def employee_code(self) -> str | None:
        return self.employee.employee_code if self.employee is not None else None



# -----------------------------------------------------------------------------
# Attendance
# -----------------------------------------------------------------------------

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_employee_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ATTENDANCE_PENDING", nullable=False)
    punch_in: Mapped[time | None] = mapped_column(Time, nullable=True)
    punch_out: Mapped[time | None] = mapped_column(Time, nullable=True)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_exit_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="HRMS", nullable=False)
    erp_record_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    sync_status: Mapped[str] = mapped_column(String(30), default="LOCAL", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship()
    shift: Mapped[Shift | None] = relationship()



class AttendancePunch(Base):
    """Raw check-in punch log from biometric devices, mobile apps, or web."""
    __tablename__ = "attendance_punches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    punch_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    punch_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'IN' or 'OUT'
    source: Mapped[str] = mapped_column(String(50), default="BIOMETRIC", nullable=False)
    erp_event_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Resolved shift window at punch time
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True)
    shift_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shift_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Processing state
    attendance_record_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_records.id", ondelete="SET NULL"), nullable=True, index=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Geolocation if applicable
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)

    employee: Mapped[Employee] = relationship()
    shift: Mapped[Shift | None] = relationship()


class AttendanceDiscrepancy(Base):
    __tablename__ = "attendance_discrepancies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attendance_record_id: Mapped[int] = mapped_column(ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=False)
    discrepancy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)


class AttendanceCorrectionRequest(Base):
    __tablename__ = "attendance_correction_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attendance_record_id: Mapped[int] = mapped_column(ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=False)
    requested_punch_in: Mapped[time | None] = mapped_column(Time, nullable=True)
    requested_punch_out: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    actioned_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    erp_correction_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    sync_status: Mapped[str] = mapped_column(String(30), default="PENDING_ERP_RECONCILIATION", nullable=False)

    attendance_record: Mapped[AttendanceRecord] = relationship()


# -----------------------------------------------------------------------------
# Overtime
# -----------------------------------------------------------------------------

class OvertimeRecord(Base):
    __tablename__ = "overtime_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_record_id: Mapped[int] = mapped_column(ForeignKey("attendance_records.id"), nullable=False)
    calculated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    actioned_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    erp_event_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    overtime_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overtime_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="ERP", nullable=False)

    employee: Mapped[Employee] = relationship()
    attendance_record: Mapped[AttendanceRecord] = relationship()


class OvertimeApproval(Base):
    __tablename__ = "overtime_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    overtime_record_id: Mapped[int] = mapped_column(ForeignKey("overtime_records.id", ondelete="CASCADE"), nullable=False)
    approved_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actioned_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    actioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_ist)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
