from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.pagination import employee_search, ordered, paginate
from db.models import (
    Employee,
    LeaveAllocation,
    LeaveApplication,
    LeaveLedgerEntry,
    LeavePeriod,
    LeaveType,
)


class LeaveRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Leave Periods ──────────────────────────────────────────────────────────

    async def get_period_by_id(self, period_id: int) -> LeavePeriod | None:
        return await self.session.get(LeavePeriod, period_id)

    async def get_active_period_for_date(self, target_date: date) -> LeavePeriod | None:
        stmt = select(LeavePeriod).where(
            LeavePeriod.is_active == True,
            LeavePeriod.from_date <= target_date,
            LeavePeriod.to_date >= target_date,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_periods(self) -> list[LeavePeriod]:
        stmt = select(LeavePeriod).order_by(LeavePeriod.from_date.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_period(self, period: LeavePeriod) -> LeavePeriod:
        self.session.add(period)
        await self.session.flush()
        return period

    # ── Leave Types ────────────────────────────────────────────────────────────

    async def get_type_by_id(self, type_id: int) -> LeaveType | None:
        return await self.session.get(LeaveType, type_id)

    async def get_type_by_code(self, code: str) -> LeaveType | None:
        stmt = select(LeaveType).where(func.lower(LeaveType.code) == code.strip().lower())
        return (await self.session.execute(stmt)).scalars().first()

    async def list_types(self, is_active: bool | None = None) -> list[LeaveType]:
        stmt = select(LeaveType).order_by(LeaveType.name)
        if is_active is not None:
            stmt = stmt.where(LeaveType.is_active == is_active)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_balances(self, employee_id: int, year: int) -> list:
        from db.models import LeaveBalance
        stmt = (
            select(LeaveBalance)
            .options(selectinload(LeaveBalance.leave_type))
            .where(LeaveBalance.employee_id == employee_id, LeaveBalance.year == year)
            .order_by(LeaveBalance.leave_type_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_type(self, leave_type: LeaveType) -> LeaveType:
        self.session.add(leave_type)
        await self.session.flush()
        return leave_type

    # ── Leave Allocations ──────────────────────────────────────────────────────

    async def get_allocation(self, allocation_id: int) -> LeaveAllocation | None:
        stmt = (
            select(LeaveAllocation)
            .options(
                selectinload(LeaveAllocation.employee),
                selectinload(LeaveAllocation.leave_type),
                selectinload(LeaveAllocation.leave_period),
            )
            .where(LeaveAllocation.id == allocation_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_allocation(
        self,
        employee_id: int,
        leave_type_id: int,
        leave_period_id: int,
    ) -> LeaveAllocation | None:
        stmt = select(LeaveAllocation).where(
            LeaveAllocation.employee_id == employee_id,
            LeaveAllocation.leave_type_id == leave_type_id,
            LeaveAllocation.leave_period_id == leave_period_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def create_allocation(self, alloc: LeaveAllocation) -> LeaveAllocation:
        self.session.add(alloc)
        await self.session.flush()
        return alloc

    async def list_allocations(
        self,
        employee_id: int | None = None,
        leave_period_id: int | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[LeaveAllocation]:
        stmt = (
            select(LeaveAllocation)
            .options(
                selectinload(LeaveAllocation.employee),
                selectinload(LeaveAllocation.leave_type),
                selectinload(LeaveAllocation.leave_period),
            )
            .order_by(LeaveAllocation.created_at.desc())
        )
        if employee_id is not None:
            stmt = stmt.where(LeaveAllocation.employee_id == employee_id)
        elif unit_ids or department_ids:
            stmt = stmt.join(Employee, LeaveAllocation.employee_id == Employee.id)
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        if leave_period_id is not None:
            stmt = stmt.where(LeaveAllocation.leave_period_id == leave_period_id)
        return list((await self.session.execute(stmt)).scalars().all())

    # ── Leave Ledger ───────────────────────────────────────────────────────────

    async def create_ledger_entry(self, entry: LeaveLedgerEntry) -> LeaveLedgerEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_ledger_balance(
        self,
        employee_id: int,
        leave_type_id: int,
        from_date: date,
        to_date: date,
    ) -> float:
        """
        Calculates cumulative leave balance from ledger entries
        overlapping with [from_date, to_date].
        """
        stmt = select(func.coalesce(func.sum(LeaveLedgerEntry.leaves), 0.0)).where(
            LeaveLedgerEntry.employee_id == employee_id,
            LeaveLedgerEntry.leave_type_id == leave_type_id,
            LeaveLedgerEntry.is_expired == False,
            LeaveLedgerEntry.to_date >= from_date,
            LeaveLedgerEntry.from_date <= to_date,
        )
        balance = (await self.session.execute(stmt)).scalar_one()
        return float(balance)

    async def list_ledger_entries(
        self,
        employee_id: int,
        leave_type_id: int | None = None,
    ) -> list[LeaveLedgerEntry]:
        stmt = (
            select(LeaveLedgerEntry)
            .options(selectinload(LeaveLedgerEntry.leave_type))
            .where(LeaveLedgerEntry.employee_id == employee_id)
            .order_by(LeaveLedgerEntry.created_at.desc())
        )
        if leave_type_id is not None:
            stmt = stmt.where(LeaveLedgerEntry.leave_type_id == leave_type_id)
        return list((await self.session.execute(stmt)).scalars().all())

    # ── Leave Applications ─────────────────────────────────────────────────────

    async def get_application_by_id(self, application_id: int) -> LeaveApplication | None:
        stmt = (
            select(LeaveApplication)
            .options(
                selectinload(LeaveApplication.employee),
                selectinload(LeaveApplication.leave_type),
                selectinload(LeaveApplication.leave_period),
            )
            .where(LeaveApplication.id == application_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_overlapping_application(
        self,
        employee_id: int,
        from_date: date,
        to_date: date,
        exclude_id: int | None = None,
    ) -> LeaveApplication | None:
        stmt = select(LeaveApplication).where(
            LeaveApplication.employee_id == employee_id,
            # An early-return request is still an approved leave until its
            # approver decides otherwise, so it must continue to reserve the
            # original dates and prevent overlapping applications.
            LeaveApplication.status.in_(["PENDING", "APPROVED", "CANCELLATION_PENDING"]),
            LeaveApplication.from_date <= to_date,
            LeaveApplication.to_date >= from_date,
        )
        if exclude_id is not None:
            stmt = stmt.where(LeaveApplication.id != exclude_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def create_application(self, app: LeaveApplication) -> LeaveApplication:
        self.session.add(app)
        await self.session.flush()
        return app

    async def list_applications(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
    ) -> list[LeaveApplication]:
        stmt = (
            select(LeaveApplication)
            .options(
                selectinload(LeaveApplication.employee),
                selectinload(LeaveApplication.leave_type),
                selectinload(LeaveApplication.leave_period),
            )
            .order_by(LeaveApplication.applied_at.desc())
        )
        if employee_id is not None:
            stmt = stmt.where(LeaveApplication.employee_id == employee_id)
        elif unit_ids or department_ids:
            stmt = stmt.join(Employee, LeaveApplication.employee_id == Employee.id)
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        if status is not None:
            stmt = stmt.where(LeaveApplication.status == status.upper())
        if from_date is not None:
            stmt = stmt.where(LeaveApplication.to_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(LeaveApplication.from_date <= to_date)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_applications_page(
        self,
        employee_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        unit_ids: set[int] | None = None,
        department_ids: set[int] | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 25,
    ) -> dict:
        stmt = (
            select(LeaveApplication)
            .options(
                selectinload(LeaveApplication.employee),
                selectinload(LeaveApplication.leave_type),
                selectinload(LeaveApplication.leave_period),
            )
            .order_by(LeaveApplication.applied_at.desc())
        )
        if employee_id is not None:
            stmt = stmt.where(LeaveApplication.employee_id == employee_id)
        elif unit_ids or department_ids:
            stmt = stmt.join(Employee, LeaveApplication.employee_id == Employee.id)
            filters = []
            if unit_ids:
                filters.append(Employee.unit_id.in_(unit_ids))
            if department_ids:
                filters.append(Employee.department_id.in_(department_ids))
            stmt = stmt.where(or_(*filters))
        if status is not None:
            stmt = stmt.where(LeaveApplication.status.in_([value.strip().upper() for value in status.split(",")]))
        if from_date is not None:
            stmt = stmt.where(LeaveApplication.to_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(LeaveApplication.from_date <= to_date)
        if search:
            ids = employee_search(select(Employee.id), Employee, search)
            stmt = stmt.where(LeaveApplication.employee_id.in_(ids))
        stmt = ordered(stmt, {"applied_at": LeaveApplication.applied_at, "status": LeaveApplication.status, "id": LeaveApplication.id}, sort_by, sort_order, "applied_at", LeaveApplication.id)
        return await paginate(self.session, stmt, page, page_size)
