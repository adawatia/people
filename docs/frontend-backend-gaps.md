# Frontend-Backend Gap Analysis & Alignment Plan

This document tracks functional differences, contract gaps, and missing endpoints between the Frappe HR UX expectation and our current FastAPI backend implementation.

---

## 1. Identified Gaps and Resolutions

### Gap 1: Current User's Linked Employee Record
- **Frappe UX Expectation**: When an employee logs in, the dashboard immediately knows their `employee_id`, current shift, leave balance, and pending requests based on the session.
- **Current FastAPI Status**: `/api/v1/users/me` returns user identity (`id`, `email`, `role`, `permissions`), but does not return the linked `employee_id` or `Employee` profile.
- **Resolution**:
  - Frontend checks if the user is linked to an employee by calling `/api/v1/employees/?q={email}` or reading `employee_code`.
  - Recommended minor FastAPI enhancement: Include `employee_id` and `employee_code` in `UserResponse` on `/api/v1/users/me` when an employee profile exists.

---

### Gap 2: Punch Geolocation Verification
- **Frappe UX Expectation**: Frappe Mobile captures latitude and longitude during mobile punch-in, displaying a mini map preview before confirmation.
- **Current FastAPI Status**: `AttendancePunchCreate` in FastAPI schema (`apps/api/schemas/attendance.py`) already supports `latitude: Optional[float]`, `longitude: Optional[float]`, `device_id`, and `punch_type`.
- **Resolution**: Fully supported. Nuxt UI check-in component uses browser `navigator.geolocation.getCurrentPosition` to supply `latitude` and `longitude` to `POST /api/v1/attendance/checkins`. No backend schema changes needed.

---

### Gap 3: Shift Calendar Matrix View
- **Frappe UX Expectation**: Frappe HR provides a visual team roster grid showing who is assigned to Morning, Afternoon, or Night shifts on each day of the month.
- **Current FastAPI Status**:
  - Individual schedule endpoint: `GET /api/v1/shifts/employee/{employee_id}/schedule?start_date=...&end_date=...`
  - Bulk assignments endpoint: `GET /api/v1/shifts/assignments?unit_id=...&start_date=...&end_date=...`
- **Resolution**: The frontend calendar can render the individual schedule using `/schedule` and the unit roster by combining active assignments and shift definitions. No backend gap.

---

### Gap 4: Real-Time Leave Balance Preview During Application
- **Frappe UX Expectation**: Selecting a Leave Type and date span immediately displays the deducted days and remaining balance *before* the user clicks Submit.
- **Current FastAPI Status**:
  - `GET /api/v1/leaves/balance/employee/{employee_id}` provides the current remaining balance per leave type.
  - Leave dates calculation (counting non-working days / holidays) is evaluated during `POST /api/v1/leaves/`.
- **Resolution**: The frontend uses `useLeave()` to fetch the employee's current balance array upon opening the modal. Days count between `from_date` and `to_date` is previewed on the form and authoritative balance deduction is verified and returned by FastAPI.

---

### Gap 5: Overtime Report vs. Attendance Matrix
- **Frappe UX Expectation**: Dedicated Overtime analysis table showing total OT hours approved per department.
- **Current FastAPI Status**:
  - Daily overtime minutes are already calculated and stored in `attendance_records.overtime_minutes` by the attendance processing engine (`AttendanceService.process_attendance`).
  - Attendance matrix endpoint `/api/v1/reports/attendance-matrix` returns daily attendance status.
- **Resolution**: The Overtime report page can query `/api/v1/attendance/` filtered by `min_overtime_minutes > 0` or compute departmental OT totals from attendance records. A dedicated backend aggregate endpoint `GET /api/v1/reports/overtime-summary` can be added in a future enhancement if high-scale aggregation is needed.

---

### Gap 6: Direct Attendance Regularisation (Correction) Workflow
- **Frappe UX Expectation**: Employee spots a missing punch or `ABSENT` day, clicks "Request Attendance / Regularise", picks the corrected in/out time, and manager receives an approval prompt.
- **Current FastAPI Status**:
  - Creation: `POST /api/v1/attendance/corrections`
  - Approval: `PATCH /api/v1/attendance/corrections/{id}/approve`
  - Rejection: `PATCH /api/v1/attendance/corrections/{id}/reject`
- **Resolution**: Fully supported by the FastAPI backend. Nuxt UI will provide the regularisation dialog on the Attendance page and the approval queue in the Manager/HR view.

---

## 2. Gap Summary Matrix

| Feature | Frappe HR Reference | FastAPI Endpoint Available | Frontend Status | Backend Status | Resolution State |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Self-Service Linked Employee** | User session links to Employee profile | `/api/v1/users/me`, `/api/v1/employees/` | Implemented via `official_email` lookup | Included in Employee schema | **Resolved** |
| **Mobile Geolocation Punch** | `CheckInPanel.vue` with Google Maps | `POST /api/v1/attendance/checkins` | Implemented in `CheckinWidget.vue` with GPS | Supported in schema & repo | **Resolved** |
| **Attendance Batch Processing** | Shift Process Tool | `POST /api/v1/attendance/process` | Implemented in `AttendanceProcessModal.vue` | Engine operational in backend | **Resolved** |
| **Punch Regularisations** | Attendance Request | `POST /api/v1/attendance/corrections` | Implemented in `corrections.vue` & `CorrectionModal.vue` | Approval/Rejection routes active | **Resolved** |
| **Double-Entry Leave Balance** | `Leave Ledger Entry` | `GET /api/v1/leaves/balance/employee/{id}` | Implemented in `LeaveBalanceCards.vue` & `apply.vue` | Ledger balance calculation live | **Resolved** |
| **Leave Allocations & Approval** | Leave Allocation & Approval | `GET/POST /api/v1/leaves/allocations`, `PATCH .../approve` | Implemented in `allocations.vue` & `approvals.vue` | Roster auto-sync on approve | **Resolved** |
| **Shift Definitions & Overnight** | Shift Type cross-midnight | `GET/POST /api/v1/shifts/`, `PATCH .../{id}` | Implemented in `shifts/index.vue` & `ShiftFormModal.vue` | Window calculation live | **Resolved** |
| **Shift Allocations & Bulk** | Shift Assignment | `GET/POST /api/v1/shifts/assignments`, `PATCH .../cancel` | Implemented in `assignments.vue` & `BulkShiftAssignmentModal.vue` | Individual & Bulk active | **Resolved** |
| **Schedule Roster Inspection** | Shift Schedule Inspector | `GET /api/v1/shifts/employee/{id}/schedule` | Implemented in `shifts/schedule.vue` | Timeline windows live | **Resolved** |
| **Work Arrangement Workflow** | Remote Work Requests | `POST /api/v1/work-arrangements/` | Scheduled for Phase 6 | Endpoints available in backend | **Ready for Phase 6** |
| **Holiday Matrix & Weekly Off** | Holiday List Generator | `GET/POST /api/v1/holidays/lists` | Scheduled for Phase 7 | Endpoints available in backend | **Ready for Phase 7** |
