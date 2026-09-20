from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrganizationBase(BaseModel):
    name: str
    short_name: str | None = None
    industry: str | None = None


class OrganizationRead(OrganizationBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DepartmentBase(BaseModel):
    name: str
    code: str | None = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    unit_id: int


class DepartmentUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    is_active: bool | None = None


class DepartmentRead(DepartmentBase):
    id: int
    unit_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UnitBase(BaseModel):
    name: str
    code: str | None = None
    city: str | None = None
    is_active: bool = True


class UnitCreate(UnitBase):
    organization_id: int


class UnitUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    city: str | None = None
    is_active: bool | None = None


class UnitRead(UnitBase):
    id: int
    organization_id: int
    created_at: datetime
    departments: list[DepartmentRead] = []
    model_config = ConfigDict(from_attributes=True)
