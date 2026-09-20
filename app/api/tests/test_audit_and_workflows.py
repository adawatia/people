import asyncio
import selectors
import sys
import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from core.database import async_session_maker
from db.models import (
    AttendanceCorrectionRequest,
    AttendanceRecord,
    Department,
    Designation,
    Employee,
    LeaveApplication,
    Organization,
    OvertimeRecord,
    Unit,
    User,
    WorkArrangementRequest,
)
from schemas.attendance import AttendanceCorrectionCreate
from schemas.leaves import (
    LeaveAllocationCreate,
    LeaveApplicationCreate,
    LeavePeriodCreate,
    LeaveTypeCreate,
)
from schemas.org import DepartmentCreate, UnitCreate
from schemas.overtime import OvertimeApprovalCreate, OvertimeRejectionCreate
from schemas.work_arrangements import WorkArrangementCreate
from services.attendance_service import AttendanceService
from services.leave_service import LeaveService
from services.org_service import OrgService
from services.overtime_service import OvertimeService
from services.work_arrangement_service import WorkArrangementService


def run_async(coro):
    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:6]


async def _setup_audit_env(session, suffix: str):
    org = Organization(name=f"Audit Org {suffix}", short_name=f"AO_{suffix}")
    session.add(org)
    await session.flush()

    unit = Unit(organization_id=org.id, name=f"Audit Unit {suffix}", code=f"AU_{suffix}")
    session.add(unit)
    await session.flush()

    dept = Department(unit_id=unit.id, name=f"Audit Dept {suffix}", code=f"AD_{suffix}")
    session.add(dept)
    await session.flush()

    desig = Designation(name=f"Audit Desig {suffix}", code=f"ADes_{suffix}")
    session.add(desig)
    await session.flush()

    # User 1: Employee with self-service user link
    emp_user = User(
        username=f"emp_{suffix}",
        email=f"emp_{suffix}@example.com",
        hashed_password="fake",
        first_name="Employee",
        last_name="User",
    )
    session.add(emp_user)
    await session.flush()

    emp = Employee(
        first_name="Audit",
        last_name="Employee",
        employee_code=f"EMP_AUD_{suffix}",
        official_email=f"emp_{suffix}@example.com",
        unit_id=unit.id,
        department_id=dept.id,
        designation_id=desig.id,
        user_id=emp_user.id,
        employment_type="FULL_TIME",
        status="ACTIVE",
    )
    session.add(emp)

    # User 2: Independent Manager
    mgr_user = User(
        username=f"mgr_{suffix}",
        email=f"mgr_{suffix}@example.com",
        hashed_password="fake",
        first_name="Manager",
        last_name="User",
    )
    session.add(mgr_user)
    await session.flush()

    return org, unit, dept, emp, emp_user, mgr_user


# ── 1. Leave Self-Approval Prevention ─────────────────────────────────────────

def test_leave_self_approval_prevention(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, emp_user, mgr_user = await _setup_audit_env(session, unique_suffix)
            leave_service = LeaveService(session)

            period = await leave_service.create_period(
                LeavePeriodCreate(
                    name=f"FY26_{unique_suffix}",
                    from_date=date(2026, 1, 1),
                    to_date=date(2026, 12, 31),
                )
            )
            ltype = await leave_service.create_type(
                LeaveTypeCreate(
                    name=f"Casual Leave {unique_suffix}",
                    code=f"CL_{unique_suffix}",
                    is_paid=True,
                    is_encashable=False,
                )
            )
            await leave_service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=10.0,
                )
            )

            app = await leave_service.apply_leave(
                LeaveApplicationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    from_date=date(2026, 4, 10),
                    to_date=date(2026, 4, 11),
                    reason="Personal work",
                )
            )

            # Attempt self-approval by the employee
            with pytest.raises(HTTPException) as exc_info:
                await leave_service.approve_leave(app.id, actioned_by_user_id=emp_user.id)
            assert exc_info.value.status_code == 400
            assert "cannot approve their own leave" in exc_info.value.detail

            # Approval by independent manager succeeds
            approved = await leave_service.approve_leave(app.id, actioned_by_user_id=mgr_user.id)
            assert approved.status == "APPROVED"

    run_async(_test())


# ── 2. Leave Cancellation Cleans Attendance Records ──────────────────────────

