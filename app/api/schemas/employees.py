from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr


class ShiftRead(BaseModel):
    id: int
    unit_id: int | None
    name: str
    start_time: str
    end_time: str
    grace_minutes: int
    break_minutes: int
    is_cross_midnight: bool
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class EmployeeBase(BaseModel):
    employee_code: str
    first_name: str
    last_name: str | None = None
    official_email: str | None = None
    personal_email: str | None = None
    phone_number: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    marital_status: str | None = None
    blood_group: str | None = None

    # Emergency Contact
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None

    # Address
    current_address: str | None = None
    permanent_address: str | None = None

    # Identity / Statutory
    pan_number: str | None = None
    aadhaar_number: str | None = None

    # Bank Details
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None

    # Employment details
    designation: str | None = None
    designation_id: int | None = None
    date_of_joining: date | None = None
    employment_type: str = "PERMANENT"
    status: str = "ACTIVE"
    biometric_id: str | None = None
    overtime_eligible: bool = True


class EmployeeCreate(EmployeeBase):
    user_id: int | None = None
    department_id: int | None = None
    unit_id: int | None = None
    shift_id: int | None = None
    reporting_manager_id: int | None = None
    monthly_salary: float | None = None


class EmployeeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    official_email: str | None = None
    personal_email: str | None = None
    phone_number: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    marital_status: str | None = None
    blood_group: str | None = None

    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None

    current_address: str | None = None
    permanent_address: str | None = None

    pan_number: str | None = None
    aadhaar_number: str | None = None

    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None

    designation: str | None = None
    designation_id: int | None = None
    date_of_joining: date | None = None
    employment_type: str | None = None
    status: str | None = None
    biometric_id: str | None = None
    department_id: int | None = None
    unit_id: int | None = None
    shift_id: int | None = None
    reporting_manager_id: int | None = None
    overtime_eligible: bool | None = None
    monthly_salary: float | None = None
    exit_date: date | None = None
    exit_reason: str | None = None


class EmployeeDeactivateRequest(BaseModel):
    exit_date: date | None = None
    exit_reason: str | None = None


class EmployeeWorkHistoryRead(BaseModel):
    id: int
    employee_id: int
    unit_id: int | None = None
    department_id: int | None = None
    designation_id: int | None = None
    from_date: date
    to_date: date | None = None
    remarks: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EmployeeRead(EmployeeBase):
    id: int
    user_id: int | None = None
    department_id: int | None = None
    unit_id: int | None = None
    shift_id: int | None = None
    reporting_manager_id: int | None = None
    monthly_salary: float | None = None
    exit_date: date | None = None
    exit_reason: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    # Nested / derived readable names
    full_name: str | None = None
    department_name: str | None = None
    unit_name: str | None = None
    shift_name: str | None = None
    designation_name: str | None = None
    reporting_manager_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedEmployeesResponse(BaseModel):
    items: list[EmployeeRead]
    total: int
    page: int
    page_size: int
    total_pages: int
