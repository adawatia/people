"""Streamlined, minimal role-based seed data for People HRMS.

This script populates ONLY essential test personas and actionable flow data:
- Super Admin account (dev credentials)
- 1 Organization (Bharat Dynamics & Tech Solutions Ltd.)
- 2 Units (Hyderabad & Bengaluru)
- 4 Departments (Engineering & HR in Hyderabad and Bengaluru)
- 4 Key Designations (CEO, DIR-HR, ENG-MGR, SR-SE, SE, HRBP, HR-EXEC)
- 2 Shifts (General 09:30-18:30, Morning 06:30-15:30)
- 4 Gazetted Holidays (Republic Day, Independence Day, Gandhi Jayanti, Diwali)
- Leave Period (2026) and 5 Leave Types (CL, EL, SL, COMP, LOP)
- 14 Role Personas (CEO, HR Director, 2 Unit HRBPs, 2 Dept Managers, 8 Employees - 2 per department)
- Pre-wired testing states:
    - PENDING Leave Application (Rahul -> Vikram) ready to approve/reject
    - PENDING Attendance Correction (Rahul -> Vikram) ready to approve/reject
    - PENDING Work Arrangement / WFH (Rahul -> Vikram) ready to approve/reject
    - PENDING Overtime Claim (Rahul -> Vikram) ready to approve/reject
    - Cross-department boundary test (Priya -> Rohit) hidden from Vikram
    - In-app Notifications for manager and employee
    - Clean 3-day attendance punches for roster/dashboard verification

Usage:
    uv run python db/seed_indian_data.py --clean
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure parent directory (app/api) is in sys.path
_APP_API_DIR = str(Path(__file__).resolve().parent.parent)
if _APP_API_DIR not in sys.path:
    sys.path.insert(0, _APP_API_DIR)

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
    ErpOutboxEvent,
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
    OvertimeRecord,
    Shift,
    ShiftAssignment,
    Unit,
    User,
    WorkArrangementRequest,
)

IST = ZoneInfo("Asia/Kolkata")
DEV_PASSWORD = "HrmsDev@2026!"
PRESERVED_TABLES = frozenset({"alembic_version"})


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


async def seed_indian_data(*, clean: bool = False, **_kwargs) -> dict[str, int]:
    """Execute lean, role-focused seed data generation."""
    settings = get_settings()
    if clean:
        sync_engine = create_engine(settings.resolved_database_url_sync(), pool_pre_ping=True)
        clean_application_tables(sync_engine)
        sync_engine.dispose()

    password_helper = PasswordHelper()
    dev_pass_hash = password_helper.hash(DEV_PASSWORD)

    async with async_session_maker() as session:
        # 1. Super Admin Account
        admin_uname = settings.super_admin_username
        superadmin = await session.scalar(select(User).where(User.username == admin_uname))
        if superadmin is None:
            superadmin = User(
                email=settings.super_admin_email,
                username=admin_uname,
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

        # 2. Organization
        org = await session.scalar(select(Organization).order_by(Organization.id.asc()))
        if org is None:
            org = Organization(
                erp_id="ORG-BDTS-001",
                singleton_key=1,
                name="Bharat Dynamics & Tech Solutions Ltd.",
                short_name="BDTS",
                industry="Information Technology & Enterprise Services",
                address_line1="Tower 4, Cyber Gateway, HITEC City",
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

        # 3. Units (Hyderabad & Bengaluru Tech Hubs)
        units_spec = [
            ("UNIT-HYD-01", "Hyderabad Tech Campus", "HYD-01", "Hyderabad"),
            ("UNIT-BLR-01", "Bengaluru Innovation Hub", "BLR-01", "Bengaluru"),
        ]
        unit_map: dict[str, Unit] = {}
        for erp_id, name, code, city in units_spec:
            u = await session.scalar(select(Unit).where(Unit.code == code))
            if u is None:
                u = Unit(erp_id=erp_id, organization_id=org.id, name=name, code=code, city=city, is_active=True)
                session.add(u)
                await session.flush()
            unit_map[code] = u

        # 4. Departments (2 in Hyd, 2 in Blr)
        dept_specs = [
            ("ENG-HYD", "Engineering & Architecture", "HYD-01"),
            ("HR-HYD", "Human Resources Hyderabad", "HYD-01"),
            ("ENG-BLR", "Platform Engineering", "BLR-01"),
            ("HR-BLR", "Human Resources Bengaluru", "BLR-01"),
        ]
        dept_map: dict[str, Department] = {}
        for code, name, ucode in dept_specs:
            d = await session.scalar(select(Department).where(Department.code == code))
            if d is None:
                d = Department(erp_id=f"DEPT-{code}", unit_id=unit_map[ucode].id, name=name, code=code, is_active=True)
                session.add(d)
                await session.flush()
            dept_map[code] = d

        # 5. Designations
        desig_specs = [
            ("CEO", "Chief Executive Officer"),
            ("DIR-HR", "Director of Human Resources"),
            ("ENG-MGR", "Engineering Manager"),
            ("HRBP", "HR Business Partner"),
            ("SR-SE", "Senior Software Engineer"),
            ("SE", "Software Engineer"),
            ("HR-EXEC", "HR Operations Executive"),
        ]
        desig_map: dict[str, Designation] = {}
        for code, name in desig_specs:
            desig = await session.scalar(select(Designation).where(Designation.code == code))
            if desig is None:
                desig = Designation(erp_id=f"DESIG-{code}", name=name, code=code, is_active=True)
                session.add(desig)
                await session.flush()
            desig_map[code] = desig

        # 6. Shifts (General & Morning)
        shift_specs = [
            ("SHIFT-GEN", "General Day Shift (09:30 - 18:30)", "GEN", time(9, 30), time(18, 30)),
            ("SHIFT-MORN", "Early Morning Shift (06:30 - 15:30)", "MORN", time(6, 30), time(15, 30)),
        ]
        shift_map: dict[str, Shift] = {}
        for erp_id, name, code, st, et in shift_specs:
            s = await session.scalar(select(Shift).where(Shift.code == code))
            if s is None:
                s = Shift(
                    erp_id=erp_id,
                    unit_id=unit_map["HYD-01"].id,
                    name=name,
                    code=code,
                    start_time=st,
                    end_time=et,
                    grace_minutes=15,
                    break_minutes=60,
                    is_active=True,
                    enable_auto_attendance=True,
                )
                session.add(s)
                await session.flush()
            shift_map[code] = s

        # 7. Holidays (Key Indian Gazetted 2026)
        hlist = await session.scalar(select(HolidayList).where(HolidayList.name == "Indian Gazetted Holidays 2026"))
        if hlist is None:
            hlist = HolidayList(
                name="Indian Gazetted Holidays 2026",
                from_date=date(2026, 1, 1),
                to_date=date(2026, 12, 31),
                weekly_off_day="Sunday",
                is_default=True,
            )
            session.add(hlist)
            await session.flush()

        for hid, hname, hdate in [
            ("HOL-01", "Republic Day", date(2026, 1, 26)),
            ("HOL-02", "Independence Day", date(2026, 8, 15)),
            ("HOL-03", "Mahatma Gandhi Jayanti", date(2026, 10, 2)),
            ("HOL-04", "Diwali", date(2026, 11, 8)),
        ]:
            h = await session.scalar(select(Holiday).where(Holiday.erp_holiday_id == hid))
            if h is None:
                session.add(
                    Holiday(
                        erp_holiday_id=hid,
                        holiday_list_id=hlist.id,
                        name=hname,
                        holiday_date=hdate,
                        is_organization_wide=True,
                    )
                )
        await session.flush()

        # 8. Leave Period & Types
        lp = await session.scalar(select(LeavePeriod).where(LeavePeriod.name == "Calendar Year 2026"))
        if lp is None:
            lp = LeavePeriod(
                name="Calendar Year 2026", from_date=date(2026, 1, 1), to_date=date(2026, 12, 31), is_active=True
            )
            session.add(lp)
            await session.flush()

        ltype_specs = [
            ("Casual Leave", "CL", 12, 3, False),
            ("Privilege Leave", "EL", 18, 15, True),
            ("Sick Leave", "SL", 10, 5, False),
            ("Compensatory Off", "COMP", 6, 2, False),
            ("Loss of Pay", "LOP", 0, None, False),
        ]
        ltype_map: dict[str, LeaveType] = {}
        for name, code, alloc, max_c, cf in ltype_specs:
            lt = await session.scalar(select(LeaveType).where(LeaveType.code == code))
            if lt is None:
                lt = LeaveType(
                    name=name,
                    code=code,
                    is_paid=(code != "LOP"),
                    annual_allocation=alloc,
                    max_consecutive_days=max_c,
                    requires_approval=True,
                    carry_forward=cf,
                    is_active=True,
                )
                session.add(lt)
                await session.flush()
            ltype_map[code] = lt

        # 9. Role Personas (Executive, Managers, and 2 Direct Reports Per Department)
        # Structure: (uname, fname, lname, mobile, role, b_role, scope, unit_code, dept_code, desig_code, rep_mgr_uname)
        personas = [
            # Executive Leadership
            (
                "rajesh.sharma",
                "Rajesh",
                "Sharma",
                "+919810101010",
                ORGANIZATION_OWNER,
                ORGANIZATION_OWNER,
                SCOPE_ORGANIZATION,
                "HYD-01",
                "ENG-HYD",
                "CEO",
                None,
            ),
            (
                "priya.nair",
                "Priya",
                "Nair",
                "+919820202020",
                HR_ADMIN,
                HR_ADMIN,
                SCOPE_ORGANIZATION,
                "HYD-01",
                "HR-HYD",
                "DIR-HR",
                "rajesh.sharma",
            ),
            # Hyderabad Unit HRBP & Dept Manager
            (
                "suresh.reddy",
                "Suresh",
                "Reddy",
                "+919840404040",
                HR_ADMIN,
                HR_ADMIN,
                SCOPE_UNIT,
                "HYD-01",
                "HR-HYD",
                "HRBP",
                "priya.nair",
            ),
            (
                "vikram.malhotra",
                "Vikram",
                "Malhotra",
                "+919850505050",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                "HYD-01",
                "ENG-HYD",
                "ENG-MGR",
                "rajesh.sharma",
            ),
            # Bengaluru Unit HRBP & Dept Manager
            (
                "ananya.iyer",
                "Ananya",
                "Iyer",
                "+919830303030",
                HR_ADMIN,
                HR_ADMIN,
                SCOPE_UNIT,
                "BLR-01",
                "HR-BLR",
                "HRBP",
                "priya.nair",
            ),
            (
                "rohit.verma",
                "Rohit",
                "Verma",
                "+919860606060",
                DEPARTMENT_MANAGER,
                DEPARTMENT_MANAGER,
                SCOPE_DEPARTMENT,
                "BLR-01",
                "ENG-BLR",
                "ENG-MGR",
                "rajesh.sharma",
            ),
            # Department 1: ENG-HYD Team (2 Direct Reports under Vikram)
            (
                "rahul.sharma",
                "Rahul",
                "Sharma",
                "+919876543210",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "HYD-01",
                "ENG-HYD",
                "SR-SE",
                "vikram.malhotra",
            ),
            (
                "neha.gupta",
                "Neha",
                "Gupta",
                "+919876543211",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "HYD-01",
                "ENG-HYD",
                "SE",
                "vikram.malhotra",
            ),
            # Department 2: HR-HYD Team (2 Direct Reports under Suresh)
            (
                "kavya.nair",
                "Kavya",
                "Nair",
                "+919876543212",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "HYD-01",
                "HR-HYD",
                "HR-EXEC",
                "suresh.reddy",
            ),
            (
                "arun.kumar",
                "Arun",
                "Kumar",
                "+919876543213",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "HYD-01",
                "HR-HYD",
                "HR-EXEC",
                "suresh.reddy",
            ),
            # Department 3: ENG-BLR Team (2 Direct Reports under Rohit)
            (
                "priya.verma",
                "Priya",
                "Verma",
                "+919876543214",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "BLR-01",
                "ENG-BLR",
                "SR-SE",
                "rohit.verma",
            ),
            (
                "amit.patel",
                "Amit",
                "Patel",
                "+919876543215",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "BLR-01",
                "ENG-BLR",
                "SE",
                "rohit.verma",
            ),
            # Department 4: HR-BLR Team (2 Direct Reports under Ananya)
            (
                "pooja.deshmukh",
                "Pooja",
                "Deshmukh",
                "+919876543216",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "BLR-01",
                "HR-BLR",
                "HR-EXEC",
                "ananya.iyer",
            ),
            (
                "deepak.joshi",
                "Deepak",
                "Joshi",
                "+919876543217",
                EMPLOYEE,
                None,
                SCOPE_SELF,
                "BLR-01",
                "HR-BLR",
                "HR-EXEC",
                "ananya.iyer",
            ),
        ]

        emp_by_uname: dict[str, Employee] = {}
        created_employees: list[Employee] = []

        for idx, (uname, fn, ln, mob, role, brole, scope, ucode, dcode, descode, _) in enumerate(personas):
            email = f"{uname}@bharatdynamics.co.in"
            user = await session.scalar(select(User).where(User.username == uname))
            if user is None:
                user = User(
                    username=uname,
                    email=email,
                    first_name=fn,
                    last_name=ln,
                    mobile_number=mob,
                    hashed_password=dev_pass_hash,
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                )
                session.add(user)
                await session.flush()

            emp = await session.scalar(select(Employee).where(Employee.official_email == email))
            dept = dept_map[dcode]
            desig = desig_map[descode]
            unit = unit_map[ucode]

            if emp is None:
                code_str = f"BDTS-0{100 + idx}"
                emp = Employee(
                    erp_id=f"ERP-{code_str}",
                    user_id=user.id,
                    employee_code=code_str,
                    role=role,
                    business_role=brole,
                    access_scope=scope,
                    access_scope_id=unit.id if scope == SCOPE_UNIT else (dept.id if scope == SCOPE_DEPARTMENT else None),
                    first_name=fn,
                    last_name=ln,
                    official_email=email,
                    personal_email=f"{uname}.personal@gmail.com",
                    phone_number=mob,
                    date_of_birth=date(1993, 5, 15),
                    gender="MALE" if fn in ["Rajesh", "Suresh", "Vikram", "Rohit", "Rahul", "Arun", "Amit", "Deepak"] else "FEMALE",
                    marital_status="MARRIED" if idx < 6 else "SINGLE",
                    blood_group="O+",
                    emergency_contact_name=f"{fn} Emergency Contact",
                    emergency_contact_phone="+919800112233",
                    emergency_contact_relation="Spouse" if idx < 6 else "Parent",
                    current_address=f"Flat {101 + idx}, Tech View Apartments, {unit.city}, India",
                    permanent_address=f"Flat {101 + idx}, Tech View Apartments, {unit.city}, India",
                    pan_number=f"ABCDE{1000 + idx}F",
                    aadhaar_number=f"98765432{1000 + idx}",
                    bank_name="HDFC Bank",
                    bank_account_number=f"5010023456{100 + idx}",
                    bank_ifsc_code="HDFC0001234",
                    department_id=dept.id,
                    unit_id=unit.id,
                    designation_id=desig.id,
                    designation=desig.name,
                    shift_id=shift_map["GEN"].id,
                    date_of_joining=date(2023, 1, 1),
                    employment_type="PERMANENT",
                    status="ACTIVE",
                    biometric_id=f"BIO-{code_str}",
                    monthly_salary=Decimal("150000.00") if idx < 6 else Decimal("85000.00"),
                    overtime_eligible=True,
                )
                session.add(emp)
                await session.flush()

            emp_by_uname[uname] = emp
            created_employees.append(emp)

        # Wire reporting managers
        for uname, *_, rep_mgr_uname in personas:
            if rep_mgr_uname and rep_mgr_uname in emp_by_uname:
                emp_by_uname[uname].reporting_manager_id = emp_by_uname[rep_mgr_uname].id
        await session.flush()

        # 10. Department Approvers & Shift Assignments
        dept_manager_map = {
            "ENG-HYD": emp_by_uname["vikram.malhotra"],
            "HR-HYD": emp_by_uname["suresh.reddy"],
            "ENG-BLR": emp_by_uname["rohit.verma"],
            "HR-BLR": emp_by_uname["ananya.iyer"],
        }
        for dcode, dept in dept_map.items():
            mgr = dept_manager_map.get(dcode)
            if mgr and mgr.user_id:
                for app_type in ["LEAVE", "SHIFT", "EXPENSE", "WORK_ARRANGEMENT"]:
                    existing_app = await session.scalar(
                        select(DepartmentApprover).where(
                            (DepartmentApprover.department_id == dept.id)
                            & (DepartmentApprover.approver_type == app_type)
                        )
                    )
                    if existing_app is None:
                        session.add(
                            DepartmentApprover(department_id=dept.id, user_id=mgr.user_id, approver_type=app_type)
                        )

        for emp in created_employees:
            existing_sa = await session.scalar(select(ShiftAssignment).where(ShiftAssignment.employee_id == emp.id))
            if existing_sa is None:
                session.add(
                    ShiftAssignment(
                        employee_id=emp.id,
                        shift_id=shift_map["GEN"].id,
                        effective_from=date(2026, 1, 1),
                        status="ACTIVE",
                        assigned_by=superadmin.id,
                    )
                )
        await session.flush()

        # 11. Leave Allocations, Balances, and Opening Ledgers
        ledger_trans_id = 2000
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
                if alloc is None:
                    session.add(
                        LeaveAllocation(
                            employee_id=emp.id,
                            leave_type_id=lt.id,
                            leave_period_id=lp.id,
                            new_leaves_allocated=float(lt.annual_allocation),
                            carry_forwarded_leaves=3.0 if lcode == "EL" else 0.0,
                            total_leaves_allocated=float(lt.annual_allocation) + (3.0 if lcode == "EL" else 0.0),
                            notes=f"Annual allocation for {lp.name}",
                        )
                    )

                bal = await session.scalar(
                    select(LeaveBalance).where(
                        (LeaveBalance.employee_id == emp.id)
                        & (LeaveBalance.leave_type_id == lt.id)
                        & (LeaveBalance.year == 2026)
                    )
                )
                if bal is None:
                    session.add(
                        LeaveBalance(
                            employee_id=emp.id,
                            leave_type_id=lt.id,
                            year=2026,
                            allocated=Decimal(str(float(lt.annual_allocation) + (3.0 if lcode == "EL" else 0.0))),
                            used=Decimal("0.0"),
                            pending=Decimal("0.0"),
                        )
                    )

                ledger_trans_id += 1
                session.add(
                    LeaveLedgerEntry(
                        employee_id=emp.id,
                        leave_type_id=lt.id,
                        transaction_type="ALLOCATION",
                        transaction_id=ledger_trans_id,
                        leaves=float(lt.annual_allocation),
                        from_date=date(2026, 1, 1),
                        to_date=date(2026, 12, 31),
                        is_carry_forward=False,
                        is_expired=False,
                    )
                )
        await session.flush()

        # 12. Pre-Wired Actionable Flows for Manual Testing
        rahul = emp_by_uname["rahul.sharma"]
        neha = emp_by_uname["neha.gupta"]
        priya_v = emp_by_uname["priya.verma"]
        vikram = emp_by_uname["vikram.malhotra"]
        rohit = emp_by_uname["rohit.verma"]

        # A. Leave Applications
        # 1. Rahul: 1 PENDING Casual Leave -> Ready for Vikram to Approve or Reject
        session.add(
            LeaveApplication(
                employee_id=rahul.id,
                leave_type_id=ltype_map["CL"].id,
                leave_period_id=lp.id,
                from_date=date(2026, 12, 1),
                to_date=date(2026, 12, 2),
                half_day=False,
                days_count=2.0,
                reason="Attending family function in Jaipur",
                status="PENDING",
                applied_at=datetime(2026, 11, 20, 10, 0, tzinfo=IST),
            )
        )
        # Update pending balance
        cl_bal = await session.scalar(
            select(LeaveBalance).where(
                (LeaveBalance.employee_id == rahul.id) & (LeaveBalance.leave_type_id == ltype_map["CL"].id)
            )
        )
        if cl_bal:
            cl_bal.pending = Decimal("2.0")

        # 2. Rahul: 1 APPROVED Privilege Leave (with ledger entry and ERP outbox event)
        la_approved = LeaveApplication(
            employee_id=rahul.id,
            leave_type_id=ltype_map["EL"].id,
            leave_period_id=lp.id,
            from_date=date(2026, 10, 12),
            to_date=date(2026, 10, 14),
            half_day=False,
            days_count=3.0,
            reason="Personal vacation travel",
            status="APPROVED",
            applied_at=datetime(2026, 10, 1, 11, 0, tzinfo=IST),
            actioned_by=vikram.user_id,
            actioned_at=datetime(2026, 10, 2, 15, 30, tzinfo=IST),
            erp_sync_status="SYNCED",
        )
        session.add(la_approved)
        await session.flush()

        el_bal = await session.scalar(
            select(LeaveBalance).where(
                (LeaveBalance.employee_id == rahul.id) & (LeaveBalance.leave_type_id == ltype_map["EL"].id)
            )
        )
        if el_bal:
            el_bal.used = Decimal("3.0")

        ledger_trans_id += 1
        session.add(
            LeaveLedgerEntry(
                employee_id=rahul.id,
                leave_type_id=ltype_map["EL"].id,
                transaction_type="APPLICATION",
                transaction_id=ledger_trans_id,
                leaves=-3.0,
                from_date=date(2026, 10, 12),
                to_date=date(2026, 10, 14),
            )
        )
        session.add(
            ErpOutboxEvent(
                event_id=f"LEAVE-{la_approved.id}-APPROVED",
                entity_type="LEAVE",
                entity_id=la_approved.id,
                event_type="LEAVE_APPROVED",
                payload={"application_id": la_approved.id, "employee_code": rahul.employee_code, "status": "APPROVED"},
                acknowledged_at=datetime(2026, 10, 2, 16, 0, tzinfo=IST),
                acknowledged_by="ERP_CONNECTOR",
            )
        )

        # 3. Neha: 1 PENDING Sick Leave -> Second pending item for Vikram
        session.add(
            LeaveApplication(
                employee_id=neha.id,
                leave_type_id=ltype_map["SL"].id,
                leave_period_id=lp.id,
                from_date=date(2026, 12, 4),
                to_date=date(2026, 12, 4),
                half_day=False,
                days_count=1.0,
                reason="Dental checkup and root canal consultation",
                status="PENDING",
                applied_at=datetime(2026, 11, 21, 9, 30, tzinfo=IST),
            )
        )

        # 4. Priya (Bengaluru): 1 PENDING Leave -> Visible to Rohit, HIDDEN from Vikram (Department scope check)
        session.add(
            LeaveApplication(
                employee_id=priya_v.id,
                leave_type_id=ltype_map["CL"].id,
                leave_period_id=lp.id,
                from_date=date(2026, 12, 10),
                to_date=date(2026, 12, 11),
                half_day=False,
                days_count=2.0,
                reason="Attending developer summit",
                status="PENDING",
                applied_at=datetime(2026, 11, 22, 11, 0, tzinfo=IST),
            )
        )

        # B. Attendance Records & Biometric Punches (Past 3 days for Rahul)
        att_dates = [date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)]

        # Day 1: Present with In/Out punches
        rec_day1 = AttendanceRecord(
            employee_id=rahul.id,
            attendance_date=att_dates[0],
            shift_id=shift_map["GEN"].id,
            status="PRESENT",
            punch_in=time(9, 25),
            punch_out=time(18, 35),
            worked_minutes=550,
            late_minutes=0,
            early_exit_minutes=0,
            source="BIOMETRIC",
        )
        session.add(rec_day1)
        await session.flush()
        session.add(
            AttendancePunch(
                employee_id=rahul.id,
                punch_time=datetime(2026, 11, 18, 9, 25, tzinfo=IST),
                punch_type="IN",
                source="BIOMETRIC",
                device_id="BIO-HYD-GATE1",
                attendance_record_id=rec_day1.id,
                is_processed=True,
            )
        )
        session.add(
            AttendancePunch(
                employee_id=rahul.id,
                punch_time=datetime(2026, 11, 18, 18, 35, tzinfo=IST),
                punch_type="OUT",
                source="BIOMETRIC",
                device_id="BIO-HYD-GATE2",
                attendance_record_id=rec_day1.id,
                is_processed=True,
            )
        )

        # Day 2: WFH
        rec_day2 = AttendanceRecord(
            employee_id=rahul.id,
            attendance_date=att_dates[1],
            shift_id=shift_map["GEN"].id,
            status="WORK_FROM_HOME",
            punch_in=time(9, 30),
            punch_out=time(18, 30),
            worked_minutes=480,
            source="HRMS",
        )
        session.add(rec_day2)

        # Day 3: Missed punch discrepancy + PENDING AttendanceCorrectionRequest
        rec_day3 = AttendanceRecord(
            employee_id=rahul.id,
            attendance_date=att_dates[2],
            shift_id=shift_map["GEN"].id,
            status="HALF_DAY",
            punch_in=time(9, 28),
            punch_out=None,
            worked_minutes=240,
            source="BIOMETRIC",
        )
        session.add(rec_day3)
        await session.flush()

        session.add(
            AttendanceDiscrepancy(
                attendance_record_id=rec_day3.id,
                discrepancy_type="MISSED_OUT_PUNCH",
                status="OPEN",
            )
        )
        session.add(
            AttendanceCorrectionRequest(
                attendance_record_id=rec_day3.id,
                requested_punch_in=time(9, 28),
                requested_punch_out=time(18, 35),
                reason="Biometric reader at Gate 2 was unresponsive when exiting yesterday",
                status="PENDING",
                requested_at=datetime(2026, 11, 21, 9, 0, tzinfo=IST),
            )
        )

        # C. Work Arrangement Request (WFH)
        session.add(
            WorkArrangementRequest(
                employee_id=rahul.id,
                arrangement_type="WORK_FROM_HOME",
                from_date=date(2026, 12, 3),
                to_date=date(2026, 12, 3),
                reason="Broadband fiber optic maintenance technician visit at home",
                destination_location="Residence - Hyderabad",
                contact_phone=rahul.phone_number,
                status="PENDING",
            )
        )

        # D. Overtime Claim (PENDING for Vikram to approve)
        session.add(
            OvertimeRecord(
                employee_id=rahul.id,
                attendance_record_id=rec_day1.id,
                calculated_minutes=60,
                approved_minutes=0,
                status="PENDING",
                source="HRMS",
            )
        )

        # E. In-App Notifications
        notif_mgr = Notification(
            title="Action Required: Pending Approvals",
            message="Rahul Sharma has submitted a Casual Leave request (2 days) and an Attendance Regularization request.",
            notification_type="APPROVAL",
            user_id=vikram.user_id,
            is_read=False,
        )
        session.add(notif_mgr)
        await session.flush()
        if vikram.user_id:
            session.add(NotificationReceipt(notification_id=notif_mgr.notification_id, user_id=vikram.user_id))

        notif_emp = Notification(
            title="Leave Request Approved",
            message="Your Privilege Leave application for Oct 12-14 was approved by Vikram Malhotra.",
            notification_type="LEAVE",
            user_id=rahul.user_id,
            is_read=False,
        )
        session.add(notif_emp)
        await session.flush()
        if rahul.user_id:
            session.add(NotificationReceipt(notification_id=notif_emp.notification_id, user_id=rahul.user_id))

        notif_broadcast = Notification(
            title="Organization Notice: Holiday Calendar 2026",
            message="The list of 2026 gazetted holidays has been published on the employee portal.",
            notification_type="ANNOUNCEMENT",
            user_id=None,
            is_read=False,
        )
        session.add(notif_broadcast)
        await session.flush()
        for u in [rahul.user_id, vikram.user_id, rohit.user_id]:
            if u:
                session.add(NotificationReceipt(notification_id=notif_broadcast.notification_id, user_id=u))

        # F. Baseline Security Audit Log
        session.add(
            AuditLog(
                actor_user_id=superadmin.id,
                action="INITIALIZE_SEED_DATA",
                entity_type="System",
                entity_id="1",
                request_id="REQ-BOOTSTRAP",
                ip_address="127.0.0.1",
            )
        )

        await session.commit()

    summary = {
        "organizations": 1,
        "units": len(units_spec),
        "departments": len(dept_specs),
        "designations": len(desig_specs),
        "employees": len(created_employees),
        "leave_types": len(ltype_specs),
        "users": len(created_employees) + 1,  # + Super Admin
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed streamlined role-based data for People HRMS.")
    parser.add_argument("--clean", action="store_true", help="Truncate application tables before seeding.")
    args = parser.parse_args()

    print("Starting lean role-based seeding...")
    res = asyncio.run(seed_indian_data(clean=args.clean))

    print("\n--- Seeding Completed Successfully! ---")
    for entity, count in res.items():
        print(f"  • {entity.replace('_', ' ').title()}: {count}")
    print(f"\nWorkforce password: {DEV_PASSWORD} (Login at http://localhost:3000/login)")
    print("Super Admin password: from .env (Login at http://localhost:3000/admin/login)")


if __name__ == "__main__":
    main()
