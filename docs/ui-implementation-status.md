# UI Implementation Status & Feature Matrix

This document tracks each HRMS feature, referencing the Frappe HR baseline, corresponding Nuxt UI implementation, FastAPI backend endpoint, and current development status.

---

## 1. Feature Status Matrix

| Module | Feature | Frappe HR Reference | Nuxt Implementation | FastAPI Endpoint | Status | Remaining Work |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Shell & Auth** | App Shell & Sidebar | Desk Workspace | `layouts/default.vue`, `UNavigationMenu` | N/A | Complete | Expanded role-aware navigation for all HRMS modules |
| **Shell & Auth** | Central API Client & Types | Desk API Request | `composables/useApi.ts`, `types/*.ts` | All `/api/v1/*` | Complete | Strongly typed schemas matching FastAPI Pydantic contracts |
| **Shell & Auth** | JWT Authentication | Desk Login | `pages/login.vue`, `composables/useAuth.ts` | `POST /api/v1/auth/jwt/login`, `GET /api/v1/users/me` | Complete | Cookie JWT session, token refresh, and idle session guard |
| **Organization** | Units & Departments | Company & Department | `pages/org.vue`, `useOrg.ts` | `GET/POST /api/v1/org/units`, `GET/POST /api/v1/org/departments` | Complete | Units and departments tree management |
| **Organization** | Designations Master | Designation | `pages/org.vue`, `useOrg.ts` | `GET/POST/PATCH/DELETE /api/v1/designations/` | Complete | Job title and role taxonomy management tab |
| **Employees** | Employee List & Filters | Employee List | `pages/employees/index.vue`, `UTable` | `GET /api/v1/employees/` | Complete | Modern directory with multi-column filters, search, table/card views |
| **Employees** | Create / Edit Form | Employee Form | `pages/employees/create.vue`, `UForm` | `POST /api/v1/employees/`, `PUT /api/v1/employees/{id}` | Complete | Multi-section onboarding form: Personal, Org, Shift, Statutory |
| **Employees** | Employee Detail View | Employee View | `pages/employees/[id].vue`, `UTabs` | `GET /api/v1/employees/{id}` | Complete | 360° profile tabs for Personal, Org, Leave Quotas, Direct Reports |
| **Attendance** | Employee Check-in / Punch | Mobile CheckInPanel | `components/attendance/PunchPanel.vue` | `POST /api/v1/attendance/checkins` | Complete | Live clock, explicit one-time browser geolocation, denied-location fallback, and contextual IN/OUT action |
| **Attendance** | Self-service Calendar & Summary | Attendance Calendar | `pages/attendance/index.vue`, `AttendanceStatusBadge.vue` | `GET /api/v1/attendance/employee/{id}/calendar`, `GET .../summary` | Complete | Responsive monthly calendar, mobile record list, KPIs, punch times, and anomaly indicators |
| **Attendance** | Raw Check-ins Audit Log | Employee Checkin | `pages/attendance/checkins.vue` | `GET /api/v1/attendance/checkins` | Planned | Permission-scoped administrator audit log for biometric and mobile punches |
| **Attendance** | Regularisation Requests | Attendance Request | `pages/attendance/index.vue`, `pages/approvals/index.vue` | `POST /api/v1/attendance/corrections`, `PATCH .../approve`, `PATCH .../reject` | Complete | Employee request flow, pending-state guard, manager comparison cards, approval, and reasoned rejection |
| **Attendance** | Batch Engine Trigger | Attendance Tool | `components/attendance/AttendanceProcessModal.vue` | `POST /api/v1/attendance/process` | Planned | Admin dialog to trigger automated attendance calculations for date ranges |
| **Leaves** | Leave Types & Periods | Leave Type & Period | `pages/leaves/types.vue` | `GET/POST /api/v1/leaves/types`, `GET /api/v1/leaves/periods` | Complete | Setup table & configuration modals for types and periods |
| **Leaves** | Quota Allocation | Leave Allocation | `pages/leaves/allocations.vue`, `LeaveAllocationModal.vue` | `GET/POST /api/v1/leaves/allocations` | Complete | Allocation modal linked to double-entry ledger with history table |
| **Leaves** | Application & Balances | Leave Application | `pages/leaves/index.vue` | `GET /api/v1/leaves/`, `POST /api/v1/leaves/`, `GET /balance/employee/{id}` | Complete | Responsive balance cards, desktop history table, mobile request cards, projected balance, half-day requests, and cancellation |
| **Leaves** | Leave Approval Queue | Leave Approval | `pages/approvals/index.vue` | `PATCH /api/v1/leaves/{id}/approve`, `PATCH .../reject` | Complete | Permission-aware unified queue with responsive review cards, employee context, one-click approval, and reasoned rejection |
| **Shifts** | Shift Types & Night Shifts| Shift Type | `pages/shifts/index.vue`, `ShiftFormModal.vue` | `GET/POST /api/v1/shifts/`, `PATCH .../{id}` | Complete | 24h & overnight shift config with timing tags and auto-midnight detector |
| **Shifts** | Shift Assignments | Shift Assignment | `pages/shifts/assignments.vue`, `ShiftAssignmentModal.vue`, `BulkShiftAssignmentModal.vue` | `GET/POST /api/v1/shifts/assignments`, `PATCH .../cancel` | Complete | Individual & bulk department/unit assignment dialogues with roster table |
| **Shifts** | Shift Schedule / Roster | Shift Schedule | `pages/shifts/schedule.vue` | `GET /api/v1/shifts/employee/{id}/schedule` | Complete | Visual timeline inspection of allowed punch-in/out windows and night shifts |
| **Work Arrangements**| WFH / Out-Duty / Field | Remote Work | `pages/work-arrangements/index.vue` | `GET/POST/PATCH /api/v1/work-arrangements/` | Complete | Responsive type chooser, date/location/contact fields, history filters, status feedback, and cancellation |
| **Work Arrangements**| Work Arrangement Approval | Remote Work Approval| `pages/approvals/index.vue` | `PATCH /api/v1/work-arrangements/{id}/approve`, `PATCH .../reject` | Complete | Unified responsive manager queue with request context, approval, and reasoned rejection |
| **Overtime** | Personal Overtime | Overtime Detail | `pages/overtime/index.vue` | `GET /api/v1/overtime/`, `GET /employee/{id}/summary` | Complete | Responsive monthly totals, status filters, and desktop/mobile record history |
| **Notifications** | Notification Center | Notification Log | `pages/notifications.vue` | `GET /api/v1/notifications`, `PATCH .../read`, `POST .../mark-all-read` | Complete | Unread filtering, deep links, individual read state, and mark-all-read action |
| **Holidays** | Holiday Lists & Weekly Off | Holiday List | `pages/holidays/index.vue` | `GET/POST /api/v1/holidays/lists` | Planned | Holiday calendar with auto weekly-off generator |
| **Reports** | Attendance Matrix | Monthly Attendance Sheet| `pages/reports/attendance-matrix.vue` | `GET /api/v1/reports/attendance-matrix` | Planned | Horizontal scrollable grid with status color coding |
| **Reports** | Leave Summary Report | Employee Leave Balance | `pages/reports/leave-summary.vue` | `GET /api/v1/reports/leave-summary` | Planned | Tabular breakdown of opening, accrued, taken, balance |

