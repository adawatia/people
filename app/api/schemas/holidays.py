from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class HolidayBase(BaseModel):
    name: str
    holiday_date: date
    description: str | None = None
    is_weekly_off: bool = False
    is_organization_wide: bool = True


class HolidayCreate(HolidayBase):
    holiday_list_id: int | None = None
    unit_id: int | None = None


class HolidayRead(HolidayBase):
    id: int
    holiday_list_id: int | None = None
    unit_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class HolidayListBase(BaseModel):
    name: str
    from_date: date
    to_date: date
    weekly_off_day: str = "Sunday"
    is_default: bool = False


class HolidayListCreate(HolidayListBase):
    unit_id: int | None = None
    holidays: list[HolidayBase] = []


class HolidayListUpdate(BaseModel):
    name: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    weekly_off_day: str | None = None
    is_default: bool | None = None
    unit_id: int | None = None


class HolidayListRead(HolidayListBase):
    id: int
    unit_id: int | None = None
    created_at: datetime
    holidays: list[HolidayRead] = []
    model_config = ConfigDict(from_attributes=True)