def test_leave_cancellation_cleans_attendance_records(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, _, mgr_user = await _setup_audit_env(session, unique_suffix)
            leave_service = LeaveService(session)

            period = await leave_service.create_period(
                LeavePeriodCreate(
                    name=f"FY26_B_{unique_suffix}",
                    from_date=date(2026, 1, 1),
                    to_date=date(2026, 12, 31),
                )
            )
            ltype = await leave_service.create_type(
                LeaveTypeCreate(
                    name=f"Sick Leave {unique_suffix}",
                    code=f"SL_{unique_suffix}",
                    is_paid=True,
                )
            )
            await leave_service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=5.0,
                )
            )

            app = await leave_service.apply_leave(
                LeaveApplicationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    from_date=date(2026, 5, 4),
                    to_date=date(2026, 5, 5),
                    reason="Medical rest",
                )
            )
            await leave_service.approve_leave(app.id, actioned_by_user_id=mgr_user.id)

            # Verify ON_LEAVE records exist
            records = (await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == emp.id,
                    AttendanceRecord.status == "ON_LEAVE",
                )
            )).scalars().all()
            assert len(records) >= 2

            # Cancel the approved leave
            await leave_service.cancel_leave(app.id, cancelled_by_user_id=emp.user_id)

            # Verify ON_LEAVE records were cleaned up
            post_records = (await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == emp.id,
                    AttendanceRecord.status == "ON_LEAVE",
                    AttendanceRecord.attendance_date.in_([date(2026, 5, 4), date(2026, 5, 5)]),
                )
            )).scalars().all()
            assert len(post_records) == 0

    run_async(_test())


# ── 3. Attendance Correction Self-Approval Prevention ─────────────────────────

