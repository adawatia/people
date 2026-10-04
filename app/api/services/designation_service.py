from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.erp_sync import acquire_erp_upsert_lock
from db.models import Designation
from repositories.designation_repo import DesignationRepository
from schemas.designations import DesignationCreate, DesignationUpdate


class DesignationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DesignationRepository(session)

    async def list_designations(self, is_active: bool | None = None) -> list[Designation]:
        return await self.repo.list_all(is_active=is_active)

    async def get_designation(self, designation_id: int) -> Designation:
        designation = await self.repo.get_by_id(designation_id)
        if not designation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Designation with ID {designation_id} not found",
            )
        return designation

    async def create_designation(self, data: DesignationCreate) -> Designation:
        # Check unique name
        existing = await self.repo.get_by_name(data.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Designation with name '{data.name}' already exists",
            )
        if data.code:
            existing_code = await self.repo.get_by_code(data.code)
            if existing_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Designation with code '{data.code}' already exists",
                )

        designation = Designation(**data.model_dump())
        created = await self.repo.create(designation)
        await self.session.commit()
        await self.session.refresh(created)
        return created

    async def update_designation(self, designation_id: int, data: DesignationUpdate) -> Designation:
        designation = await self.get_designation(designation_id)

        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] != designation.name:
            existing = await self.repo.get_by_name(update_data["name"])
            if existing and existing.id != designation_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Designation with name '{update_data['name']}' already exists",
                )

        if "code" in update_data and update_data["code"] and update_data["code"] != designation.code:
            existing_code = await self.repo.get_by_code(update_data["code"])
            if existing_code and existing_code.id != designation_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Designation with code '{update_data['code']}' already exists",
                )

        for key, val in update_data.items():
            setattr(designation, key, val)

        await self.session.commit()
        await self.session.refresh(designation)
        return designation

    async def upsert_designation(self, erp_id: str, data: DesignationUpdate) -> Designation:
        await acquire_erp_upsert_lock(self.session, "designation", erp_id)
        if "name" in data.model_fields_set and not data.name:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        if "is_active" in data.model_fields_set and data.is_active is None:
            raise HTTPException(status_code=422, detail="is_active cannot be null")
        designation = await self.repo.get_by_erp_id(erp_id)
        try:
            if designation is None:
                if not data.name:
                    raise HTTPException(status_code=422, detail="name is required when creating a designation")
                designation = Designation(
                    **DesignationCreate.model_validate(data.model_dump(exclude_unset=True)).model_dump(), erp_id=erp_id
                )
                await self.repo.create(designation)
            else:
                for key, value in data.model_dump(exclude_unset=True).items():
                    setattr(designation, key, value)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=409, detail="Designation conflicts with existing master data") from exc
        await self.session.refresh(designation)
        return designation

    async def delete_designation(self, designation_id: int) -> None:
        designation = await self.get_designation(designation_id)
        designation.is_active = False
        await self.session.commit()
