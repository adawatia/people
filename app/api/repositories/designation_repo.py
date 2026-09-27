from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Designation


class DesignationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, designation_id: int) -> Designation | None:
        return await self.session.get(Designation, designation_id)

    async def get_by_erp_id(self, erp_id: str) -> Designation | None:
        return await self.session.scalar(select(Designation).where(Designation.erp_id == erp_id))

    async def get_by_name(self, name: str) -> Designation | None:
        stmt = select(Designation).where(Designation.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_code(self, code: str) -> Designation | None:
        stmt = select(Designation).where(Designation.code == code)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_all(self, is_active: bool | None = None) -> list[Designation]:
        stmt = select(Designation).order_by(Designation.name)
        if is_active is not None:
            stmt = stmt.where(Designation.is_active == is_active)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, designation: Designation) -> Designation:
        self.session.add(designation)
        await self.session.flush()
        return designation

    async def delete(self, designation: Designation) -> None:
        await self.session.delete(designation)
        await self.session.flush()
