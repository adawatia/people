from db.models import now_ist
from repositories.dashboard_repo import dashboard_metrics
from repositories.employee_repo import EmployeeRepository
from services.shift_service import ShiftService


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


class DashboardService:
    def __init__(self, session):
        self.session = session

    async def metrics(self, user):
        result = await dashboard_metrics(user, self.session)
        employee = await EmployeeRepository(self.session).get_by_user_id(user.id)
        if employee is not None:
            schedule = await ShiftService(self.session).get_employee_shift_schedule(employee.id, now_ist())
            result["employeeMetrics"]["currentShift"] = _dashboard_shift(schedule.assigned_shift)
            result["employeeMetrics"]["upcomingShift"] = _dashboard_shift(schedule.upcoming_shift)
        return result
