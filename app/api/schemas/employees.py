from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr

BusinessRole = Literal["EMPLOYEE", "DEPARTMENT_MANAGER", "HR_ADMIN", "ORGANIZATION_OWNER"]


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
    role: BusinessRole = "EMPLOYEE"
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


class EmployeeOnboardingCreate(EmployeeCreate):
    """Employee HR record plus its required portal-account provisioning."""
    create_user_account: bool = True
    username: str | None = None
    initial_password: str | None = None
    model_config = ConfigDict(json_schema_extra={"example": {
        "employee_code": "EMP001", "role": "EMPLOYEE", "first_name": "Rahul", "last_name": "Sharma",
        "official_email": "rahul.sharma@example.com", "personal_email": "rahul.personal@example.com",
        "phone_number": "9876543210", "date_of_birth": "1992-04-15", "gender": "MALE", "marital_status": "MARRIED", "blood_group": "O+",
        "emergency_contact_name": "Priya Sharma", "emergency_contact_phone": "9876501234", "emergency_contact_relation": "Spouse",
        "current_address": "Andheri East, Mumbai", "permanent_address": "Jaipur, Rajasthan",
        "pan_number": "ABCDE1234F", "aadhaar_number": "123456789012",
        "bank_name": "Example Bank", "bank_account_number": "123456789012", "bank_ifsc_code": "EXMP0001234",
        "designation": "Senior Engineer", "designation_id": 1, "date_of_joining": "2026-09-20", "employment_type": "PERMANENT",
        "status": "ACTIVE", "biometric_id": "BIO-EMP001", "overtime_eligible": True,
        "unit_id": 1, "department_id": 1, "shift_id": None, "reporting_manager_id": None, "monthly_salary": None,
        "user_id": None, "create_user_account": True, "username": "rahul.sharma",
        "initial_password": "StrongPassword@123"
    }})


class EmployeeUpdate(BaseModel):
    role: BusinessRole | None = None
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
    model_config = ConfigDict(json_schema_extra={"example": {
        "role": "EMPLOYEE", "first_name": "Rahul", "last_name": "Sharma",
        "official_email": "rahul.sharma@example.com", "personal_email": "rahul.personal@example.com", "phone_number": "9876543210",
        "date_of_birth": "1992-04-15", "gender": "MALE", "marital_status": "MARRIED", "blood_group": "O+",
        "emergency_contact_name": "Priya Sharma", "emergency_contact_phone": "9876501234", "emergency_contact_relation": "Spouse",
        "current_address": "Andheri East, Mumbai", "permanent_address": "Jaipur, Rajasthan",
        "pan_number": "ABCDE1234F", "aadhaar_number": "123456789012", "bank_name": "Example Bank",
        "bank_account_number": "123456789012", "bank_ifsc_code": "EXMP0001234", "designation": "Senior Engineer", "designation_id": 1,
        "date_of_joining": "2026-09-20", "employment_type": "PERMANENT", "status": "ACTIVE", "biometric_id": "BIO-EMP001",
        "overtime_eligible": True, "department_id": 1, "unit_id": 1, "shift_id": None, "reporting_manager_id": None,
        "monthly_salary": None, "exit_date": None, "exit_reason": None
    }})


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


class EmployeeDirectoryRead(BaseModel):
    """Safe directory projection for normal authenticated users.

    Statutory IDs, bank data, private contact details and compensation are
    intentionally absent.  Those fields stay available only to ERP-facing
    administration flows and must not leak through the people directory.
    """

    id: int
    employee_code: str
    role: BusinessRole
    first_name: str
    last_name: str | None = None
    official_email: str | None = None
    designation: str | None = None
    designation_id: int | None = None
    date_of_joining: date | None = None
    employment_type: str
    status: str
    department_id: int | None = None
    unit_id: int | None = None
    shift_id: int | None = None
    reporting_manager_id: int | None = None
    overtime_eligible: bool
    full_name: str | None = None
    department_name: str | None = None
    unit_name: str | None = None
    shift_name: str | None = None
    designation_name: str | None = None
    reporting_manager_name: str | None = None
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

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {
        "employee_code": "EMP001", "role": "EMPLOYEE", "first_name": "Rahul", "last_name": "Sharma",
        "official_email": "rahul.sharma@example.com", "personal_email": None, "phone_number": "9876543210",
        "date_of_birth": "1992-04-15", "gender": "MALE", "marital_status": "MARRIED", "blood_group": "O+",
        "emergency_contact_name": "Priya Sharma", "emergency_contact_phone": "9876501234", "emergency_contact_relation": "Spouse",
        "current_address": "Andheri East, Mumbai", "permanent_address": "Jaipur, Rajasthan", "pan_number": "ABCDE1234F", "aadhaar_number": None,
        "bank_name": "Example Bank", "bank_account_number": None, "bank_ifsc_code": None, "designation": "Senior Engineer", "designation_id": 1,
        "date_of_joining": "2026-09-20", "employment_type": "PERMANENT", "status": "ACTIVE", "biometric_id": "BIO-EMP001",
        "overtime_eligible": True, "id": 1, "user_id": 5, "department_id": 1, "unit_id": 1, "shift_id": None,
        "reporting_manager_id": None, "monthly_salary": None, "exit_date": None, "exit_reason": None,
        "created_at": "2026-09-20T23:49:36.607372+05:30", "updated_at": "2026-09-20T23:49:36.607377+05:30",
        "full_name": "Rahul Sharma", "department_name": "Engineering", "unit_name": "Mumbai Unit", "shift_name": None,
        "designation_name": "Senior Engineer", "reporting_manager_name": None
    }})


class PaginatedEmployeesResponse(BaseModel):
    items: list[EmployeeDirectoryRead]
    total: int
    page: int
    page_size: int
    total_pages: int