---

## 2. Legend
- **Complete**: Implemented, tested, and passing integration and type checks.
- **In Review**: Working prototype present, undergoing architectural refactor / modernization.
- **Planned**: Architected, schemas verified against FastAPI endpoints, ready for implementation upon approval.

---

## 3. Implementation Progress by Phase

| Phase | Module / Focus | Status | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Foundation & Architecture | **Complete** | Central `useApi.ts` client, 8 TypeScript schemas matching FastAPI models, App shell in `layouts/default.vue`, UI primitives (`StatusBadge`, `EmptyState`, `ConfirmDialog`). |
| **Phase 2** | Organization & Employees | **Complete** | Designations master CRUD, Units & Departments tree in `pages/org.vue`, Employee directory in `pages/employees/index.vue`, multi-section onboarding in `create.vue`, 360° profile in `[id].vue`. |
| **Phase 3** | Attendance & Punching | **In Review** | Employee GPS punch, monthly calendar/summary, responsive records, correction submission, and manager correction approvals are implemented. Backend reads, punches, corrections, approvals, and batch runs now enforce self/role scope. Raw-punch administration and batch processing UI remain. |
| **Phase 4** | Leave Management | **In Review** | Employee balances, requests, allocations, cancellation, and manager actions now enforce self/role scope. Administration masters UI remains. |
| **Phase 5** | Shifts & Night Shifts | **Complete** | Shift config modal with auto-midnight detection in `ShiftFormModal.vue`, individual assignment in `ShiftAssignmentModal.vue`, bulk assignment in `BulkShiftAssignmentModal.vue`, definitions table in `pages/shifts/index.vue`, roster in `assignments.vue`, timeline inspector in `schedule.vue`. |
| **Phase 6** | Unified Approvals & Work Arrangements | In Review | Employee work-arrangement requests plus attendance, leave, and work-arrangement approval queues are implemented responsively. Work-arrangement APIs now enforce self/role scope, use dedicated permissions, and return employee identity. Overtime review remains. |
| **Phase 7** | Holidays & Reports | Planned | Yearly holiday calendars, auto weekly-off generator, monthly attendance matrix grid, and leave ledger balance summary. |
| **Phase 8** | Polish & E2E Validation | Planned | Responsive fine-tuning, keyboard shortcuts, PWA offline sync verification, performance audit. |