def test_attendance_correction_self_approval_prevention(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, emp_user, mgr_user = await _setup_audit_env(session, unique_suffix)
            att_service = AttendanceService(session)

            rec = AttendanceRecord(
                employee_id=emp.id,
                attendance_date=date(2026, 6, 1),
                status="ABSENT",
            )
            session.add(rec)
            await session.flush()

            corr = await att_service.submit_correction(
                AttendanceCorrectionCreate(
                    attendance_record_id=rec.id,
                    requested_punch_in="09:00",
                    requested_punch_out="18:00",
                    reason="Device issue",
                )
            )

            # Attempt self-approval
            with pytest.raises(HTTPException) as exc_info:
                await att_service.approve_correction(corr.id, actioned_by_user_id=emp_user.id)
            assert exc_info.value.status_code == 400
            assert "cannot act on their own" in exc_info.value.detail

            # Attempt self-rejection
            with pytest.raises(HTTPException) as exc_info_rej:
                await att_service.reject_correction(corr.id, actioned_by_user_id=emp_user.id)
            assert exc_info_rej.value.status_code == 400

            # Independent manager can reject with reason
            res = await att_service.reject_correction(
                corr.id,
                actioned_by_user_id=mgr_user.id,
                rejection_reason="Unverified punch proof",
            )
            assert res.status == "REJECTED"
            assert res.rejection_reason == "Unverified punch proof"

    run_async(_test())


# ── 4. Overtime Self-Approval & Rejection ─────────────────────────────────────

def test_overtime_self_approval_and_rejection(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, emp_user, mgr_user = await _setup_audit_env(session, unique_suffix)
            ot_service = OvertimeService(session)

            att_rec = AttendanceRecord(
                employee_id=emp.id,
                attendance_date=date(2026, 7, 10),
                status="PRESENT",
            )
            session.add(att_rec)
            await session.flush()

            ot = OvertimeRecord(
                employee_id=emp.id,
                attendance_record_id=att_rec.id,
                calculated_minutes=120,
                status="PENDING",
            )
            session.add(ot)
            await session.flush()

            # Attempt self-approval
            with pytest.raises(HTTPException) as exc_info:
                await ot_service.approve_overtime(
                    ot.id,
                    OvertimeApprovalCreate(approved_minutes=120, remarks="Ok"),
                    actioned_by_user_id=emp_user.id,
                )
            assert exc_info.value.status_code == 400
            assert "cannot approve their own" in exc_info.value.detail

            # Independent manager rejects
            rejected = await ot_service.reject_overtime(
                ot.id,
                OvertimeRejectionCreate(remarks="No prior pre-approval"),
                actioned_by_user_id=mgr_user.id,
            )
            assert rejected.status == "REJECTED"
            assert rejected.rejection_reason == "No prior pre-approval"
            assert rejected.actioned_by == mgr_user.id

    run_async(_test())


# ── 5. Overtime Monthly Summary Filtering ─────────────────────────────────────

def test_overtime_monthly_summary_filtering(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, _, _ = await _setup_audit_env(session, unique_suffix)
            ot_service = OvertimeService(session)

            att_july = AttendanceRecord(
                employee_id=emp.id,
                attendance_date=date(2026, 7, 15),
                status="PRESENT",
            )
            att_aug = AttendanceRecord(
                employee_id=emp.id,
                attendance_date=date(2026, 8, 20),
                status="PRESENT",
            )
            session.add_all([att_july, att_aug])
            await session.flush()

            # July 2026 record
            ot_july = OvertimeRecord(
                employee_id=emp.id,
                attendance_record_id=att_july.id,
                calculated_minutes=90,
                approved_minutes=90,
                status="APPROVED",
            )
            # August 2026 record
            ot_aug = OvertimeRecord(
                employee_id=emp.id,
                attendance_record_id=att_aug.id,
                calculated_minutes=150,
                approved_minutes=150,
                status="APPROVED",
            )
            session.add_all([ot_july, ot_aug])
            await session.flush()

            # Query only July 2026
            summary_july = await ot_service.get_overtime_summary(
                employee_id=emp.id,
                month=7,
                year=2026,
            )
            assert summary_july.total_calculated_minutes == 90
            assert summary_july.total_approved_minutes == 90

            # Query August 2026
            summary_aug = await ot_service.get_overtime_summary(
                employee_id=emp.id,
                month=8,
                year=2026,
            )
            assert summary_aug.total_calculated_minutes == 150
            assert summary_aug.total_approved_minutes == 150

    run_async(_test())


# ── 6. Work Arrangement Self-Approval & Attendance Reversion ─────────────────

def test_work_arrangement_workflow_and_attendance(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, emp_user, mgr_user = await _setup_audit_env(session, unique_suffix)
            wa_service = WorkArrangementService(session)

            req = await wa_service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=date(2026, 9, 1),
                    to_date=date(2026, 9, 2),
                    reason="Client call from home",
                )
            )

            # Self-approval prevented
            with pytest.raises(HTTPException) as exc_info:
                await wa_service.approve_request(req.id, actioned_by_user_id=emp_user.id)
            assert exc_info.value.status_code == 400

            # Manager approves
            approved = await wa_service.approve_request(req.id, actioned_by_user_id=mgr_user.id)
            assert approved.status == "APPROVED"

            # Attendance records created
            recs = (await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == emp.id,
                    AttendanceRecord.attendance_date.in_([date(2026, 9, 1), date(2026, 9, 2)]),
                )
            )).scalars().all()
            assert len(recs) == 2
            assert all(r.status == "WORK_FROM_HOME" for r in recs)

            # Cancel cleans attendance records
            await wa_service.cancel_request(req.id, cancelled_by_user_id=emp_user.id)
            recs_after = (await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.employee_id == emp.id,
                    AttendanceRecord.attendance_date.in_([date(2026, 9, 1), date(2026, 9, 2)]),
                )
            )).scalars().all()
            assert len(recs_after) == 0

    run_async(_test())


# ── 7. WFH Recognition in Batch Attendance Processor ─────────────────────────

def test_wfh_awareness_in_attendance_processor(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            _, _, _, emp, _, mgr_user = await _setup_audit_env(session, unique_suffix)
            wa_service = WorkArrangementService(session)
            att_service = AttendanceService(session)

            target_date = date(2026, 9, 15)

            # Pre-approve a WFH request for target_date
            req = await wa_service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=target_date,
                    to_date=target_date,
                    reason="Remote sprint",
                )
            )
            # Remove any records created by approve_request so we can test the daily processor directly
            await wa_service.approve_request(req.id, actioned_by_user_id=mgr_user.id)
            existing_rec = await att_service.record_repo.get_by_employee_and_date(emp.id, target_date)
            if existing_rec:
                await att_service.record_repo.delete(existing_rec)
                await session.commit()

            # Now run attendance processing for that date without biometric punches
            rec, created = await att_service.process_attendance_for_employee_date(emp, target_date)
            await session.commit()

            # Assert marked WORK_FROM_HOME instead of ABSENT
            assert rec.status == "WORK_FROM_HOME"

    run_async(_test())


