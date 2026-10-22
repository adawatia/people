"""Seed rich, authentic Indian English data for all HRMS entities using Faker ('en_IN').

This module populates the complete database with realistic Indian enterprise data:
- Organization (Indian enterprise with GSTIN, PAN, Indian corporate address)
- Units across major Indian tech hubs (Bengaluru, Hyderabad, Mumbai, Pune, Gurugram)
- Departments, Designations, and Department Approvers
- Shifts (General, Morning, Evening, Night) with auto-attendance thresholds
- Gazetted & National Indian Holidays 2026 (Republic Day, Holi, Independence Day, Diwali, etc.)
- Leave Periods, Leave Types, Allocations, Balances, and Double-entry Ledger Entries
- Full workforce of Users and Employees with:
    - Authentic Indian names (en_IN Faker)
    - Valid E.164 Indian mobile numbers (+91 followed by 6-9 and 9 digits)
    - Realistic Indian street addresses, cities, states, and PIN codes
    - Statutory identity: Indian PAN (ABCDE1234F) & Aadhaar (12 digits)
    - Indian Bank accounts (SBI, HDFC, ICICI, Axis, Kotak) & valid IFSC codes
    - Emergency contacts with Indian relationships
    - Proper organizational hierarchy (CEO -> Directors/HR -> Managers -> Team Members)
    - Elevated business roles (ORGANIZATION_OWNER, HR_ADMIN, DEPARTMENT_MANAGER, EMPLOYEE)
    - Working User accounts with pre-hashed dev password for testing
- Shift Assignments for all employees
- Authentic Leave Applications with real-world Indian reasons and approvals
- Work Arrangement Requests (Work From Home, On Duty, Field Work)
- Biometric Attendance Punches and Attendance Records over recent months
- Attendance Discrepancies and Regularization/Correction Requests
- Overtime Records and Approvals
- Employee Work Histories (promotions and inter-unit transfers)
- In-app Notifications and Notification Receipts
- Security Audit Logs
- ERP Outbox Events and Sync Batch Audits

Usage:
    uv run python -m db.seed_indian_data
    uv run python db/seed_indian_data.py --clean
"""

from __future__ import annotations

import argparse
import asyncio
import random
import string
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure parent directory (app/api) is in sys.path when run directly as a script
_APP_API_DIR = str(Path(__file__).resolve().parent.parent)
if _APP_API_DIR not in sys.path:
    sys.path.insert(0, _APP_API_DIR)

from faker import Faker
from fastapi_users.password import PasswordHelper
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import Engine

from core.business_roles import (
    DEPARTMENT_MANAGER,
    EMPLOYEE,
    HR_ADMIN,
    ORGANIZATION_OWNER,
    SCOPE_DEPARTMENT,
    SCOPE_ORGANIZATION,
    SCOPE_SELF,
    SCOPE_UNIT,
)
from core.database import async_session_maker
from core.settings import get_settings
from db.models import (
    AttendanceCorrectionRequest,
    AttendanceDiscrepancy,
    AttendancePunch,
    AttendanceRecord,
    AuditLog,
    Department,
    DepartmentApprover,
    Designation,
    Employee,
    EmployeeWorkHistory,
    ErpOutboxEvent,
    ErpSyncBatch,
    Holiday,
    HolidayList,
    LeaveAllocation,
    LeaveApplication,
    LeaveBalance,
    LeaveLedgerEntry,
    LeavePeriod,
    LeaveType,
    Notification,
    NotificationReceipt,
    Organization,
    OvertimeApproval,
    OvertimeRecord,
    Shift,
    ShiftAssignment,
    Unit,
    User,
    WorkArrangementRequest,
)

IST = ZoneInfo("Asia/Kolkata")
DEV_PASSWORD = "HrmsDev@2026!"

# Fixed seed for reproducibility while still looking natural
fake = Faker("en_IN")
Faker.seed(42)
random.seed(42)

PRESERVED_TABLES = frozenset({"alembic_version"})

INDIAN_BANKS = [
    ("State Bank of India", "SBIN"),
    ("HDFC Bank", "HDFC"),
    ("ICICI Bank", "ICIC"),
    ("Axis Bank", "UTIB"),
    ("Kotak Mahindra Bank", "KKBK"),
    ("Bank of Baroda", "BARB"),
    ("Punjab National Bank", "PUNB"),
]

INDIAN_RELATIONS = ["Father", "Mother", "Spouse", "Brother", "Sister"]
BLOOD_GROUPS = ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"]

LEAVE_REASONS = [
    "Attending cousin's wedding ceremony in Jaipur",
    "Visiting parents in Varanasi for Diwali festivities",
    "Down with viral fever and persistent cough; consulting doctor at Fortis Hospital",
    "Attending sister's wedding in Lucknow",
    "Family trip to Ooty for wedding anniversary",
    "Personal banking work and Aadhaar biometric update at local Post Office",
    "Child's school parent-teacher meeting and annual day celebrations",
    "House shifting to new apartment in Whitefield",
    "Severe migraine headache and fatigue, resting as advised by physician",
    "Attending friend's destination wedding in Udaipur",
    "Medical checkup and dental root canal treatment at Apollo Clinic",
    "Observing Chhath Puja with family in Patna",
    "Attending religious pilgrimage and family rituals at Tirupati",
    "Visiting hometown in Chandigarh for urgent family matter",
    "Acute food poisoning; doctor advised 2 days bed rest",
]

WFH_REASONS = [
    "Broadband fiber optic maintenance and technician visit scheduled at residence",
    "Severe traffic congestion advisory due to metro pillar construction on Outer Ring Road",
    "Client architectural review meeting with overseas team across overlapping time zones",
    "Attending PyCon India 2026 developer conference remotely",
    "Severe waterlogging and heavy monsoon rain advisory in residential area",
    "Home inverter and electrical installation work requiring presence",
    "Recovering from mild seasonal cold; working remotely to prevent spreading infection",
    "Parent visiting hospital for routine tests; assisting with local transport",
    "Working from hometown (Chandigarh) ahead of the extended holiday weekend",
    "Site inspection and security audit of vendor server racks in Whitefield",
]

ATTENDANCE_CORRECTION_REASONS = [
    "Biometric fingerprint scanner at Gate 2 was unresponsive when leaving yesterday evening",
    "Forgot to punch out while rushing to board the office transport cab",
    "Biometric device had network connectivity sync delay during morning entry",
    "Punch card reader failed to capture exit swipe; reported to security desk immediately",
    "Was working late from server room and exited via emergency gate without reader",
]


def gen_pan() -> str:
    """Generate a valid Indian PAN format: 5 letters + 4 digits + 1 letter."""
    letters1 = "".join(random.choices(string.ascii_uppercase, k=5))
    digits = f"{random.randint(1000, 9999)}"
    letter2 = random.choice(string.ascii_uppercase)
    return f"{letters1}{digits}{letter2}"


def gen_aadhaar() -> str:
    """Generate a valid Indian 12-digit Aadhaar number."""
    first = random.randint(2, 9)
    rest = "".join(random.choices(string.digits, k=11))
    return f"{first}{rest}"


