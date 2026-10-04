"""ERP leave status change feed and acknowledgements."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_async_session
from core.erp_auth import require_erp_scope
from db.models import Employee, LeaveApplication, LeaveBalance, LeaveType, now_ist
from schemas.leaves import LeavePeriodCreate, LeavePeriodRead, LeaveTypeCreate, LeaveTypeRead, LeaveTypeUpdate
from services.leave_service import LeaveService

router = APIRouter(prefix="/integrations/erp/leaves", tags=["erp-leaves"])


class ErpLeaveBalance(BaseModel):
    employee_id: int | None = None
    employee_code: str | None = None
    leave_code: str
    year: int = Field(..., ge=2000, le=2100)
    allocated: float = Field(default=0, ge=0)
    used: float = Field(default=0, ge=0)
    pending: float = Field(default=0, ge=0)
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "employee_code": "EMP001",
                    "leave_code": "CL",
                    "year": 2026,
                    "allocated": 12,
                    "used": 2,
                    "pending": 0,
                }
            ]
        }
    }


class ErpLeaveChange(BaseModel):
    event_id: str | None
    leave_id: int
    employee_code: str
    leave_code: str
    from_date: date
    to_date: date
    days: float
    status: str
    reason: str | None
    rejection_reason: str | None
    approved_at: datetime | None


class ErpLeaveChangesResponse(BaseModel):
    items: list[ErpLeaveChange] = Field(default_factory=list)
    has_more: bool


class ErpLeaveChangesAcknowledgement(BaseModel):
    acknowledged: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)


class ErpLeaveBalanceSyncAccepted(BaseModel):
    employee_id: int
    leave_code: str
    year: int


class ErpLeaveBalanceSyncFailure(BaseModel):
    employee_code: str | None
    leave_code: str
    error: str


class ErpLeaveBalanceSyncResult(BaseModel):
    accepted: list[ErpLeaveBalanceSyncAccepted] = Field(default_factory=list)
    failed: list[ErpLeaveBalanceSyncFailure] = Field(default_factory=list)


@router.get(
    "/changes",
    response_model=ErpLeaveChangesResponse,
    dependencies=[Depends(require_erp_scope("leaves:read"))],
)
async def get_leave_changes(
    since: datetime | None = Query(None, description="Return events updated after this timestamp"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_async_session),
) -> ErpLeaveChangesResponse:
    stmt = (
        select(LeaveApplication)
        .options(selectinload(LeaveApplication.employee), selectinload(LeaveApplication.leave_type))
        .where(LeaveApplication.erp_sync_status != "ACKNOWLEDGED")
        .where(LeaveApplication.status.in_(["APPROVED", "REJECTED", "CANCELLED"]))
        .order_by(LeaveApplication.actioned_at.asc(), LeaveApplication.id.asc())
        .limit(limit)
    )
    if since:
        stmt = stmt.where(LeaveApplication.actioned_at > since)
    items = list((await session.execute(stmt)).scalars().all())
    return {
        "items": [
            {
                "event_id": item.erp_event_id,
                "leave_id": item.id,
                "employee_code": item.employee.employee_code,
                "leave_code": item.leave_type.code,
                "from_date": item.from_date,
                "to_date": item.to_date,
                "days": float(item.days_count),
                "status": item.status,
                "reason": item.reason,
                "rejection_reason": item.rejection_reason,
                "approved_at": item.actioned_at,
            }
            for item in items
        ],
        "has_more": len(items) == limit,
    }


@router.post(
    "/changes/ack",
    response_model=ErpLeaveChangesAcknowledgement,
    dependencies=[Depends(require_erp_scope("leaves:write"))],
)
async def acknowledge_leave_changes(
    event_ids: list[str],
    session: AsyncSession = Depends(get_async_session),
) -> ErpLeaveChangesAcknowledgement:
    if not event_ids:
        return {"acknowledged": [], "unknown": []}
    result = await session.execute(select(LeaveApplication).where(LeaveApplication.erp_event_id.in_(event_ids)))
    applications = list(result.scalars().all())
    found = {item.erp_event_id for item in applications}
    for item in applications:
        item.erp_sync_status = "ACKNOWLEDGED"
        item.erp_synced_at = now_ist()
    await session.commit()
    return {"acknowledged": sorted(found), "unknown": sorted(set(event_ids) - found)}


async def sync_leave_balances(
    balances: list[ErpLeaveBalance],
    session: AsyncSession = Depends(get_async_session),
) -> ErpLeaveBalanceSyncResult:
    accepted: list[dict] = []
    failed: list[dict] = []
    for item in balances:
        try:
            employee = await session.get(Employee, item.employee_id) if item.employee_id else None
            if employee is None and item.employee_code:
                employee = await session.scalar(select(Employee).where(Employee.employee_code == item.employee_code))
            leave_type = await session.scalar(select(LeaveType).where(LeaveType.code == item.leave_code.upper()))
            if employee is None:
                identity = item.employee_id if item.employee_id is not None else item.employee_code
                raise ValueError(f"Employee {identity!r} not found")
            if leave_type is None:
                raise ValueError(f"Leave type code {item.leave_code.upper()!r} not found")
            balance = await session.scalar(
                select(LeaveBalance).where(
                    LeaveBalance.employee_id == employee.id,
                    LeaveBalance.leave_type_id == leave_type.id,
                    LeaveBalance.year == item.year,
                )
            )
            if balance is None:
                balance = LeaveBalance(employee_id=employee.id, leave_type_id=leave_type.id, year=item.year)
                session.add(balance)
            balance.allocated = int(item.allocated)
            balance.used = int(item.used)
            balance.pending = int(item.pending)
            await session.flush()
            accepted.append({"employee_id": employee.id, "leave_code": leave_type.code, "year": item.year})
        except Exception as exc:
            failed.append({"employee_code": item.employee_code, "leave_code": item.leave_code, "error": str(exc)})
    await session.commit()
    return {"accepted": accepted, "failed": failed}


@router.post(
    "/balances/bulk",
    response_model=ErpLeaveBalanceSyncResult,
    dependencies=[Depends(require_erp_scope("leaves:write"))],
    summary="Bulk sync ERP leave balances",
    description="Synchronizes balances for multiple employees, leave types, and years in one request.",
)
async def sync_leave_balances_bulk(
    balances: list[ErpLeaveBalance],
    session: AsyncSession = Depends(get_async_session),
) -> ErpLeaveBalanceSyncResult:
    return await sync_leave_balances(balances, session)


@router.post(
    "/periods",
    response_model=LeavePeriodRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("leave-master:write"))],
    summary="Create an ERP-owned leave period",
)
async def create_leave_period(data: LeavePeriodCreate, session: AsyncSession = Depends(get_async_session)) -> LeavePeriodRead:
    return await LeaveService(session).create_period(data)


@router.post(
    "/types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_erp_scope("leave-master:write"))],
    summary="Create an ERP-owned leave type",
)
async def create_leave_type(data: LeaveTypeCreate, session: AsyncSession = Depends(get_async_session)) -> LeaveTypeRead:
    return await LeaveService(session).create_type(data)


@router.patch(
    "/types/{type_id}",
    response_model=LeaveTypeRead,
    dependencies=[Depends(require_erp_scope("leave-master:write"))],
    summary="Update an ERP-owned leave type",
)
async def update_leave_type(
    type_id: int, data: LeaveTypeUpdate, session: AsyncSession = Depends(get_async_session)
) -> LeaveTypeRead:
    return await LeaveService(session).update_type(type_id, data)
