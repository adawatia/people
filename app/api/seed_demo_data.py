"""
seed_demo_data.py — Insert realistic demo data for HRMS testing.

Creates:
  1. Organizations, Units, Departments (org structure)
  2. Shifts (General, Morning, Evening, Night)
  3. Holidays
  4. Weekly-off rules
  5. Leave types & leave policies
  6. 25 demo employees with system users + scoped role assignments
  7. Sample attendance records (last 30 days)
  8. Sample leave applications
  9. Sample notifications

Run with:
    uv run python seed_demo_data.py

This script is idempotent — safe to run multiple times.
"""
import asyncio
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Adjust sys.path so we can import the app modules ─────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi_users.password import PasswordHelper

from core.settings import get_settings
from db.models import (
    AttendanceRecord as AttendanceRecordModel,
    Base,
    Department as DepartmentModel,
    Employee as EmployeeModel,
    Holiday as HolidayModel,
    LeaveApplication as LeaveApplicationModel,
    LeaveBalance as LeaveBalanceModel,
    LeaveType as LeaveTypeModel,
    Organization as OrganizationModel,
    Permission,
    Role,
    RolePermission,
    Shift as ShiftModel,
    Unit as UnitModel,
    User,
    UserRoleAssignment,
)

IST = ZoneInfo("Asia/Kolkata")
helper = PasswordHelper()

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────
async def run_sql(session: AsyncSession, sql: str, **params):
    await session.execute(text(sql), params)


async def upsert_row(session: AsyncSession, table: str, unique_col: str, unique_val, data: dict) -> int:
    """Insert or update a row and return its id."""
    result = await session.execute(text(f"SELECT id FROM {table} WHERE {unique_col} = :{unique_col}"), {unique_col: unique_val})
    row = result.fetchone()
    if row:
        return row[0]
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())
    result = await session.execute(
        text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING id"),
        data,
    )
    return result.fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# Main Seeder