# ── 8. OrgService CRUD and Validation ────────────────────────────────────────

def test_org_service_crud_and_validation(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            org, _, _, _, _, _ = await _setup_audit_env(session, unique_suffix)
            org_service = OrgService(session)

            # List orgs
            orgs = await org_service.list_organizations()
            assert any(o.id == org.id for o in orgs)

            # Create Unit
            unit = await org_service.create_unit(
                UnitCreate(
                    organization_id=org.id,
                    name=f"New Unit {unique_suffix}",
                    code=f"NU_{unique_suffix}",
                )
            )
            assert unit.id is not None

            # Create Department under new unit
            dept = await org_service.create_department(
                DepartmentCreate(
                    unit_id=unit.id,
                    name=f"Engineering {unique_suffix}",
                    code=f"ENG_{unique_suffix}",
                )
            )
            assert dept.id is not None
            assert dept.unit_id == unit.id

            # Validation: cannot create department under nonexistent unit
            with pytest.raises(HTTPException) as exc_info:
                await org_service.create_department(
                    DepartmentCreate(
                        unit_id=999999,
                        name=f"Invalid {unique_suffix}",
                        code=f"INV_{unique_suffix}",
                    )
                )
            assert exc_info.value.status_code == 404

    run_async(_test())


# ── 9. Completed Detail / Single-Resource Retrieval Endpoints ────────────────

def test_completed_detail_endpoints(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            org, unit, dept, emp, emp_user, _ = await _setup_audit_env(session, unique_suffix)
            org_service = OrgService(session)
            leave_service = LeaveService(session)
            wa_service = WorkArrangementService(session)
            ot_service = OvertimeService(session)
            att_service = AttendanceService(session)

            # 1. Org & Dept Get
            u = await org_service.get_unit(unit.id)
            assert u.id == unit.id
            d = await org_service.get_department(dept.id)
            assert d.id == dept.id

            # 2. Leave Application Get
            period = await leave_service.create_period(
                LeavePeriodCreate(
                    name=f"FY26_C_{unique_suffix}",
                    from_date=date(2026, 1, 1),
                    to_date=date(2026, 12, 31),
                )
            )
            ltype = await leave_service.create_type(
                LeaveTypeCreate(
                    name=f"Earned Leave {unique_suffix}",
                    code=f"EL_{unique_suffix}",
                    is_paid=True,
                )
            )
            await leave_service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=15.0,
                )
            )
            app = await leave_service.apply_leave(
                LeaveApplicationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    from_date=date(2026, 10, 1),
                    to_date=date(2026, 10, 2),
                    reason="Vacation",
                )
            )
            fetched_app = await leave_service.get_application(app.id)
            assert fetched_app.id == app.id
            assert fetched_app.employee_name == f"{emp.first_name} {emp.last_name}"

            # 3. Work Arrangement Get
            req = await wa_service.create_request(
                WorkArrangementCreate(
                    employee_id=emp.id,
                    arrangement_type="WORK_FROM_HOME",
                    from_date=date(2026, 10, 15),
                    to_date=date(2026, 10, 16),
                    reason="Remote",
                )
            )
            fetched_req = await wa_service.get_request(req.id)
            assert fetched_req.id == req.id

            # 4. Attendance Record Get
            att_rec = AttendanceRecord(
                employee_id=emp.id,
                attendance_date=date(2026, 10, 20),
                status="PRESENT",
            )
            session.add(att_rec)
            await session.flush()
            fetched_att = await att_service.get_attendance_record(att_rec.id)
            assert fetched_att.id == att_rec.id

            # 5. Overtime Record Get
            ot_rec = OvertimeRecord(
                employee_id=emp.id,
                attendance_record_id=att_rec.id,
                calculated_minutes=60,
                status="PENDING",
            )
            session.add(ot_rec)
            await session.flush()
            fetched_ot = await ot_service.get_overtime(ot_rec.id)
            assert fetched_ot.id == ot_rec.id

            # 6. Shift Assignment Get
            from schemas.shifts import ShiftAssignmentCreate, ShiftCreate
            from services.shift_service import ShiftService
            shift_svc = ShiftService(session)
            shift = await shift_svc.create_shift(
                ShiftCreate(
                    name=f"Morning {unique_suffix}",
                    code=f"MS_{unique_suffix}",
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                )
            )
            assign = await shift_svc.assign_shift(
                ShiftAssignmentCreate(
                    employee_id=emp.id,
                    shift_id=shift.id,
                    effective_from=date(2026, 11, 1),
                )
            )
            fetched_assign = await shift_svc.get_assignment(assign.id)
            assert fetched_assign.id == assign.id
            assert fetched_assign.shift_name == shift.name

    run_async(_test())


