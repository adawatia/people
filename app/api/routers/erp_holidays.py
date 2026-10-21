"""ERP-owned organization-wide holiday synchronization.

ERP owns the holiday calendar. HRMS keeps one organization-wide list and mirrors
what ERP sends: ``is_active=false`` removes the holiday, and a holiday date that
already belongs to a different ERP holiday id is a conflict rather than a second
row on the same day (which would double-count the day in leave and attendance
calculations).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import add_audit_event
from core.database import get_async_session
from core.erp_auth import ErpPrincipal, require_erp_scope
from core.erp_batch import (
    ErpBatchResult,
    ErpItemError,
    apply_batch_status,
    classify_erp_error,
    log_erp_item_failure,
    new_batch,
    record_batch,
    resolve_batch_id,
)
from db.models import Holiday, HolidayList, now_ist

router = APIRouter(prefix="/integrations/erp/holidays", tags=["erp-holidays"])

CHUNK_SIZE = 500


class ErpHoliday(BaseModel):
    erp_holiday_id: str
    name: str
    holiday_date: date
    description: str | None = None
    is_active: bool = True


async def _default_calendar(session: AsyncSession) -> HolidayList:
    calendar = await session.scalar(
        select(HolidayList).where(HolidayList.is_default.is_(True)).order_by(HolidayList.id)
    )
    if calendar is None:
        today = now_ist().date()
        calendar = HolidayList(
            name="ERP Holiday Calendar",
            from_date=date(today.year, 1, 1),
            to_date=date(today.year, 12, 31),
            weekly_off_day="Sunday",
            is_default=True,
        )
        session.add(calendar)
        await session.flush()
    return calendar


async def sync_holidays_bulk(
    holidays: list[ErpHoliday],
    session: AsyncSession = Depends(get_async_session),
    *,
    batch_id: str | None = None,
    client_id: str | None = None,
) -> ErpBatchResult:
    result = new_batch("holidays.bulk", batch_id or uuid.uuid4().hex, len(holidays))
    if not holidays:
        return result

    calendar = await _default_calendar(session)
    for start in range(0, len(holidays), CHUNK_SIZE):
        chunk = holidays[start : start + CHUNK_SIZE]
        existing_events = {
            row.erp_holiday_id: row
            for row in (
                await session.execute(
                    select(Holiday).where(Holiday.erp_holiday_id.in_({item.erp_holiday_id for item in chunk}))
                )
            ).scalars()
        }
        by_date = {
            row.holiday_date: row
            for row in (
                await session.execute(
                    select(Holiday).where(
                        Holiday.holiday_list_id == calendar.id,
                        Holiday.holiday_date.in_({item.holiday_date for item in chunk}),
                    )
                )
            ).scalars()
        }

        outcomes: list[tuple[str, str, int | None]] = []
        for item in chunk:
            try:
                async with session.begin_nested():
                    holiday = existing_events.get(item.erp_holiday_id)
                    if not item.is_active:
                        if holiday is None:
                            outcomes.append(("duplicate", item.erp_holiday_id, None))
                            continue
                        add_audit_event(
                            session,
                            actor=None,
                            action="ERP_HOLIDAY_REMOVED",
                            entity_type="holiday",
                            entity_id=str(holiday.id),
                            filters={
                                "erp_batch_id": result.batch_id,
                                "erp_holiday_id": item.erp_holiday_id,
                                "holiday_date": holiday.holiday_date,
                                "name": holiday.name,
                            },
                        )
                        by_date.pop(holiday.holiday_date, None)
                        existing_events.pop(item.erp_holiday_id, None)
                        await session.delete(holiday)
                        outcomes.append(("accepted", item.erp_holiday_id, None))
                        continue

                    same_day = by_date.get(item.holiday_date)
                    if same_day is not None and same_day.erp_holiday_id != item.erp_holiday_id:
                        raise ErpItemError(
                            "HOLIDAY_DATE_CONFLICT",
                            f"This date is already holiday {same_day.erp_holiday_id!r}",
                        )

                    if holiday is None:
                        holiday = Holiday(
                            erp_holiday_id=item.erp_holiday_id,
                            holiday_list_id=calendar.id,
                            name=item.name,
                            holiday_date=item.holiday_date,
                        )
                        session.add(holiday)
                    elif (
                        holiday.name == item.name
                        and holiday.holiday_date == item.holiday_date
                        and holiday.description == item.description
                        and holiday.holiday_list_id == calendar.id
                        and holiday.is_organization_wide
                        and not holiday.is_weekly_off
                    ):
                        outcomes.append(("duplicate", item.erp_holiday_id, holiday.id))
                        continue
                    else:
                        previous_date = holiday.holiday_date
                        holiday.holiday_list_id = calendar.id
                        holiday.name = item.name
                        holiday.holiday_date = item.holiday_date
                        if previous_date != item.holiday_date:
                            by_date.pop(previous_date, None)

                    holiday.description = item.description
                    holiday.is_organization_wide = True
                    holiday.is_weekly_off = False
                    await session.flush()
                    existing_events[item.erp_holiday_id] = holiday
                    by_date[item.holiday_date] = holiday
                outcomes.append(("accepted", item.erp_holiday_id, holiday.id))
            except Exception as exc:
                log_erp_item_failure(item.erp_holiday_id, exc, result.batch_id, result.endpoint)
                code, message, retryable = classify_erp_error(exc)
                result.add_failure(item.erp_holiday_id, code=code, message=message, retryable=retryable)

        await session.commit()
        for status, key, local_id in outcomes:
            if status == "duplicate":
                result.add_duplicate(key, local_id)
            else:
                result.add_accepted(key, local_id)
    return result


@router.post(
    "/bulk",
    response_model=ErpBatchResult,
    summary="Bulk sync ERP holidays",
    description=(
        "Upserts organization-wide holidays by `erp_holiday_id`. Replaying "
        "unchanged values reports `duplicate`; `is_active=false` removes the "
        "holiday; two ERP ids on the same date conflict rather than double-booking "
        "the day."
    ),
)
async def sync_holidays_bulk_endpoint(
    response: Response,
    holidays: Annotated[list[ErpHoliday], Body(min_length=1, max_length=5000)],
    batch_id: Annotated[str, Depends(resolve_batch_id)],
    principal: Annotated[ErpPrincipal, Depends(require_erp_scope("holidays:write"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ErpBatchResult:
    result = await sync_holidays_bulk(holidays, session, batch_id=batch_id, client_id=principal.client_id)
    apply_batch_status(response, result)
    await record_batch(session, result, client_id=principal.client_id, http_status=response.status_code)
    await session.commit()
    return result
