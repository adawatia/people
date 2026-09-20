from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DesignationBase(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None
    is_active: bool = True


class DesignationCreate(DesignationBase):
    pass


class DesignationUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    is_active: bool | None = None


class DesignationRead(DesignationBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