def gen_mobile() -> str:
    """Generate a valid 10-digit Indian mobile number in E.164 format (+91[6-9]...)."""
    first = random.choice(["6", "7", "8", "9"])
    rest = "".join(random.choices(string.digits, k=9))
    return f"+91{first}{rest}"


def gen_ifsc(bank_code: str) -> str:
    """Generate a valid Indian IFSC code: 4 letters + '0' + 6 alphanumeric."""
    num_part = f"{random.randint(100000, 999999)}"
    return f"{bank_code}0{num_part}"


def gen_bank_account() -> str:
    """Generate a realistic 12 to 16 digit bank account number."""
    return "".join(random.choices(string.digits, k=random.randint(12, 16)))


def clean_application_tables(engine: Engine, schema: str = "public") -> None:
    """Truncate all application tables while preserving Alembic and Super Admin."""
    with engine.connect() as conn:
        all_tables = sorted(t for t in inspect(conn).get_table_names(schema=schema) if t not in PRESERVED_TABLES)
    if not all_tables:
        return

    quote = engine.dialect.identifier_preparer.quote
    quote_schema = engine.dialect.identifier_preparer.quote_schema
    q_tables = ", ".join(f"{quote_schema(schema)}.{quote(t)}" for t in all_tables)

    with engine.begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE TABLE {q_tables} RESTART IDENTITY CASCADE")
        users_table = f"{quote_schema(schema)}.{quote('users')}"
        conn.exec_driver_sql(f"DELETE FROM {users_table} WHERE is_superuser IS NOT TRUE")
    print(f"Cleaned {len(all_tables)} application tables and preserved Super Admin accounts.")