# ─────────────────────────────────────────────────────────────────────────────
async def seed_demo():
    # NOTE: the canonical schema is owned by db.models metadata + Alembic.
    # Do NOT hand-create domain tables here — an out-of-date CREATE TABLE
    # (e.g. employees with a stale employee_code NOT NULL column) diverges
    # from the ORM and breaks inserts. Just ensure ORM tables exist.
    from db.models import Base as ModelsBase
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)

    async with async_session_maker() as session:
        # ── 1. Organization (ORM-first: matches real schema) ─────────────────
        print("→ Seeding organization...")
        r = await session.execute(
            select(OrganizationModel).where(OrganizationModel.name == "Bajaj Sons Industries")
        )
        org = r.scalar_one_or_none()
        if org is None:
            org = OrganizationModel(
                name="Bajaj Sons Industries", short_name="BSL", industry="Manufacturing"
            )
            session.add(org)
            await session.flush()
        org_id = org.id

        # ── 2. Units ──────────────────────────────────────────────────────────
        print("→ Seeding units...")
        unit_data = [
            ("Ludhiana Plant", "BSL-LDH", "Ludhiana"),
            ("Jalandhar Plant", "BSL-JLD", "Jalandhar"),
            ("Amritsar Plant", "BSL-AMR", "Amritsar"),
        ]
        unit_ids = {}
        for uname, ucode, ucity in unit_data:
            r = await session.execute(select(UnitModel).where(UnitModel.code == ucode))
            unit = r.scalar_one_or_none()
            if unit is None:
                unit = UnitModel(
                    organization_id=org_id, name=uname, code=ucode, city=ucity
                )
                session.add(unit)
                await session.flush()
            unit_ids[ucode] = unit.id

        # ── 3. Departments ────────────────────────────────────────────────────
        print("→ Seeding departments...")
        dept_data = [
            ("Production", "PROD"),
            ("Quality Control", "QC"),
            ("Maintenance", "MAINT"),
            ("Accounts", "ACCT"),
            ("HR & Admin", "HR"),
            ("Stores", "STORE"),
        ]
        dept_ids = {}  # (unit_code, dept_code) -> dept_id
        for ucode, uid in unit_ids.items():
            for dname, dcode in dept_data:
                full_code = f"{ucode}-{dcode}"
                r = await session.execute(
                    select(DepartmentModel).where(DepartmentModel.code == full_code)
                )
                dept = r.scalar_one_or_none()
                if dept is None:
                    dept = DepartmentModel(unit_id=uid, name=dname, code=full_code)
                    session.add(dept)
                    await session.flush()
                dept_ids[(ucode, dcode)] = dept.id

        # ── 4. Shifts ─────────────────────────────────────────────────────────
        print("→ Seeding shifts...")
        from datetime import time as dtime

        def _parse_hhmm(value: str) -> dtime:
            hh, mm = value.split(":")
            return dtime(int(hh), int(mm))

        shift_data = [
            ("General Shift", "09:00", "18:00", False),
            ("Morning Shift", "06:00", "14:00", False),
            ("Evening Shift", "14:00", "22:00", False),
            ("Night Shift", "22:00", "06:00", True),
        ]
        shift_ids = {}
        for uid in unit_ids.values():
            for sname, start, end, cross in shift_data:
                r = await session.execute(
                    select(ShiftModel).where(
                        ShiftModel.unit_id == uid, ShiftModel.name == sname
                    )
                )
                shift = r.scalar_one_or_none()
                if shift is None:
                    shift = ShiftModel(
                        unit_id=uid,
                        name=sname,
                        start_time=_parse_hhmm(start),
                        end_time=_parse_hhmm(end),
                        is_cross_midnight=cross,
                    )
                    session.add(shift)
                    await session.flush()
                shift_ids[(uid, sname)] = shift.id

        # ── 5. Holidays ───────────────────────────────────────────────────────
        print("→ Seeding holidays...")
        holidays = [
            ("Republic Day", date(2026, 1, 26)),
            ("Holi", date(2026, 3, 25)),
            ("Independence Day", date(2026, 8, 15)),
            ("Gandhi Jayanti", date(2026, 10, 2)),
            ("Diwali", date(2026, 11, 1)),
        ]
        for hname, hdate in holidays:
            r = await session.execute(
                select(HolidayModel).where(
                    HolidayModel.name == hname,
                    HolidayModel.holiday_date == hdate,
                )
            )
            if r.scalar_one_or_none() is None:
                session.add(
                    HolidayModel(
                        name=hname, holiday_date=hdate, is_organization_wide=True
                    )
                )
        await session.flush()

        # ── 6. Leave Types ────────────────────────────────────────────────────
        print("→ Seeding leave types...")
        leave_types = [
            ("Casual Leave", "CL", True, 12, 3, False),
            ("Sick Leave", "SL", True, 9, 7, False),
            ("Earned Leave", "EL", True, 15, 30, True),
            ("Maternity Leave", "ML", True, 180, 180, False),
            ("Paternity Leave", "PL", True, 15, 15, False),
            ("Compensatory Leave", "COMP", True, 0, 3, False),
        ]
        leave_type_ids = {}
        for lname, lcode, paid, alloc, max_days, carry in leave_types:
            r = await session.execute(
                select(LeaveTypeModel).where(LeaveTypeModel.code == lcode)
            )
            lt = r.scalar_one_or_none()
            if lt is None:
                lt = LeaveTypeModel(
                    name=lname,
                    code=lcode,
                    is_paid=paid,
                    annual_allocation=alloc,
                    max_consecutive_days=max_days,
                    carry_forward=carry,
                )
                session.add(lt)
                await session.flush()
            leave_type_ids[lcode] = lt.id

        # ── 7. Fetch roles ────────────────────────────────────────────────────
        print("→ Loading roles...")
        roles_result = await session.execute(select(Role))
        roles_map = {r.role_name: r.role_id for r in roles_result.scalars().all()}

        # ── 8. Demo employees + system users ──────────────────────────────────
        print("→ Seeding 25 demo employees...")

        DEMO_EMPLOYEES = [
            # (first, last, email, username, designation, unit_code, dept_code, role_name, salary)
            # Unit Ludhiana
            ("Arvind", "Kumar", "arvind.kumar@bsl.com", "arvind.kumar", "Production Manager", "BSL-LDH", "PROD", "UNIT_HEAD", 85000),
            ("Sunita", "Rao", "sunita.rao@bsl.com", "sunita.rao", "HR Manager", "BSL-LDH", "HR", "HR_MANAGER", 72000),
            ("Ramesh", "Patel", "ramesh.patel@bsl.com", "ramesh.patel", "Dept Head Production", "BSL-LDH", "PROD", "DEPARTMENT_HEAD", 68000),
            ("Vikram", "Singh", "vikram.singh@bsl.com", "vikram.singh", "Production Operator", "BSL-LDH", "PROD", "EMPLOYEE", 28000),
            ("Meena", "Sharma", "meena.sharma@bsl.com", "meena.sharma", "QC Inspector", "BSL-LDH", "QC", "EMPLOYEE", 32000),
            ("Deepak", "Verma", "deepak.verma@bsl.com", "deepak.verma", "Maintenance Technician", "BSL-LDH", "MAINT", "EMPLOYEE", 31000),
            ("Priya", "Gupta", "priya.gupta@bsl.com", "priya.gupta", "QC Head", "BSL-LDH", "QC", "DEPARTMENT_HEAD", 62000),
            ("Anil", "Nair", "anil.nair@bsl.com", "anil.nair", "Store Keeper", "BSL-LDH", "STORE", "EMPLOYEE", 27000),
            ("Kavita", "Joshi", "kavita.joshi@bsl.com", "kavita.joshi", "Accounts Officer", "BSL-LDH", "ACCT", "EMPLOYEE", 40000),
            ("Raj", "Yadav", "raj.yadav@bsl.com", "raj.yadav", "Maintenance Head", "BSL-LDH", "MAINT", "DEPARTMENT_HEAD", 60000),

            # Unit Jalandhar
            ("Gurpreet", "Singh", "gurpreet.singh@bsl.com", "gurpreet.singh", "Unit Head", "BSL-JLD", "PROD", "UNIT_HEAD", 88000),
            ("Harbhajan", "Kaur", "harbhajan.kaur@bsl.com", "harbhajan.kaur", "HR Coordinator", "BSL-JLD", "HR", "HR_MANAGER", 60000),
            ("Mandeep", "Grewal", "mandeep.grewal@bsl.com", "mandeep.grewal", "Production Operator", "BSL-JLD", "PROD", "EMPLOYEE", 26000),
            ("Simran", "Bains", "simran.bains@bsl.com", "simran.bains", "QC Analyst", "BSL-JLD", "QC", "EMPLOYEE", 33000),
            ("Jaswant", "Dhillon", "jaswant.dhillon@bsl.com", "jaswant.dhillon", "Dept Head Production", "BSL-JLD", "PROD", "DEPARTMENT_HEAD", 65000),
            ("Parminder", "Sandhu", "parminder.sandhu@bsl.com", "parminder.sandhu", "Maintenance Lead", "BSL-JLD", "MAINT", "EMPLOYEE", 35000),
            ("Balvinder", "Sohal", "balvinder.sohal@bsl.com", "balvinder.sohal", "Store Manager", "BSL-JLD", "STORE", "DEPARTMENT_HEAD", 55000),
            ("Navneet", "Gill", "navneet.gill@bsl.com", "navneet.gill", "Production Operator", "BSL-JLD", "PROD", "EMPLOYEE", 26000),

            # Unit Amritsar
            ("Rohit", "Mehta", "rohit.mehta@bsl.com", "rohit.mehta", "Unit Head", "BSL-AMR", "PROD", "UNIT_HEAD", 90000),
            ("Pooja", "Arora", "pooja.arora@bsl.com", "pooja.arora", "HR Lead", "BSL-AMR", "HR", "HR_MANAGER", 65000),
            ("Suresh", "Bhatt", "suresh.bhatt@bsl.com", "suresh.bhatt", "Production Operator", "BSL-AMR", "PROD", "EMPLOYEE", 27000),
            ("Anita", "Chawla", "anita.chawla@bsl.com", "anita.chawla", "QC Supervisor", "BSL-AMR", "QC", "DEPARTMENT_HEAD", 58000),
            ("Devraj", "Malhotra", "devraj.malhotra@bsl.com", "devraj.malhotra", "Maintenance Technician", "BSL-AMR", "MAINT", "EMPLOYEE", 30000),
            ("Shalini", "Khanna", "shalini.khanna@bsl.com", "shalini.khanna", "Accounts Executive", "BSL-AMR", "ACCT", "EMPLOYEE", 38000),
            ("Tejinder", "Walia", "tejinder.walia@bsl.com", "tejinder.walia", "Production Lead", "BSL-AMR", "PROD", "DEPARTMENT_HEAD", 62000),
        ]

        demo_password = "DemoHRMS@2026"
        hashed_pw = helper.hash(demo_password)

        emp_ids = []
        for i, (first, last, email, username, desig, ucode, dcode, role_name, salary) in enumerate(DEMO_EMPLOYEES):
            # Create system user
            r = await session.execute(select(User).where(User.email == email))
            user = r.scalar_one_or_none()
            if not user:
                user = User(
                    email=email,
                    username=username,
                    first_name=first,
                    last_name=last,
                    hashed_password=hashed_pw,
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                    invitation_used_at=datetime.now(IST),
                )
                session.add(user)
                await session.flush()

            # Scoped UserRoleAssignment
            role_id = roles_map.get(role_name)
            uid_val = unit_ids[ucode]
            dept_id = dept_ids.get((ucode, dcode))
            if role_id:
                scope_type = "unit" if "UNIT_HEAD" in role_name or "HR_MANAGER" in role_name else (
                    "department" if "DEPARTMENT_HEAD" in role_name else "organization"
                )
                scope_id = uid_val if scope_type == "unit" else (dept_id if scope_type == "department" else None)
                r = await session.execute(
                    select(UserRoleAssignment).where(
                        UserRoleAssignment.user_id == user.id,
                        UserRoleAssignment.role_id == role_id,
                    )
                )
                if not r.scalar_one_or_none():
                    session.add(UserRoleAssignment(
                        user_id=user.id, role_id=role_id,
                        scope_type=scope_type, scope_id=scope_id,
                    ))

            # Employee record — aligned to the ORM Employee model.
            r = await session.execute(
                select(EmployeeModel).where(EmployeeModel.official_email == email)
            )
            emp_row = r.scalar_one_or_none()
            if emp_row is None:
                shift_name = random.choice(["General Shift", "Morning Shift"])
                shift_id = shift_ids.get((uid_val, shift_name))
                doj = date(2022, random.randint(1, 12), random.randint(1, 28))
                emp_obj = EmployeeModel(
                    user_id=user.id,
                    employee_code=f"EMP-{1000 + i:04d}",
                    first_name=first,
                    last_name=last,
                    official_email=email,
                    department_id=dept_id,
                    unit_id=uid_val,
                    designation=desig,
                    date_of_joining=doj,
                    employment_type="PERMANENT",
                    status="ACTIVE",
                    biometric_id=f"BIO-EMP-{1000 + i:04d}",
                    monthly_salary=salary,
                    overtime_eligible=True,
                    shift_id=shift_id,
                )
                session.add(emp_obj)
                await session.flush()
                emp_id = emp_obj.id
            else:
                emp_id = emp_row.id
            emp_ids.append(emp_id)

            # Leave balances (current year) — ORM model.
            year = date.today().year
            for lcode, lt_id in leave_type_ids.items():
                r = await session.execute(
                    select(LeaveBalanceModel).where(
                        LeaveBalanceModel.employee_id == emp_id,
                        LeaveBalanceModel.leave_type_id == lt_id,
                        LeaveBalanceModel.year == year,
                    )
                )
                if r.scalar_one_or_none() is None:
                    lt_r = await session.execute(
                        select(LeaveTypeModel).where(LeaveTypeModel.id == lt_id)
                    )
                    alloc = lt_r.scalar_one().annual_allocation or 0
                    used = random.randint(0, min(alloc, 4)) if alloc > 0 else 0
                    session.add(
                        LeaveBalanceModel(
                            employee_id=emp_id,
                            leave_type_id=lt_id,
                            year=year,
                            allocated=alloc,
                            used=used,
                        )
                    )

        await session.flush()

        # ── 9. Attendance records (last 30 days) ──────────────────────────────
        print("→ Seeding attendance records (last 30 days)...")
        today = date.today()
        statuses = ["PRESENT", "PRESENT", "PRESENT", "PRESENT", "PRESENT", "PRESENT",
                    "ABSENT", "ON_LEAVE", "LATE", "MISSED_PUNCH"]
        for emp_id in emp_ids[:15]:  # First 15 employees for speed
            for day_offset in range(30):
                adate = today - timedelta(days=day_offset)
                if adate.weekday() >= 6:  # Sunday off
                    st = "WEEKLY_OFF"
                    punch_in = punch_out = None
                    worked = 0
                else:
                    st = random.choice(statuses)
                    if st == "PRESENT":
                        punch_in = time(8, random.randint(45, 65) % 60, 0)
                        punch_out = time(18, random.randint(0, 30), 0)
                        worked = 540 + random.randint(-30, 30)
                    elif st == "LATE":
                        punch_in = time(9, random.randint(15, 45), 0)
                        punch_out = time(18, 0, 0)
                        worked = 510
                    elif st == "MISSED_PUNCH":
                        punch_in = time(9, 0, 0)
                        punch_out = None
                        worked = 0
                    else:
                        punch_in = punch_out = None
                        worked = 0

                r = await session.execute(
                    select(AttendanceRecordModel).where(
                        AttendanceRecordModel.employee_id == emp_id,
                        AttendanceRecordModel.attendance_date == adate,
                    )
                )
                if r.scalar_one_or_none() is None:
                    ot = max(0, worked - 540) if worked > 540 else 0
                    session.add(
                        AttendanceRecordModel(
                            employee_id=emp_id,
                            attendance_date=adate,
                            status=st,
                            punch_in=punch_in,
                            punch_out=punch_out,
                            worked_minutes=worked,
                            overtime_minutes=ot,
                        )
                    )
        await session.flush()

        # ── 10. Sample leave applications ─────────────────────────────────────
        print("→ Seeding sample leave applications...")
        leave_samples = [
            (emp_ids[3], "CL", date.today() + timedelta(days=5), date.today() + timedelta(days=6), "Personal work", "PENDING"),
            (emp_ids[4], "SL", date.today() - timedelta(days=10), date.today() - timedelta(days=10), "Sick - fever", "APPROVED"),
            (emp_ids[5], "EL", date.today() + timedelta(days=15), date.today() + timedelta(days=20), "Vacation", "PENDING"),
            (emp_ids[7], "CL", date.today() - timedelta(days=5), date.today() - timedelta(days=5), "Family function", "REJECTED"),
            (emp_ids[8], "SL", date.today() - timedelta(days=3), date.today() - timedelta(days=2), "Doctor visit", "APPROVED"),
        ]
        for emp_id, lcode, fdate, tdate, reason, status in leave_samples:
            lt_id = leave_type_ids[lcode]
            days = (tdate - fdate).days + 1
            r = await session.execute(
                select(LeaveApplicationModel).where(
                    LeaveApplicationModel.employee_id == emp_id,
                    LeaveApplicationModel.from_date == fdate,
                )
            )
            if r.scalar_one_or_none() is None:
                session.add(
                    LeaveApplicationModel(
                        employee_id=emp_id,
                        leave_type_id=lt_id,
                        from_date=fdate,
                        to_date=tdate,
                        days_count=days,
                        reason=reason,
                        status=status,
                    )
                )

        await session.commit()
        print()
        print("✅ Demo data seeded successfully!")
        print()
        print("─── Demo Users ───────────────────────────────────────────────")
        print(f"  Password for ALL demo users: {demo_password}")
        print()
        print("  Super Admin:    admin@hrms.com             / SuperAdmin@123")
        print()
        print("  Unit Head:      arvind.kumar@bsl.com       (Ludhiana Plant)")
        print("  HR Manager:     sunita.rao@bsl.com         (Ludhiana Plant)")
        print("  Dept Head:      ramesh.patel@bsl.com       (Production, Ludhiana)")
        print("  Employee:       vikram.singh@bsl.com       (Production, Ludhiana)")
        print()
        print("  Unit Head:      gurpreet.singh@bsl.com     (Jalandhar Plant)")
        print("  HR Manager:     harbhajan.kaur@bsl.com     (Jalandhar Plant)")
        print()
        print("  Unit Head:      rohit.mehta@bsl.com        (Amritsar Plant)")
        print("  HR Manager:     pooja.arora@bsl.com        (Amritsar Plant)")
        print("─────────────────────────────────────────────────────────────")
        print()
        print("  Org structure:  3 Units × 6 Departments = 18 departments")
        print("  Employees:      25 demo employees with system accounts")
        print("  Attendance:     30 days of attendance records (15 employees)")
        print("  Leave:          5 sample leave applications (PENDING/APPROVED/REJECTED)")
        print("  Leave types:    CL / SL / EL / ML / PL / COMP")
        print("  Shifts:         General / Morning / Evening / Night")
        print("  Holidays:       5 national holidays seeded")


if __name__ == "__main__":
    asyncio.run(seed_demo())