# ── 10. Notification Read Authorization & Manager Dashboard Metrics ──────────

def test_notification_and_manager_dashboard_workflow(unique_suffix):
    async def _test():
        async with async_session_maker() as session:
            org, unit, dept, emp, emp_user, mgr_user = await _setup_audit_env(session, unique_suffix)
            from db.models import Notification, Role, UserRoleAssignment
            from routers.dashboard import get_dashboard_metrics
            from routers.notifications import mark_notification_read
            from schemas.leaves import LeaveAllocationCreate, LeaveApplicationCreate, LeavePeriodCreate, LeaveTypeCreate
            from services.leave_service import LeaveService

            # 1. Notification owner authorization check
            notif = Notification(
                title="Private Alert",
                message="Only for employee",
                notification_type="alert",
                user_id=emp_user.id,
                is_read=False,
            )
            session.add(notif)
            await session.commit()
            await session.refresh(notif)

            # Manager trying to mark employee's private notification as read -> 403 Forbidden
            with pytest.raises(HTTPException) as exc_info:
                await mark_notification_read(id=notif.notification_id, current_user=mgr_user, session=session)
            assert exc_info.value.status_code == 403

            # Employee marking their own notification -> 200 OK
            marked = await mark_notification_read(id=notif.notification_id, current_user=emp_user, session=session)
            assert marked.is_read is True

            # 2. Manager Dashboard Metrics & Scoped Pending Approvals
            # Give mgr_user the HR_MANAGER role scoped to this unit
            role_hr = Role(role_name=f"HR_MGR_{unique_suffix}", is_system_role=False)
            session.add(role_hr)
            await session.flush()
            from db.models import Permission, RolePermission
            perm_leave = await session.scalar(select(Permission).where(Permission.permission_code == "leave.approve"))
            if not perm_leave:
                perm_leave = Permission(permission_code="leave.approve", module_name="leaves")
                session.add(perm_leave)
                await session.flush()
            session.add(RolePermission(role_id=role_hr.role_id, permission_id=perm_leave.permission_id))
            session.add(UserRoleAssignment(
                user_id=mgr_user.id,
                role_id=role_hr.role_id,
                scope_type="unit",
                scope_id=unit.id,
            ))
            await session.commit()

            # Create pending leave application by employee
            leave_service = LeaveService(session)
            period = await leave_service.create_period(
                LeavePeriodCreate(
                    name=f"FY26_D_{unique_suffix}",
                    from_date=date(2026, 1, 1),
                    to_date=date(2026, 12, 31),
                )
            )
            ltype = await leave_service.create_type(
                LeaveTypeCreate(
                    name=f"Casual Leave {unique_suffix}",
                    code=f"CL_{unique_suffix}",
                    is_paid=True,
                )
            )
            await leave_service.allocate_leaves(
                LeaveAllocationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    leave_period_id=period.id,
                    new_leaves_allocated=10.0,
                )
            )
            app = await leave_service.apply_leave(
                LeaveApplicationCreate(
                    employee_id=emp.id,
                    leave_type_id=ltype.id,
                    from_date=date(2026, 11, 10),
                    to_date=date(2026, 11, 11),
                    reason="Doctor visit",
                )
            )

            # Call get_dashboard_metrics as manager
            metrics = await get_dashboard_metrics(user=mgr_user, session=session)
            assert metrics["unitMetrics"]["totalHeadcount"] >= 1
            assert metrics["unitMetrics"]["pendingLeaves"] >= 1
            assert len(metrics["pendingApprovals"]) >= 1
            found = any(p["id"] == f"leave_{app.id}" for p in metrics["pendingApprovals"])
            assert found is True

    run_async(_test())

