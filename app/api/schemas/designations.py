from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DesignationBase(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None
    is_active: bool = True


class DesignationCreate(DesignationBase):
    model_config = ConfigDict(json_schema_extra={"example": {"name": "Senior Engineer", "code": "ENG-SR", "description": "Senior engineering role", "is_active": True}})


class DesignationUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    is_active: bool | None = None
    model_config = ConfigDict(json_schema_extra={"example": {"name": "Senior Engineer", "is_active": False}})


class DesignationRead(DesignationBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