async def seed_indian_data(*, clean: bool = False, num_employees: int = 40) -> dict[str, int]:
    """Execute complete Indian English data seeding for all HRMS entities."""
    settings = get_settings()
    sync_url = settings.resolved_database_url_sync()

    if clean:
        sync_engine = create_engine(sync_url, pool_pre_ping=True)
        clean_application_tables(sync_engine)
        sync_engine.dispose()

    password_helper = PasswordHelper()
    shared_dev_password_hash = password_helper.hash(DEV_PASSWORD)

    async with async_session_maker() as session:
        # 1. Super Admin Account
        superadmin = await session.scalar(select(User).where(User.username == settings.super_admin_username))
        if superadmin is None:
            superadmin = User(
                email=settings.super_admin_email,
                username=settings.super_admin_username,
                first_name=settings.super_admin_first_name or "Super",
                last_name=settings.super_admin_last_name or "Admin",
                hashed_password=password_helper.hash(settings.super_admin_password),
                mobile_number="+919800000001",
                is_active=True,
                is_verified=True,
                is_superuser=True,
            )
            session.add(superadmin)
            await session.flush()

        # 2. Organization (Indian Enterprise)
        org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
        if org is None:
            org = Organization(
                erp_id="ORG-BDTS-001",
                singleton_key=1,
                name="Bharat Dynamics & Tech Solutions Ltd.",
                short_name="BDTS",
                industry="Information Technology & Enterprise Services",
                address_line1="Tower 4, 6th Floor, Cyber Gateway, HITEC City",
                address_line2="Madhapur",
                city="Hyderabad",
                state="Telangana",
                country="India",
                postal_code="500081",
                phone="+914023456789",
                email="contact@bharatdynamics.co.in",
                website="https://www.bharatdynamics.co.in",
                tax_id="36AAACB1234D1Z5",
            )
            session.add(org)
            await session.flush()
        else:
            org.name = "Bharat Dynamics & Tech Solutions Ltd."
            org.short_name = "BDTS"
            org.industry = "Information Technology & Enterprise Services"
            org.address_line1 = "Tower 4, 6th Floor, Cyber Gateway, HITEC City"
            org.address_line2 = "Madhapur"
            org.city = "Hyderabad"
            org.state = "Telangana"
            org.country = "India"
            org.postal_code = "500081"
            org.phone = "+914023456789"
            org.email = "contact@bharatdynamics.co.in"
            org.website = "https://www.bharatdynamics.co.in"
            org.tax_id = "36AAACB1234D1Z5"
            await session.flush()

        # 3. Units across Indian Tech Hubs
        units_spec = [
            ("UNIT-HYD-01", "Hyderabad Tech Campus", "HYD-01", "Hyderabad"),
            ("UNIT-BLR-01", "Bengaluru Innovation Hub", "BLR-01", "Bengaluru"),
            ("UNIT-BOM-01", "Mumbai Corporate Office", "BOM-01", "Mumbai"),
            ("UNIT-PNQ-01", "Pune Development Center", "PNQ-01", "Pune"),
            ("UNIT-GGN-01", "Gurugram Operations Campus", "GGN-01", "Gurugram"),
        ]
        unit_map: dict[str, Unit] = {}
        for erp_id, name, code, city in units_spec:
            u = await session.scalar(select(Unit).where(Unit.code == code))
            if u is None:
                u = Unit(
                    erp_id=erp_id,
                    organization_id=org.id,
                    name=name,
                    code=code,
                    city=city,
                    is_active=True,
                )
                session.add(u)
                await session.flush()
            unit_map[code] = u

        # 4. Departments
        dept_specs = [
            # code, name, unit_code
            ("ENG-HYD", "Engineering & Architecture", "HYD-01"),
            ("PRD-HYD", "Product & User Experience", "HYD-01"),
            ("QA-HYD", "Quality Assurance & Automation", "HYD-01"),
            ("HR-HYD", "Human Resources & People Ops", "HYD-01"),
            ("FIN-HYD", "Finance & Corporate Accounts", "HYD-01"),
            ("ENG-BLR", "Core Platform Engineering", "BLR-01"),
            ("PRD-BLR", "Cloud Products & AI Labs", "BLR-01"),
            ("QA-BLR", "Performance & Security Testing", "BLR-01"),
            ("HR-BLR", "Talent Acquisition & Culture", "BLR-01"),
            ("FIN-BOM", "Treasury & Strategic Finance", "BOM-01"),
            ("SLS-BOM", "Enterprise Sales & Partnerships", "BOM-01"),
            ("HR-BOM", "Western Region HR Operations", "BOM-01"),
            ("ENG-PNQ", "Solutions Delivery & Cloud DevOps", "PNQ-01"),
            ("QA-PNQ", "System Verification & QA", "PNQ-01"),
            ("SLS-GGN", "Government & Enterprise Alliances", "GGN-01"),
            ("OPS-GGN", "Customer Success & 24/7 Operations", "GGN-01"),
        ]
        dept_map: dict[str, Department] = {}
        for code, name, unit_code in dept_specs:
            d = await session.scalar(select(Department).where(Department.code == code))
            if d is None:
                d = Department(
                    erp_id=f"DEPT-{code}",
                    unit_id=unit_map[unit_code].id,
                    name=name,
                    code=code,
                    is_active=True,
                )
                session.add(d)
                await session.flush()
            dept_map[code] = d

        # 5. Designations (Indian IT & Corporate Ladder)
        desig_specs = [
            ("CEO", "Chief Executive Officer", "Executive leadership & strategic direction"),
            ("CTO", "Chief Technology Officer", "Global engineering & architecture"),
            ("DIR-HR", "Director of Human Resources", "People strategy, culture & talent"),
            ("DIR-ENG", "Director of Engineering", "Engineering org leadership & delivery"),
            ("ENG-MGR", "Engineering Manager", "People management & technical execution"),
            ("LEAD-PM", "Lead Product Manager", "Product vision & roadmap ownership"),
            ("PRIN-SE", "Principal Software Engineer", "System architecture & staff mentoring"),
            ("SR-SE", "Senior Software Engineer", "Core backend and full-stack development"),
            ("SE", "Software Engineer", "Feature development and code maintenance"),
            ("ASE", "Associate Software Engineer", "Junior software development and bug fixes"),
            ("SR-QA", "Senior QA Automation Engineer", "Test framework architecture & automation"),
            ("QA-ENG", "QA Automation Engineer", "Automated test suites & quality reporting"),
            ("LEAD-HRBP", "Lead HR Business Partner", "Strategic business partnering & growth"),
            ("HRBP", "HR Business Partner", "Employee relations & unit HR support"),
            ("SR-TAS", "Senior Talent Acquisition Specialist", "Senior hiring & university outreach"),
            ("FIN-MGR", "Finance & Accounts Manager", "Financial planning, taxation & compliance"),
            ("SR-FIN", "Senior Financial Analyst", "Budgeting, variance & audit support"),
            ("SALES-DIR", "Enterprise Sales Director", "Revenue growth & client relationships"),
            ("SR-BDM", "Business Development Manager", "New client acquisitions & accounts"),
            ("OPS-LEAD", "Operations Support Lead", "Service delivery & 24/7 client support"),
            ("DEVOPS-ENG", "DevOps & Cloud Engineer", "Infrastructure as code & Kubernetes"),
        ]
        desig_map: dict[str, Designation] = {}
        for code, name, desc in desig_specs:
            desig = await session.scalar(select(Designation).where(Designation.code == code))
            if desig is None:
                desig = Designation(
                    erp_id=f"DESIG-{code}",
                    name=name,
                    code=code,
                    description=desc,
                    is_active=True,
                )
                session.add(desig)
                await session.flush()
            desig_map[code] = desig

        # 6. Shifts
        shift_specs = [
            ("SHIFT-GEN", "General Day Shift (09:30 - 18:30)", "GEN", time(9, 30), time(18, 30), False, 15, 60),
            ("SHIFT-MORN", "Early Morning Shift (06:30 - 15:30)", "MORN", time(6, 30), time(15, 30), False, 15, 60),
            ("SHIFT-EVE", "Evening Support Shift (14:30 - 23:30)", "EVE", time(14, 30), time(23, 30), False, 15, 60),
            ("SHIFT-NIGHT", "US Overlap Night Shift (21:30 - 06:30)", "NIGHT", time(21, 30), time(6, 30), True, 15, 60),
        ]
        shift_map: dict[str, Shift] = {}
        for erp_id, name, code, st, et, cross, grace, brk in shift_specs:
            s = await session.scalar(select(Shift).where(Shift.code == code))
            if s is None:
                s = Shift(
                    erp_id=erp_id,
                    unit_id=unit_map["HYD-01"].id,
                    name=name,
                    code=code,
                    start_time=st,
                    end_time=et,
                    grace_minutes=grace,
                    break_minutes=brk,
                    is_cross_midnight=cross,
                    is_active=True,
                    begin_check_in_before_minutes=60,
                    allow_check_out_after_minutes=60,
                    late_entry_grace_minutes=grace,
                    early_exit_grace_minutes=grace,
                    half_day_threshold_hours=4.5,
                    absent_threshold_hours=2.0,
                    enable_auto_attendance=True,
                )
                session.add(s)
                await session.flush()
            shift_map[code] = s

        # 7. Holiday List & 2026 Indian Gazetted Holidays
        hlist = await session.scalar(
            select(HolidayList).where(HolidayList.name == "Indian National & Gazetted Holidays 2026")
        )
        if hlist is None:
            hlist = HolidayList(
                unit_id=None,
                name="Indian National & Gazetted Holidays 2026",
                from_date=date(2026, 1, 1),
                to_date=date(2026, 12, 31),
                weekly_off_day="Sunday",
                is_default=True,
            )
            session.add(hlist)
            await session.flush()

        indian_holidays_2026 = [
            ("HOL-2026-01", "Republic Day", "Celebration of the Constitution of India", date(2026, 1, 26)),
            ("HOL-2026-02", "Maha Shivratri", "Celebration of Lord Shiva", date(2026, 2, 16)),
            ("HOL-2026-03", "Holi", "Festival of colors and spring", date(2026, 3, 3)),
            ("HOL-2026-04", "Eid-ul-Fitr", "Islamic festival marking the end of Ramadan", date(2026, 3, 20)),
            ("HOL-2026-05", "Good Friday", "Christian observance", date(2026, 4, 3)),
            ("HOL-2026-06", "Dr. B.R. Ambedkar Jayanti", "Birth anniversary of Dr. B. R. Ambedkar", date(2026, 4, 14)),
            ("HOL-2026-07", "Maharashtra Day / May Day", "International Workers' Day", date(2026, 5, 1)),
            ("HOL-2026-08", "Bakrid / Eid al-Adha", "Feast of Sacrifice", date(2026, 5, 27)),
            ("HOL-2026-09", "Independence Day", "Celebration of Indian Independence", date(2026, 8, 15)),
            ("HOL-2026-10", "Raksha Bandhan", "Festival celebrating sibling relationships", date(2026, 8, 28)),
            ("HOL-2026-11", "Janmashtami", "Celebration of Lord Krishna's birth", date(2026, 9, 4)),
            (
                "HOL-2026-12",
                "Mahatma Gandhi Jayanti",
                "Birthday of Mahatma Gandhi (National Holiday)",
                date(2026, 10, 2),
            ),
            ("HOL-2026-13", "Dussehra (Vijayadashami)", "Triumph of virtue over evil", date(2026, 10, 20)),
            ("HOL-2026-14", "Diwali (Deepavali)", "Festival of lights", date(2026, 11, 8)),
            ("HOL-2026-15", "Govardhan Puja", "Day of devotion and Annakut", date(2026, 11, 9)),
            ("HOL-2026-16", "Guru Nanak Jayanti", "Birth celebration of Guru Nanak Dev Ji", date(2026, 11, 24)),
            ("HOL-2026-17", "Christmas Day", "Christmas celebration", date(2026, 12, 25)),
        ]
        for erp_hid, hname, hdesc, hdate in indian_holidays_2026:
            h = await session.scalar(select(Holiday).where(Holiday.erp_holiday_id == erp_hid))
            if h is None:
                h = Holiday(
                    erp_holiday_id=erp_hid,
                    holiday_list_id=hlist.id,
                    name=hname,
                    description=hdesc,
                    holiday_date=hdate,
                    is_weekly_off=False,
                    is_organization_wide=True,
                )
                session.add(h)
        await session.flush()

        # 8. Leave Period & Leave Types
        lp = await session.scalar(select(LeavePeriod).where(LeavePeriod.name == "Calendar Year 2026"))
        if lp is None:
            lp = LeavePeriod(
                name="Calendar Year 2026",
                from_date=date(2026, 1, 1),
                to_date=date(2026, 12, 31),
                is_active=True,
            )
            session.add(lp)
            await session.flush()

        ltype_specs = [
            ("Casual Leave", "CL", True, 12, 3, True, False, False),
            ("Earned / Privilege Leave", "EL", True, 18, 15, True, True, False),
            ("Sick Leave", "SL", True, 10, 5, True, False, False),
            ("Compensatory Off", "COMP", True, 6, 2, True, False, False),
            ("Maternity Leave", "ML", True, 180, 180, True, False, True),
            ("Paternity Leave", "PL", True, 15, 15, True, False, False),
            ("Loss of Pay", "LOP", False, 0, None, True, False, False),
        ]
        ltype_map: dict[str, LeaveType] = {}
        for name, code, paid, alloc, max_c, req_app, cf, inc_h in ltype_specs:
            lt = await session.scalar(select(LeaveType).where(LeaveType.code == code))
            if lt is None:
                lt = LeaveType(
                    name=name,
                    code=code,
                    is_paid=paid,
                    annual_allocation=alloc,
                    max_consecutive_days=max_c,
                    requires_approval=req_app,
                    carry_forward=cf,
                    include_holidays=inc_h,
                    is_active=True,
                )
                session.add(lt)
                await session.flush()
            ltype_map[code] = lt

        # 9. Key Executive and Manager Personas (Standard Indian names)
        # Structure: (username, first_name, last_name, email, mobile, role, business_role, scope, scope_unit, dept_code, desig_code, salary)
        leadership_specs = [
            # CEO / Org Owner
            (
                "rajesh.sharma",
                "Rajesh",
                "Sharma",
                "rajesh.sharma@bharatdynamics.co.in",
                "+919810101010",
                ORGANIZATION_OWNER,
                ORGANIZATION_OWNER,
                SCOPE_ORGANIZATION,
                None,
                "ENG-HYD",
                "CEO",
                380000.00,
            ),
            # HR Director (Org HR Admin)
            (
                "priya.nair",
                "Priya",
                "Nair",
                "priya.nair@bharatdynamics.co.in",
                "+919820202020",
                HR_ADMIN,
                HR_ADMIN,
                SCOPE_ORGANIZATION,
                None,
                "HR-HYD",
                "DIR-HR",
                260000.00,
            ),
            # Bengaluru Unit HR Admin
            (
                "ananya.iyer",
                "Ananya",
                "Iyer",
                "ananya.iyer@bharatdynamics.co.in",
                "+919830303030",
                HR_ADMIN,
                HR_ADMIN,
                SCOPE_UNIT,
                "BLR-01",
                "HR-BLR",
                "LEAD-HRBP",
                165000.00,
            ),
            # Hyderabad Unit HR Admin
            (
                "suresh.reddy",
                "Suresh",
                "Reddy",
                "suresh.reddy@bharatdynamics.co.in",
                "+919840404040",
                HR_ADMIN,
                HR_ADMIN,
                SCOPE_UNIT,
                "HYD-01",
                "HR-HYD",
                "HRBP",
                140000.00,
            ),
            # Engineering Manager (Hyd)
            (
                "vikram.malhotra",
                "Vikram",
                "Malhotra",
                "vikram.malhotra@bharatdynamics.co.in",
                "+919850505050",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "ENG-HYD",
                "ENG-MGR",
                225000.00,
            ),
            # Core Platform Engineering Manager (Blr)
            (
                "rohit.verma",
                "Rohit",
                "Verma",
                "rohit.verma@bharatdynamics.co.in",
                "+919860606060",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "ENG-BLR",
                "DIR-ENG",
                245000.00,
            ),
            # Product Manager (Blr)
            (
                "sneha.rao",
                "Sneha",
                "Rao",
                "sneha.rao@bharatdynamics.co.in",
                "+919870707070",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "PRD-BLR",
                "LEAD-PM",
                210000.00,
            ),
            # QA Lead (Hyd)
            (
                "arjun.kapoor",
                "Arjun",
                "Kapoor",
                "arjun.kapoor@bharatdynamics.co.in",
                "+919880808080",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "QA-HYD",
                "SR-QA",
                175000.00,
            ),
            # Finance Manager (Bom)
            (
                "kavita.deshmukh",
                "Kavita",
                "Deshmukh",
                "kavita.deshmukh@bharatdynamics.co.in",
                "+919890909090",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "FIN-BOM",
                "FIN-MGR",
                195000.00,
            ),
            # Sales Director (Bom)
            (
                "amit.sen",
                "Amit",
                "Sen",
                "amit.sen@bharatdynamics.co.in",
                "+919900000000",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "SLS-BOM",
                "SALES-DIR",
                230000.00,
            ),
            # Operations Lead (Ggn)
            (
                "deepak.joshi",
                "Deepak",
                "Joshi",
                "deepak.joshi@bharatdynamics.co.in",
                "+919911111111",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                None,
                "OPS-GGN",
                "OPS-LEAD",
                160000.00,
            ),
        ]

        created_employees: list[Employee] = []
        emp_code_counter = 100

        ceo_employee: Employee | None = None
        manager_employees: dict[str, Employee] = {}

        for (
            uname,
            fname,
            lname,
            email,
            mobile,
            role,
            b_role,
            scope,
            scope_unit_code,
            dcode,
            descode,
            sal,
        ) in leadership_specs:
            user = await session.scalar(select(User).where(User.username == uname))
            if user is None:
                user = User(
                    username=uname,
                    email=email,
                    first_name=fname,
                    last_name=lname,
                    mobile_number=mobile,
                    hashed_password=shared_dev_password_hash,
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                )
                session.add(user)
                await session.flush()

            emp_code_counter += 1
            code_str = f"BDTS-{emp_code_counter:04d}"
            emp = await session.scalar(select(Employee).where(Employee.official_email == email))
            scope_id = unit_map[scope_unit_code].id if scope == SCOPE_UNIT and scope_unit_code else None
            dept = dept_map[dcode]
            unit = dept.unit

            bank_name, bcode = random.choice(INDIAN_BANKS)
            if emp is None:
                emp = Employee(
                    erp_id=f"ERP-{code_str}",
                    user_id=user.id,
                    employee_code=code_str,
                    role=role,
                    business_role=b_role,
                    access_scope=scope,
                    access_scope_id=scope_id,
                    first_name=fname,
                    last_name=lname,
                    official_email=email,
                    personal_email=f"{uname}.personal@gmail.com",
                    phone_number=mobile,
                    date_of_birth=date(random.randint(1978, 1990), random.randint(1, 12), random.randint(1, 28)),
                    gender="MALE"
                    if fname in ["Rajesh", "Suresh", "Vikram", "Rohit", "Arjun", "Amit", "Deepak"]
                    else "FEMALE",
                    marital_status="MARRIED",
                    blood_group=random.choice(BLOOD_GROUPS),
                    emergency_contact_name=f"{fake.name()}",
                    emergency_contact_phone=gen_mobile(),
                    emergency_contact_relation="Spouse",
                    current_address=f"{fake.street_address()}, {dept.unit.city}, India",
                    permanent_address=f"{fake.street_address()}, {dept.unit.city}, India",
                    pan_number=gen_pan(),
                    aadhaar_number=gen_aadhaar(),
                    bank_name=bank_name,
                    bank_account_number=gen_bank_account(),
                    bank_ifsc_code=gen_ifsc(bcode),
                    department_id=dept.id,
                    unit_id=unit.id,
                    designation_id=desig_map[descode].id,
                    designation=desig_map[descode].name,
                    reporting_manager_id=ceo_employee.id if ceo_employee and descode != "CEO" else None,
                    shift_id=shift_map["GEN"].id,
                    date_of_joining=date(2020, 4, 1),
                    employment_type="PERMANENT",
                    status="ACTIVE",
                    biometric_id=f"BIO-{code_str}",
                    monthly_salary=Decimal(str(sal)),
                    overtime_eligible=False,
                )
                session.add(emp)
                await session.flush()

            if descode == "CEO":
                ceo_employee = emp
            else:
                manager_employees[dcode] = emp
            created_employees.append(emp)

        # 10. Generate Workforce Members across Departments using Faker
        dept_keys = list(dept_map.keys())
        engineering_desigs = ["PRIN-SE", "SR-SE", "SE", "ASE", "DEVOPS-ENG"]
        qa_desigs = ["SR-QA", "QA-ENG"]
        product_desigs = ["LEAD-PM", "SR-SE"]
        hr_desigs = ["HRBP", "SR-TAS"]
        fin_desigs = ["SR-FIN"]
        sales_desigs = ["SR-BDM"]
        ops_desigs = ["OPS-LEAD"]

        total_workforce = max(num_employees - len(created_employees), 15)

        for i in range(total_workforce):
            emp_code_counter += 1
            code_str = f"BDTS-{emp_code_counter:04d}"

            # Pick a department and its appropriate manager
            dcode = dept_keys[i % len(dept_keys)]
            dept = dept_map[dcode]
            unit = dept.unit

            # Pick designation matching the department
            if "ENG" in dcode:
                des_code = random.choice(engineering_desigs)
            elif "QA" in dcode:
                des_code = random.choice(qa_desigs)
            elif "PRD" in dcode:
                des_code = random.choice(product_desigs)
            elif "HR" in dcode:
                des_code = random.choice(hr_desigs)
            elif "FIN" in dcode:
                des_code = random.choice(fin_desigs)
            elif "SLS" in dcode:
                des_code = random.choice(sales_desigs)
            else:
                des_code = random.choice(ops_desigs)

            desig = desig_map[des_code]

            # Generate natural Indian name & clean username
            full_name = fake.name()
            name_parts = full_name.split()
            fname = name_parts[0]
            lname = name_parts[-1] if len(name_parts) > 1 else "Kumar"
            clean_fname = "".join(c for c in fname.lower() if c.isalnum())
            clean_lname = "".join(c for c in lname.lower() if c.isalnum())
            uname = f"{clean_fname}.{clean_lname}.{emp_code_counter}"
            email = f"{clean_fname}.{clean_lname}.{emp_code_counter}@bharatdynamics.co.in"
            mobile = gen_mobile()

            user = await session.scalar(select(User).where(User.username == uname))
            if user is None:
                user = User(
                    username=uname,
                    email=email,
                    first_name=fname,
                    last_name=lname,
                    mobile_number=mobile,
                    hashed_password=shared_dev_password_hash,
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                )
                session.add(user)
                await session.flush()

            # Assign reporting manager: department manager if available, else CEO
            rep_mgr = manager_employees.get(dcode, ceo_employee)
            bank_name, bcode = random.choice(INDIAN_BANKS)

            # Assign shift: mostly General, some Evening or Night for Ops/Engineering
            if "OPS" in dcode:
                shift_choice = shift_map[random.choice(["GEN", "MORN", "EVE"])]
            elif "ENG" in dcode and i % 5 == 0:
                shift_choice = shift_map["NIGHT"]
            else:
                shift_choice = shift_map["GEN"]

            sal = round(random.uniform(42000.0, 145000.0), 2)
            joining_year = random.choice([2021, 2022, 2023, 2024, 2025])
            joining_month = random.randint(1, 12)
            joining_day = random.randint(1, 28)

            emp = await session.scalar(select(Employee).where(Employee.official_email == email))
            if emp is None:
                emp = Employee(
                    erp_id=f"ERP-{code_str}",
                    user_id=user.id,
                    employee_code=code_str,
                    role=EMPLOYEE,
                    business_role=None,
                    access_scope=SCOPE_SELF,
                    access_scope_id=None,
                    first_name=fname,
                    last_name=lname,
                    official_email=email,
                    personal_email=f"{clean_fname}.{clean_lname}.personal@gmail.com",
                    phone_number=mobile,
                    date_of_birth=date(random.randint(1991, 2002), random.randint(1, 12), random.randint(1, 28)),
                    gender=random.choice(["MALE", "FEMALE"]),
                    marital_status=random.choice(["SINGLE", "MARRIED"]),
                    blood_group=random.choice(BLOOD_GROUPS),
                    emergency_contact_name=f"{fake.name()}",
                    emergency_contact_phone=gen_mobile(),
                    emergency_contact_relation=random.choice(INDIAN_RELATIONS),
                    current_address=f"{fake.street_address()}, {dept.unit.city}, India",
                    permanent_address=f"{fake.street_address()}, {dept.unit.city}, India",
                    pan_number=gen_pan(),
                    aadhaar_number=gen_aadhaar(),
                    bank_name=bank_name,
                    bank_account_number=gen_bank_account(),
                    bank_ifsc_code=gen_ifsc(bcode),
                    department_id=dept.id,
                    unit_id=unit.id,
                    designation_id=desig.id,
                    designation=desig.name,
                    reporting_manager_id=rep_mgr.id if rep_mgr else None,
                    shift_id=shift_choice.id,
                    date_of_joining=date(joining_year, joining_month, joining_day),
                    employment_type="PERMANENT",
                    status="ACTIVE",
                    biometric_id=f"BIO-{code_str}",
                    monthly_salary=Decimal(str(sal)),
                    overtime_eligible=True,
                )
                session.add(emp)
                await session.flush()

            created_employees.append(emp)

        # 11. Department Approvers
        # For each department, link designated approvers for LEAVE, SHIFT, EXPENSE, WORK_ARRANGEMENT
        for dcode, dept in dept_map.items():
            mgr_emp = manager_employees.get(dcode, ceo_employee)
            if not mgr_emp or not mgr_emp.user_id:
                continue

            for app_type in ["LEAVE", "SHIFT", "EXPENSE", "WORK_ARRANGEMENT"]:
                existing_app = await session.scalar(
                    select(DepartmentApprover).where(
                        (DepartmentApprover.department_id == dept.id) & (DepartmentApprover.approver_type == app_type)
                    )
                )
                if existing_app is None:
                    session.add(
                        DepartmentApprover(
                            department_id=dept.id,
                            user_id=mgr_emp.user_id,
                            approver_type=app_type,
                        )
                    )
        await session.flush()

        # 12. Shift Assignments
        for emp in created_employees:
            existing_sa = await session.scalar(select(ShiftAssignment).where(ShiftAssignment.employee_id == emp.id))
            if existing_sa is None:
                session.add(
                    ShiftAssignment(
                        employee_id=emp.id,
                        shift_id=emp.shift_id or shift_map["GEN"].id,
                        effective_from=emp.date_of_joining or date(2026, 1, 1),
                        status="ACTIVE",
                        assigned_by=superadmin.id,
                    )
                )
        await session.flush()

        # 13. Leave Allocations, Leave Balances, and Leave Ledger Entries
        alloc_count = 0
        balance_count = 0
        ledger_count = 0
        ledger_trans_id = 1000

        for emp in created_employees:
            for lcode in ["CL", "EL", "SL", "COMP"]:
                lt = ltype_map[lcode]
                alloc = await session.scalar(
                    select(LeaveAllocation).where(
                        (LeaveAllocation.employee_id == emp.id)
                        & (LeaveAllocation.leave_type_id == lt.id)
                        & (LeaveAllocation.leave_period_id == lp.id)
                    )
                )
                cf = 3.0 if lcode == "EL" else 0.0
                total_alloc = float(lt.annual_allocation) + cf

                if alloc is None:
                    alloc = LeaveAllocation(
                        employee_id=emp.id,
                        leave_type_id=lt.id,
                        leave_period_id=lp.id,
                        new_leaves_allocated=float(lt.annual_allocation),
                        carry_forwarded_leaves=cf,
                        total_leaves_allocated=total_alloc,
                        notes=f"Annual allocation for {lp.name}",
                    )
                    session.add(alloc)
                    alloc_count += 1

                bal = await session.scalar(
                    select(LeaveBalance).where(
                        (LeaveBalance.employee_id == emp.id)
                        & (LeaveBalance.leave_type_id == lt.id)
                        & (LeaveBalance.year == 2026)
                    )
                )
                if bal is None:
                    bal = LeaveBalance(
                        employee_id=emp.id,
                        leave_type_id=lt.id,
                        year=2026,
                        allocated=Decimal(str(total_alloc)),
                        used=Decimal("0.0"),
                        pending=Decimal("0.0"),
                    )
                    session.add(bal)
                    balance_count += 1

                ledger_trans_id += 1
                entry = await session.scalar(
                    select(LeaveLedgerEntry).where(
                        (LeaveLedgerEntry.transaction_type == "ALLOCATION")
                        & (LeaveLedgerEntry.transaction_id == ledger_trans_id)
                    )
                )
                if entry is None:
                    entry = LeaveLedgerEntry(
                        employee_id=emp.id,
                        leave_type_id=lt.id,
                        transaction_type="ALLOCATION",
                        transaction_id=ledger_trans_id,
                        leaves=total_alloc,
                        from_date=date(2026, 1, 1),
                        to_date=date(2026, 12, 31),
                        is_carry_forward=(cf > 0),
                        is_expired=False,
                    )
                    session.add(entry)
                    ledger_count += 1
        await session.flush()

        # 14. Leave Applications (Realistic Indian reasons & statuses)
        leave_app_count = 0
        sample_employees = created_employees[:25]  # first 25 employees have leave applications

        for idx, emp in enumerate(sample_employees):
            # Create 1-3 applications throughout 2026
            num_apps = random.randint(1, 3)
            for a_idx in range(num_apps):
                lcode = random.choice(["CL", "EL", "SL"])
                lt = ltype_map[lcode]
                app_month = random.randint(1, 10)
                app_day = random.randint(1, 25)
                fdate = date(2026, app_month, app_day)
                duration = random.choice([1.0, 2.0, 3.0])
                tdate = fdate + timedelta(days=int(duration) - 1)
                reason_text = LEAVE_REASONS[(idx + a_idx) % len(LEAVE_REASONS)]

                status_choices = ["APPROVED", "APPROVED", "PENDING", "REJECTED"]
                status = status_choices[(idx + a_idx) % len(status_choices)]

                rep_user_id = emp.reporting_manager.user_id if emp.reporting_manager else superadmin.id

                la = LeaveApplication(
                    employee_id=emp.id,
                    leave_type_id=lt.id,
                    leave_period_id=lp.id,
                    from_date=fdate,
                    to_date=tdate,
                    half_day=False,
                    days_count=duration,
                    reason=reason_text,
                    status=status,
                    applied_at=datetime(2026, app_month, max(1, app_day - 3), 10, 30, tzinfo=IST),
                    actioned_by=rep_user_id if status != "PENDING" else None,
                    actioned_at=datetime(2026, app_month, max(1, app_day - 1), 14, 0, tzinfo=IST)
                    if status != "PENDING"
                    else None,
                    rejection_reason="Sprint delivery commitment; please adjust dates"
                    if status == "REJECTED"
                    else None,
                    erp_event_id=f"LEAVE-EVT-{emp.id}-{app_month}-{app_day}",
                    erp_sync_status="SYNCED" if status == "APPROVED" else "PENDING",
                    erp_synced_at=datetime(2026, app_month, app_day, 9, 0, tzinfo=IST)
                    if status == "APPROVED"
                    else None,
                )
                session.add(la)
                await session.flush()
                leave_app_count += 1

                # If approved, update balance and add ledger debit entry
                if status == "APPROVED":
                    bal = await session.scalar(
                        select(LeaveBalance).where(
                            (LeaveBalance.employee_id == emp.id)
                            & (LeaveBalance.leave_type_id == lt.id)
                            & (LeaveBalance.year == 2026)
                        )
                    )
                    if bal:
                        bal.used = Decimal(str(float(bal.used) + duration))

                    ledger_trans_id += 1
                    session.add(
                        LeaveLedgerEntry(
                            employee_id=emp.id,
                            leave_type_id=lt.id,
                            transaction_type="APPLICATION",
                            transaction_id=ledger_trans_id,
                            leaves=-duration,
                            from_date=fdate,
                            to_date=tdate,
                            is_carry_forward=False,
                            is_expired=False,
                        )
                    )

                    # Also publish ERP Outbox Event
                    session.add(
                        ErpOutboxEvent(
                            event_id=f"LEAVE-{la.id}-APPROVED",
                            entity_type="LEAVE",
                            entity_id=la.id,
                            event_type="LEAVE_APPROVED",
                            payload={
                                "application_id": la.id,
                                "employee_code": emp.employee_code,
                                "leave_type": lt.code,
                                "from_date": fdate.isoformat(),
                                "to_date": tdate.isoformat(),
                                "days_count": duration,
                                "status": "APPROVED",
                            },
                            delivery_attempts=1,
                            acknowledged_at=datetime(2026, app_month, app_day, 9, 30, tzinfo=IST),
                            acknowledged_by="ERP_DAEMON",
                        )
                    )

        # 15. Work Arrangement Requests (WFH, Out Duty, Field Work)
        wfh_count = 0
        for idx, emp in enumerate(created_employees[:20]):
            wfh_month = random.choice([8, 9, 10])
            wfh_day = random.randint(1, 20)
            fdate = date(2026, wfh_month, wfh_day)
            tdate = fdate + timedelta(days=random.choice([0, 1]))
            atype = random.choice(["WORK_FROM_HOME", "WORK_FROM_HOME", "OUT_DUTY", "FIELD_WORK"])
            wfh_reason = WFH_REASONS[idx % len(WFH_REASONS)]
            status = "APPROVED" if idx % 4 != 0 else "PENDING"
            rep_user_id = emp.reporting_manager.user_id if emp.reporting_manager else superadmin.id

            war = WorkArrangementRequest(
                employee_id=emp.id,
                arrangement_type=atype,
                from_date=fdate,
                to_date=tdate,
                reason=wfh_reason,
                destination_location=f"Residence / Client Office - {emp.unit.city if emp.unit else 'Bengaluru'}",
                contact_phone=emp.phone_number,
                status=status,
                actioned_by=rep_user_id if status == "APPROVED" else None,
                actioned_at=datetime(2026, wfh_month, wfh_day, 9, 0, tzinfo=IST) if status == "APPROVED" else None,
            )
            session.add(war)
            wfh_count += 1
        await session.flush()

        # 16. Attendance Records & Biometric Punches
        # Generate for past 20 business days (Sept 22, 2026 to Oct 21, 2026)
        att_record_count = 0
        punch_count = 0
        overtime_count = 0
        correction_count = 0

        # Coordinates for Indian tech campuses
        city_coords = {
            "Hyderabad": (17.4435, 78.3772),
            "Bengaluru": (12.9716, 77.5946),
            "Mumbai": (19.0760, 72.8777),
            "Pune": (18.5204, 73.8567),
            "Gurugram": (28.4595, 77.0266),
        }

        # Collect holidays for date checking
        holiday_dates = {h[3] for h in indian_holidays_2026}

        work_dates: list[date] = []
        cur_d = date(2026, 9, 22)
        end_d = date(2026, 10, 21)
        while cur_d <= end_d:
            # Skip Sundays and Gazetted Holidays
            if cur_d.weekday() != 6 and cur_d not in holiday_dates:
                work_dates.append(cur_d)
            cur_d += timedelta(days=1)

        # Seed attendance for a representative cohort of 20 employees
        att_cohort = created_employees[:20]

        for emp in att_cohort:
            unit_city = emp.unit.city if emp.unit and emp.unit.city in city_coords else "Hyderabad"
            lat_base, lng_base = city_coords[unit_city]

            for d_idx, att_date in enumerate(work_dates):
                # Pattern: mostly PRESENT, occasionally WFH, HALF_DAY, or LATE
                day_rand = (emp.id * 17 + d_idx * 31) % 100

                if day_rand < 82:
                    # Regular Present Day
                    status = "PRESENT"
                    in_min = random.randint(15, 42)  # 09:15 to 09:42
                    out_min = random.randint(30, 75)  # 18:30 to 19:15
                    p_in = time(9, in_min)
                    p_out = time(18, out_min % 60) if out_min < 60 else time(19, out_min - 60)
                    worked = 8 * 60 + (out_min - in_min)
                    late = max(0, in_min - 30)  # Grace is 15 mins (past 09:45)
                    early = 0
                    ot_mins = max(0, out_min - 30) if emp.overtime_eligible else 0
                elif day_rand < 92:
                    # Work From Home
                    status = "WORK_FROM_HOME"
                    p_in = time(9, 30)
                    p_out = time(18, 30)
                    worked = 8 * 60
                    late = 0
                    early = 0
                    ot_mins = 0
                elif day_rand < 97:
                    # Half Day
                    status = "HALF_DAY"
                    p_in = time(9, 30)
                    p_out = time(14, 0)
                    worked = 4 * 60 + 30
                    late = 0
                    early = 4 * 60 + 30
                    ot_mins = 0
                else:
                    # On Leave
                    status = "ON_LEAVE"
                    p_in = None
                    p_out = None
                    worked = 0
                    late = 0
                    early = 0
                    ot_mins = 0

                rec = AttendanceRecord(
                    employee_id=emp.id,
                    attendance_date=att_date,
                    shift_id=emp.shift_id or shift_map["GEN"].id,
                    status=status,
                    punch_in=p_in,
                    punch_out=p_out,
                    worked_minutes=worked,
                    overtime_minutes=ot_mins,
                    late_minutes=late,
                    early_exit_minutes=early,
                    source="BIOMETRIC" if status == "PRESENT" else "HRMS",
                    sync_status="SYNCED",
                )
                session.add(rec)
                await session.flush()
                att_record_count += 1

                # If present, add Biometric Punch IN and OUT
                if p_in and p_out:
                    lat_jitter = lat_base + random.uniform(-0.005, 0.005)
                    lng_jitter = lng_base + random.uniform(-0.005, 0.005)

                    in_dt = datetime(
                        att_date.year, att_date.month, att_date.day, p_in.hour, p_in.minute, 12, tzinfo=IST
                    )
                    out_dt = datetime(
                        att_date.year, att_date.month, att_date.day, p_out.hour, p_out.minute, 45, tzinfo=IST
                    )

                    session.add(
                        AttendancePunch(
                            employee_id=emp.id,
                            punch_time=in_dt,
                            punch_type="IN",
                            source="BIOMETRIC",
                            device_id=f"BIO-{unit_city[:3].upper()}-GATE1",
                            shift_id=emp.shift_id or shift_map["GEN"].id,
                            attendance_record_id=rec.id,
                            is_processed=True,
                            latitude=lat_jitter,
                            longitude=lng_jitter,
                        )
                    )
                    session.add(
                        AttendancePunch(
                            employee_id=emp.id,
                            punch_time=out_dt,
                            punch_type="OUT",
                            source="BIOMETRIC",
                            device_id=f"BIO-{unit_city[:3].upper()}-GATE2",
                            shift_id=emp.shift_id or shift_map["GEN"].id,
                            attendance_record_id=rec.id,
                            is_processed=True,
                            latitude=lat_jitter,
                            longitude=lng_jitter,
                        )
                    )
                    punch_count += 2

                # If overtime was worked, create an OvertimeRecord
                if ot_mins >= 30 and emp.overtime_eligible:
                    ot_rec = OvertimeRecord(
                        employee_id=emp.id,
                        attendance_record_id=rec.id,
                        calculated_minutes=ot_mins,
                        approved_minutes=ot_mins if d_idx % 3 != 0 else 0,
                        status="APPROVED" if d_idx % 3 != 0 else "PENDING",
                        actioned_by=emp.reporting_manager.user_id if emp.reporting_manager and d_idx % 3 != 0 else None,
                        actioned_at=datetime(att_date.year, att_date.month, att_date.day, 20, 0, tzinfo=IST)
                        if d_idx % 3 != 0
                        else None,
                        erp_event_id=f"OT-{emp.id}-{att_date.isoformat()}",
                        source="HRMS",
                    )
                    session.add(ot_rec)
                    await session.flush()
                    overtime_count += 1

                    if ot_rec.status == "APPROVED":
                        session.add(
                            OvertimeApproval(
                                overtime_record_id=ot_rec.id,
                                approved_minutes=ot_mins,
                                actioned_by=emp.reporting_manager.user_id if emp.reporting_manager else superadmin.id,
                                actioned_at=datetime(att_date.year, att_date.month, att_date.day, 20, 15, tzinfo=IST),
                                remarks="Approved for critical release support and client deliverables",
                            )
                        )

                # Occasional missed punch discrepancy & correction request
                if day_rand == 96:
                    disc = AttendanceDiscrepancy(
                        attendance_record_id=rec.id,
                        discrepancy_type="MISSED_OUT_PUNCH",
                        status="RESOLVED",
                    )
                    session.add(disc)

                    corr = AttendanceCorrectionRequest(
                        attendance_record_id=rec.id,
                        requested_punch_in=time(9, 30),
                        requested_punch_out=time(18, 45),
                        reason=ATTENDANCE_CORRECTION_REASONS[emp.id % len(ATTENDANCE_CORRECTION_REASONS)],
                        status="APPROVED",
                        requested_at=datetime(att_date.year, att_date.month, att_date.day, 19, 0, tzinfo=IST),
                        actioned_by=emp.reporting_manager.user_id if emp.reporting_manager else superadmin.id,
                        actioned_at=datetime(att_date.year, att_date.month, att_date.day, 19, 30, tzinfo=IST),
                        sync_status="SYNCED",
                    )
                    session.add(corr)
                    correction_count += 1

        # 17. Employee Work Histories (Internal Indian Career Trajectories)
        wh_count = 0
        senior_cohort = created_employees[:10]
        for idx, emp in enumerate(senior_cohort):
            wh = EmployeeWorkHistory(
                employee_id=emp.id,
                unit_id=emp.unit_id,
                department_id=emp.department_id,
                designation_id=desig_map["SE"].id if emp.designation != "Software Engineer" else desig_map["ASE"].id,
                from_date=date(2022, 4, 1),
                to_date=date(2024, 3, 31),
                remarks=f"Annual appraisal promotion to {emp.designation} based on performance rating 4.8/5",
            )
            session.add(wh)
            wh_count += 1
        await session.flush()

        # 18. In-App Notifications and Receipts
        notifications_data = [
            (
                "Leave Request Approved",
                "Your Casual Leave application for 2 days has been approved by your reporting manager.",
                "LEAVE",
                created_employees[1].user_id,
            ),
            (
                "Holiday Announcement: Mahatma Gandhi Jayanti",
                "The organization will remain closed on Friday, 2nd October 2026, on account of Mahatma Gandhi Jayanti.",
                "ANNOUNCEMENT",
                None,  # Broadcast
            ),
            (
                "Holiday Announcement: Diwali Holidays",
                "Offices across all Indian units will observe Deepavali holidays on 8th & 9th November 2026.",
                "ANNOUNCEMENT",
                None,  # Broadcast
            ),
            (
                "Work Arrangement Approved",
                "Your Work From Home request has been approved. Please maintain status updates in team Slack.",
                "APPROVAL",
                created_employees[3].user_id,
            ),
            (
                "Attendance Regularization Reminder",
                "Please submit attendance regularization for any missing biometric punches before month-end payroll cutoff.",
                "ATTENDANCE",
                created_employees[5].user_id,
            ),
            (
                "Overtime Claim Approved",
                "Your overtime request for 90 minutes on project release deployment has been approved.",
                "OVERTIME",
                created_employees[7].user_id,
            ),
        ]
        notif_count = 0
        for title, msg, ntype, uid in notifications_data:
            notif = Notification(
                title=title,
                message=msg,
                notification_type=ntype,
                user_id=uid,
                is_read=False,
            )
            session.add(notif)
            await session.flush()
            notif_count += 1

            # Add receipts for relevant users
            if uid:
                session.add(NotificationReceipt(notification_id=notif.notification_id, user_id=uid))
            else:
                for emp in created_employees[:5]:
                    if emp.user_id:
                        session.add(NotificationReceipt(notification_id=notif.notification_id, user_id=emp.user_id))
        await session.flush()

        # 19. Security Audit Logs
        audit_entries = [
            ("VIEW_ORGANIZATION_ANALYTICS", "Organization", str(org.id), superadmin.id),
            ("UPDATE_BUSINESS_ROLE", "Employee", str(created_employees[1].id), superadmin.id),
            ("APPROVE_LEAVE_APPLICATION", "LeaveApplication", "1", created_employees[4].user_id),
            ("EXPORT_PAYROLL_ATTENDANCE", "AttendanceRecord", None, created_employees[2].user_id),
            ("CONFIGURE_HOLIDAY_CALENDAR", "HolidayList", str(hlist.id), superadmin.id),
        ]
        for action, etype, eid, uid in audit_entries:
            session.add(
                AuditLog(
                    actor_user_id=uid,
                    action=action,
                    entity_type=etype,
                    entity_id=eid,
                    request_id=f"REQ-{random.randint(100000, 999999)}",
                    ip_address="127.0.0.1",
                )
            )

        # 20. ERP Sync Batch Audit Records
        sync_batches = [
            ("BATCH-ERP-20261021-01", "/api/v1/integrations/erp/attendance", 25, 25, 0, 0),
            ("BATCH-ERP-20261021-02", "/api/v1/integrations/erp/bulk", 40, 40, 0, 0),
            ("BATCH-ERP-20261020-01", "/api/v1/integrations/erp/leaves/outbox/ack", 12, 12, 0, 0),
        ]
        for bid, endpoint, recv, acc, dup, failed in sync_batches:
            batch = await session.scalar(select(ErpSyncBatch).where(ErpSyncBatch.batch_id == bid))
            if batch is None:
                session.add(
                    ErpSyncBatch(
                        batch_id=bid,
                        endpoint=endpoint,
                        client_id="ERP-CONNECTOR-PROD",
                        received_count=recv,
                        accepted_count=acc,
                        duplicate_count=dup,
                        failed_count=failed,
                        retryable_failed_count=0,
                        status="COMPLETED",
                        http_status=200,
                    )
                )

        await session.commit()

    summary = {
        "organizations": 1,
        "units": len(units_spec),
        "departments": len(dept_specs),
        "designations": len(desig_specs),
        "shifts": len(shift_specs),
        "holidays": len(indian_holidays_2026),
        "leave_types": len(ltype_specs),
        "employees": len(created_employees),
        "leave_allocations": alloc_count,
        "leave_balances": balance_count,
        "leave_ledger_entries": ledger_count,
        "leave_applications": leave_app_count,
        "work_arrangement_requests": wfh_count,
        "attendance_records": att_record_count,
        "attendance_punches": punch_count,
        "overtime_records": overtime_count,
        "work_histories": wh_count,
        "notifications": notif_count,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed rich Indian English data for all HRMS entities.")
    parser.add_argument("--clean", action="store_true", help="Truncate application tables before seeding.")
    parser.add_argument("--num-employees", type=int, default=45, help="Total workforce size to seed (default: 45).")
    args = parser.parse_args()

    print("Starting Indian English data seeding with Faker (en_IN)...")
    res = asyncio.run(seed_indian_data(clean=args.clean, num_employees=args.num_employees))

    print("\n--- Seeding Completed Successfully! ---")
    for entity, count in res.items():
        print(f"  • {entity.replace('_', ' ').title()}: {count}")
    print(
        f"\nDefault credentials for workforce users: username (e.g. rajesh.sharma, priya.nair) / password: {DEV_PASSWORD}"
    )
    print("Super Admin credentials: from .env (admin@hrms.com / SuperAdmin@123)")


if __name__ == "__main__":
    main()
