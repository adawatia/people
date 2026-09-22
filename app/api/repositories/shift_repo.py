from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Shift, ShiftAssignment, now_ist


class ShiftRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, shift_id: int) -> Shift | None:
        return await self.session.get(Shift, shift_id)

    async def get_by_name(self, name: str, unit_id: int | None = None) -> Shift | None:
        stmt = select(Shift).where(Shift.name == name)
        if unit_id is not None:
            stmt = stmt.where(Shift.unit_id == unit_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_shifts(self, unit_id: int | None = None, is_active: bool | None = True) -> list[Shift]:
        stmt = select(Shift)
        if is_active is not None:
            stmt = stmt.where(Shift.is_active == is_active)
        if unit_id is not None:
            stmt = stmt.where(or_(Shift.unit_id == unit_id, Shift.unit_id.is_(None)))
        stmt = stmt.order_by(Shift.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_shift(self, shift: Shift) -> Shift:
        self.session.add(shift)
        await self.session.flush()
        return shift

    # ── Shift Assignments ──────────────────────────────────────────────────────

    async def get_assignment_by_id(self, assignment_id: int) -> ShiftAssignment | None:
        stmt = (
            select(ShiftAssignment)
            .options(selectinload(ShiftAssignment.shift), selectinload(ShiftAssignment.employee))
            .where(ShiftAssignment.id == assignment_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_active_assignments_for_date(self, employee_id: int, target_date: date) -> list[ShiftAssignment]:
        """Finds all active shift assignments for an employee overlapping with target_date."""
        stmt = (
            select(ShiftAssignment)
            .options(selectinload(ShiftAssignment.shift))
            .where(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.status == "ACTIVE",
                ShiftAssignment.effective_from <= target_date,
                or_(
                    ShiftAssignment.effective_to.is_(None),
                    ShiftAssignment.effective_to >= target_date,
                ),
            )
            .order_by(ShiftAssignment.effective_from.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_active_assignments_between(
        self,
        employee_id: int,
        start_date: date,
        end_date: date,
    ) -> list[ShiftAssignment]:
        """Finds active assignments overlapping [start_date, end_date] in one query.

        This is the batched counterpart of `list_active_assignments_for_date`:
        schedule lookups that need the effective shift for many consecutive days
        use this and partition the result in Python instead of issuing one query
        per calendar date.
        """
        stmt = (
            select(ShiftAssignment)
            .options(selectinload(ShiftAssignment.shift))
            .where(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.status == "ACTIVE",
                ShiftAssignment.effective_from <= end_date,
                or_(
                    ShiftAssignment.effective_to.is_(None),
                    ShiftAssignment.effective_to >= start_date,
                ),
            )
            .order_by(ShiftAssignment.effective_from.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_active_assignment_shifts(
        self,
        employee_id: int,
        today: date | None = None,
        lookahead_days: int = 15,
    ) -> list[Shift]:
        """Return the distinct shift definitions the employee works over the
        next `lookahead_days` (including today and any night shift started
        yesterday) — the only shifts a self-scoped employee needs to see.
        """
        today = today or now_ist().date()
        end_date = today + timedelta(days=lookahead_days - 1)
        stmt = (
            select(Shift)
            .distinct()
            .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.status == "ACTIVE",
                ShiftAssignment.effective_from <= end_date,
                or_(
                    ShiftAssignment.effective_to.is_(None),
                    ShiftAssignment.effective_to >= today,
                ),
            )
            .order_by(Shift.name)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_overlapping_assignment(
        self,
        employee_id: int,
        effective_from: date,
        effective_to: date | None = None,
        exclude_id: int | None = None,
    ) -> ShiftAssignment | None:
        """Checks if employee already has an active shift assignment overlapping with [effective_from, effective_to]."""
        stmt = (
            select(ShiftAssignment)
            .options(selectinload(ShiftAssignment.shift))
            .where(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.status == "ACTIVE",
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(ShiftAssignment.id != exclude_id)

        if effective_to is not None:
            # Overlaps if assignment.from <= new_to AND (assignment.to is NULL OR assignment.to >= new_from)
            stmt = stmt.where(
                ShiftAssignment.effective_from <= effective_to,
                or_(
                    ShiftAssignment.effective_to.is_(None),
                    ShiftAssignment.effective_to >= effective_from,
                ),
            )
        else:
            # New assignment is open-ended: overlaps if assignment.to is NULL OR assignment.to >= new_from
            stmt = stmt.where(
                or_(
                    ShiftAssignment.effective_to.is_(None),
                    ShiftAssignment.effective_to >= effective_from,
                )
            )

        return (await self.session.execute(stmt)).scalars().first()

    async def create_assignment(self, assignment: ShiftAssignment) -> ShiftAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def list_employee_assignments(self, employee_id: int) -> list[ShiftAssignment]:
        stmt = (
            select(ShiftAssignment)
            .options(selectinload(ShiftAssignment.shift), selectinload(ShiftAssignment.employee))
            .where(ShiftAssignment.employee_id == employee_id)
            .order_by(ShiftAssignment.effective_from.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_assignments(
        self,
        shift_id: int | None = None,
        employee_id: int | None = None,
        status: str | None = None,
    ) -> list[ShiftAssignment]:
        stmt = (
            select(ShiftAssignment)
            .options(selectinload(ShiftAssignment.shift), selectinload(ShiftAssignment.employee))
            .order_by(ShiftAssignment.effective_from.desc())
        )
        if shift_id is not None:
            stmt = stmt.where(ShiftAssignment.shift_id == shift_id)
        if employee_id is not None:
            stmt = stmt.where(ShiftAssignment.employee_id == employee_id)
        if status is not None:
            stmt = stmt.where(ShiftAssignment.status == status.upper())
        return list((await self.session.execute(stmt)).scalars().all())
