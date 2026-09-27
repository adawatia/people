"""routers/dashboard.py — Dynamic permission-based dashboard widget API."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import record_audit_event
from core.auth import current_business_user, current_sensitive_user, get_user_permissions
from core.database import get_async_session
from core.rbac import get_visible_widgets
from core.sorting import OwnerExceptionSort
from db.models import (
    Employee,
    User,
)
from schemas.dashboard import (
    DashboardMetricsResponse,
    DashboardWidgetsResponse,
    OwnerDashboardResponse,
    OwnerExceptionResponse,
    TechnicalAdminMetrics,
)
from services.owner_dashboard_service import OwnerDashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
PENDING_LEAVE_STATUSES = ("PENDING", "CANCELLATION_PENDING")


def _audit_request_values(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("x-request-id"), request.client.host if request.client else None


def _dashboard_shift(window) -> dict[str, object] | None:
    """Convert a shift window to the narrow, employee-safe dashboard projection."""
    if window is None:
        return None
    return {
        "name": window.shift_name,
        "shiftDate": window.shift_start.date(),
        "startsAt": window.shift_start,
        "endsAt": window.shift_end,
        "isCrossMidnight": window.is_cross_midnight,
    }


@router.get("/owner", response_model=OwnerDashboardResponse, summary="Organization owner analytics dashboard")
async def get_owner_dashboard(
    request: Request,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    unit_id: int | None = Query(None),
    user: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> OwnerDashboardResponse:
    if "dashboard.view_organization" not in await get_user_permissions(user, session):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Organization owner analytics access required")
    payload = await OwnerDashboardService(session).dashboard(from_date, to_date, unit_id)
    request_id, ip_address = _audit_request_values(request)
    await record_audit_event(
        session,
        actor=user,
        action="ORGANIZATION_DASHBOARD_VIEWED",
        entity_type="organization_dashboard",
        filters={"from_date": payload.from_date, "to_date": payload.to_date, "unit_id": unit_id},
        request_id=request_id,
        ip_address=ip_address,
    )
    return payload


@router.get(
    "/owner/exceptions", response_model=OwnerExceptionResponse, summary="Organization owner exception drill-down"
)
async def get_owner_exceptions(
    request: Request,
    kind: str = Query(...),
    target_date: date = Query(default_factory=date.today),
    unit_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    sort_by: OwnerExceptionSort | None = Query(None),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    user: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> OwnerExceptionResponse:
    if "dashboard.view_organization" not in await get_user_permissions(user, session):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Organization owner analytics access required")
    payload = await OwnerDashboardService(session).exceptions(
        kind, unit_id, target_date, page, page_size, search, sort_by, sort_order
    )
    request_id, ip_address = _audit_request_values(request)
    await record_audit_event(
        session,
        actor=user,
        action="ORGANIZATION_EXCEPTION_DRILLDOWN_VIEWED",
        entity_type="employee_directory",
        filters={
            "kind": kind,
            "target_date": target_date,
            "unit_id": unit_id,
            "page": page,
            "search": search,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
        request_id=request_id,
        ip_address=ip_address,
    )
    return payload


@router.get("/technical-metrics", response_model=TechnicalAdminMetrics, summary="Get technical administration counts")
async def get_technical_metrics(
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
) -> TechnicalAdminMetrics:
    if not user.is_superuser:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Technical administrator access required")
    from db.models import Department, Designation, Unit

    return TechnicalAdminMetrics(
        users=await session.scalar(select(func.count(User.id)).where(User.is_superuser.is_(False))) or 0,
        employees=await session.scalar(select(func.count(Employee.id)).where(Employee.status == "ACTIVE")) or 0,
        units=await session.scalar(select(func.count(Unit.id)).where(Unit.is_active.is_(True))) or 0,
        departments=await session.scalar(select(func.count(Department.id)).where(Department.is_active.is_(True))) or 0,
        designations=await session.scalar(select(func.count(Designation.id)).where(Designation.is_active.is_(True)))
        or 0,
    )


@router.get(
    "/widgets",
    response_model=DashboardWidgetsResponse,
    summary="Get dashboard widgets visible to the current user",
)
async def get_dashboard_widgets(
    user: User = Depends(current_sensitive_user),
    session: AsyncSession = Depends(get_async_session),
) -> DashboardWidgetsResponse:
    widgets = await get_visible_widgets(user, session)
    return DashboardWidgetsResponse(widgets=widgets)


@router.get(
    "/metrics",
    response_model=DashboardMetricsResponse,
    summary="Get aggregated KPIs and metrics for the dashboard",
)
async def get_dashboard_metrics(
    user: User = Depends(current_business_user),
    session: AsyncSession = Depends(get_async_session),
) -> DashboardMetricsResponse:
    from services.dashboard_service import DashboardService

    return await DashboardService(session).metrics(user)
