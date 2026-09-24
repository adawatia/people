"""Public sort contracts for paginated API endpoints.

These aliases intentionally mirror the allowlists enforced by repositories.
Using them in router signatures publishes the accepted values in OpenAPI and
rejects unsupported sort keys before a query reaches the persistence layer.
"""

from typing import Literal

type AttendanceCorrectionSort = Literal["requested_at", "status", "id"]
type AttendancePunchSort = Literal["punch_time", "punch_type", "source", "is_processed", "id"]
type AttendanceRecordSort = Literal["attendance_date", "status", "id"]
type EmployeeHistorySort = Literal["from_date", "to_date", "created_at", "id"]
type EmployeeReportSort = Literal["employee_code", "name"]
type EmployeeSort = Literal["employee_code", "name", "created_at", "status"]
type LeaveApplicationSort = Literal["applied_at", "status", "id"]
type LookupSort = Literal["name", "id"]
type NotificationSort = Literal["created_at", "id"]
type OvertimeSort = Literal["attendance_date", "status", "id"]
type OwnerExceptionSort = Literal["employee_code", "name", "unit_id", "department_id", "id"]
type ShiftAssignmentSort = Literal["effective_from", "status"]
type ShiftDefinitionSort = Literal["name", "code", "start_time", "id"]
type WorkArrangementSort = Literal["created_at", "status", "id"]
