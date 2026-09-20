# Frappe HR Functional Analysis & FastAPI Backend Architecture

## Executive Summary

This document provides a comprehensive technical analysis comparing the **Frappe HR** reference implementation (`hrms-16.18.1`) with our **FastAPI + PostgreSQL backend** in `apps/api`. It establishes the functional mapping, business logic rules, entity models, and recommended architecture for implementing an enterprise-grade HRMS backend tailored to multi-unit manufacturing organizations (such as Bajaj Sons).

---

## 1. Existing FastAPI Architecture Summary (`apps/api`)

### Current Technology Stack
- **Framework**: FastAPI (asyncio, Python 3.12+)
- **ORM**: SQLAlchemy 2.0 (async with `asyncpg` driver for PostgreSQL)
- **Migrations**: Alembic (`alembic/versions`)
- **Authentication**: FastAPI Users (JWT Bearer tokens, secure password hashing, invitation workflows, zxcvbn password validation)
- **Authorization**: Scoped Dynamic RBAC (`UserRoleAssignment` with `scope_type: organization | unit | department` and `scope_id`)
- **Validation**: Pydantic v2 schemas
- **Email & Background Tasks**: Async email notifications via SMTP (Zoho Mail), background notification cleanup loop

### Current Directory Structure
```text
apps/api/
├── alembic/              # Database migration versions
├── core/
│   ├── auth.py           # FastAPI Users setup, JWT backend, password validators
│   ├── database.py       # Async SQLAlchemy engine & session maker
│   ├── email.py          # SMTP email delivery
│   ├── pagination.py     # Generic pagination helpers
│   ├── rbac.py           # Permission checking, scope validation, widget registry
│   └── settings.py       # Pydantic BaseSettings (.env loading)
├── db/
│   ├── models.py         # SQLAlchemy ORM models (DeclarativeBase)
│   └── seed.py           # Initial role definitions, system permissions, seed admin
├── routers/              # FastAPI route controllers
│   ├── attendance.py     # Attendance listing, calendar, summary, corrections
│   ├── employees.py      # Employee listing, create, update, deactivate
│   ├── leaves.py         # Leave types, balances, applications, approve/reject/cancel
│   ├── org.py            # Organization, Unit, Department CRUD
│   ├── overtime.py       # Overtime records & approvals
│   ├── shifts.py         # Shifts and shift assignments
│   ├── roles.py          # Roles & permissions administration
│   └── users.py          # User management & profile
├── schemas/              # Pydantic request/response models
└── utils/                # Notification cleanup, number conversion
```

### Architectural Gaps & Limitations
1. **Lack of Service Layer**: Business logic currently resides directly inside route functions in `routers/`. Routes handle database transactions, status mutations, and validation in-line.
2. **Missing Ingestion & Processing Engine**:
   - `attendance_punches` table exists, but there is no service to process raw check-ins into `attendance_records`.
   - No shift window matching (early arrival grace, late exit grace).
   - No support for night shifts spanning across midnight (e.g., 22:00 to 06:00).
   - No automatic computation of total worked hours, half-day, late arrival, or early exit flags based on shift thresholds.
3. **Rudimentary Leave Balances**:
   - `leave_balances` is a flat counter table (`allocated`, `used`, `pending`) tied only to a year integer.
   - Missing effective validity periods (`from_date`, `to_date`), carry-forward rules, earned leave schedules, or immutable leave ledger tracking.
   - Leave applications do not account for holidays or weekly offs falling within leave periods.
4. **Disconnected Employee Profile**:
   - `Employee` table has foreign keys to `User`, `Department`, `Unit`, `Shift`, but lacks core employee profile attributes (personal details, emergency contacts, permanent/current address, designation master link, identity documents).
5. **Missing Dedicated Work Arrangement Module**:
   - No data model or workflow for Work From Home (WFH), Out Duty (OD), or Field Work requests.
6. **Flat Holiday Table**:
   - `holidays` table lacks a grouped `Holiday List` structure and fails to define weekly off schedules or calendar inheritance (Unit/Department/Company level).

---

## 2. Frappe HR Architecture & Module Summary (`hrms-16.18.1`)

Frappe HR is built on top of the Frappe Framework, utilizing DocTypes, controller lifecycle hooks (`validate()`, `before_insert()`, `on_submit()`, `on_cancel()`), and workflow transition states.

### Core Modules Analyzed
1. **Organizational Master**:
   - `Company` (Enterprise root)
   - `Branch` (Operating Unit/Factory)
   - `Department` (Hierarchical tree structure with nested `lft`/`rgt` indices)
   - `Designation` (Standard job title and skills)
   - `Department Approver` (Child table mapping approvers for leaves, shift requests, and expense claims)
2. **Employee Master & Lifecycle**:
   - `Employee`: Master record with code, names, joining date, status, company, branch, department, designation, reports_to, approvers, default shift, holiday list.
   - `Employee Transfer` & `Employee Internal Work History`: Records movement across departments, designations, or units with historical audit logs.
3. **Shift Management**:
   - `Shift Type`: Defines shift hours (`start_time`, `end_time`), cross-midnight flag, pre-shift check-in buffer (`begin_check_in_before_shift_start_time`), post-shift check-out buffer (`allow_check_out_after_shift_end_time`), late entry grace period, early exit grace period, half-day working hours threshold, absent working hours threshold, and auto-attendance toggle.
   - `Shift Assignment`: Assigns employee to shift between `start_date` and `end_date`. Enforces non-overlapping active assignments.
   - `Shift Request`: Employee self-service request to change or assign shift, requiring approval.
4. **Attendance & Biometrics**:
   - `Employee Checkin`: High-throughput punch table storing raw device punches (`time`, `log_type` IN/OUT, `device_id`, `skip_auto_attendance`, `shift`, resolved `shift_start`, `shift_end`).
   - `Attendance`: Master daily record (`employee`, `attendance_date`, `status` [Present, Absent, Half Day, On Leave, Work From Home], `working_hours`, `in_time`, `out_time`, `late_entry`, `early_exit`, `shift`, linked request references).
   - `Attendance Request`: Workflow for applying for missing punch regularization, out-duty, or WFH.
   - **Auto-Attendance Engine**: Grouping check-ins by employee and shift window, calculating actual worked duration, applying thresholds, updating attendance status, and auto-marking un-punched employees as Absent after verifying holidays/leaves.
5. **Leave Management**:
   - `Leave Type`: Configurable parameters (`is_paid`, `is_carry_forward`, `max_continuous_days_allowed`, `include_holidays`, `is_compensatory`, `applicable_after`).
   - `Leave Period`: Calendar/Financial year boundary (`from_date`, `to_date`).
   - `Leave Allocation`: Credits leave balance to employee with carry-forward calculation.
   - `Leave Ledger Entry`: Immutable ledger tracking every credit (allocation) and debit (application, encashment, expiration). Leave balance is derived dynamically from ledger sums.
   - `Leave Application`: Application submitted by employee, validated against ledger balance and date overlaps. Upon approval (`on_submit`), auto-creates `Attendance` with status "On Leave" and writes debit ledger entry. Cancellation reverses ledger and cancels attendance.
6. **Holiday Management**:
   - `Holiday List`: Master calendar containing year boundaries and weekly off day (e.g. Sunday).
   - `Holiday`: Child items with `holiday_date`, `description`, `weekly_off` boolean.
   - Resolution order: Employee Holiday List Assignment -> Employee Master -> Department -> Company.

---

## 3. Feature Comparison Table

| Feature Area | Frappe HR Implementation (`hrms-16.18.1`) | Current `apps/api` Implementation | Target FastAPI Implementation |
|---|---|---|---|
| **Organization Structure** | Company -> Branch -> Department (Tree) | Organization -> Unit -> Department (Flat) | Organization -> Unit -> Department + Designation Master |
| **Employee Profile** | Full HR master with personal, employment, salary, and approvers | Minimal fields linked to User; personal info stored on User | Normalized Employee Profile + Employment Details + Manager Hierarchy |
| **Designation Master** | `Designation` DocType | Free-text string on Employee | Dedicated `Designation` table with code, name, description |
| **Holiday Calendar** | `Holiday List` with child `Holiday` entries + weekly off generator | Flat `holidays` table with boolean `is_organization_wide` | `HolidayList` + `Holiday` table with `is_weekly_off`, assigned to Unit/Org/Employee |
| **Shift Definition** | `Shift Type` with start/end time, buffers, grace periods, thresholds | `Shift` table with start/end time, grace, break, cross_midnight | Rich `ShiftType` with pre/post margins, late/early grace, half-day/absent hours |
| **Shift Assignment** | `Shift Assignment` with start/end date, overlap validation | `ShiftAssignment` with effective_from/to; minimal validation | `ShiftAssignment` with strict overlap detection & midnight shift awareness |
| **Biometric Punches** | `Employee Checkin` with auto shift matching & duplicate prevention | `AttendancePunch` table (IN/OUT, device_id, source) | `EmployeeCheckin` / `AttendancePunch` with automatic shift resolution & deduplication |
| **Attendance Processing** | Automated batch processor grouping check-ins by shift window | No automated engine; manual punches or corrections only | `AttendanceProcessingService` calculating worked hours, late/early flags, half-day/absent |
| **Night Shift Support** | Built-in window calculation across day boundary (22:00 -> 06:00) | Boolean column `is_cross_midnight`, but no calculation logic | Timestamp window matcher combining date offsets for night shifts |
| **Leave Types** | Dynamic master with rules (paid, carry forward, include holidays) | `LeaveType` table with basic flags | Configurable `LeaveType` with holiday inclusion and carry-forward rules |
| **Leave Allocation** | `Leave Allocation` per period with carry forward & ledger entries | `LeaveBalance` table (allocated/used/pending per year) | `LeaveAllocation` with effective validity dates + carry-forward logic |
| **Leave Transactions** | `Leave Ledger Entry` (immutable ledger of credits/debits) | Direct mutable integer updates on `LeaveBalance` | Immutable ledger / audit trail ensuring zero drift in balance calculation |
| **Leave Application** | Workflow with overlap check, balance check, holiday exclusion | Basic router checking integer balance and date range | `LeaveApplicationService` validating balance, overlaps, holidays, updating attendance |
| **Attendance Linking** | Approved leave auto-marks `Attendance` as "On Leave" | No integration between leave and attendance | Approval automatically writes/updates `AttendanceRecord` |
| **Work Arrangement** | Handled via `Attendance Request` (reason: WFH, On Duty) | Not implemented | Dedicated `WorkArrangementRequest` (Office, WFH, Out Duty, Field Work) |
| **Attendance Regularization**| `Attendance Request` with approval workflow | `AttendanceCorrectionRequest` with simple approve/reject | Reusable workflow with audit trail and punch adjustments |
| **Architecture Pattern** | DocType controllers with database hooks | Routers directly invoking SQLAlchemy sessions | Router -> Service -> Repository -> Database |

---

## 4. Database & Entity Mapping

```
+---------------------------------------------------------------------------------------------------+
|                                      ORGANIZATION HIERARCHY                                       |
+---------------------------------------------------------------------------------------------------+
| Frappe HR                          | FastAPI / PostgreSQL (`apps/api`)                            |
+------------------------------------+--------------------------------------------------------------+
| Company                            | organizations (id, name, code, domain, currency)             |
| Branch                             | units (id, organization_id, name, code, city, address)       |
| Department                         | departments (id, unit_id, parent_id, name, code)             |
| Designation                        | designations (id, name, code, description)                   |
| Department Approver                | department_approvers (id, department_id, approver_type, ...)  |
+------------------------------------+--------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
|                                       EMPLOYEE MANAGEMENT                                         |
+---------------------------------------------------------------------------------------------------+
| Frappe HR                          | FastAPI / PostgreSQL (`apps/api`)                            |
+------------------------------------+--------------------------------------------------------------+
| Employee                           | employees (id, user_id, employee_code, first_name,           |
|                                    |   last_name, email, mobile_number, department_id, unit_id,    |
|                                    |   designation_id, reporting_manager_id, date_of_joining,     |
|                                    |   date_of_birth, gender, employment_type, status, ...)       |
| Employee Internal Work History     | employee_work_histories (id, employee_id, change_type, ...)  |
+------------------------------------+--------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
|                                    SHIFTS & HOLIDAY MANAGEMENT                                    |
+---------------------------------------------------------------------------------------------------+
| Frappe HR                          | FastAPI / PostgreSQL (`apps/api`)                            |
+------------------------------------+--------------------------------------------------------------+
| Shift Type                         | shift_types (id, unit_id, name, code, start_time, end_time,   |
|                                    |   begin_check_in_before_minutes, allow_check_out_after_min,  |
|                                    |   late_entry_grace_minutes, early_exit_grace_minutes,        |
|                                    |   half_day_threshold_hours, absent_threshold_hours, ...)     |
| Shift Assignment                   | shift_assignments (id, employee_id, shift_type_id,           |
|                                    |   start_date, end_date, status, assigned_by)                 |
| Shift Request                      | shift_requests (id, employee_id, shift_type_id, from_date,   |
|                                    |   to_date, status, approver_id, reason)                      |
| Holiday List                       | holiday_lists (id, unit_id, name, from_date, to_date,        |
|                                    |   weekly_off_day, is_default)                                |
| Holiday                            | holidays (id, holiday_list_id, holiday_date, description,     |
|                                    |   is_weekly_off)                                             |
+------------------------------------+--------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
|                                    ATTENDANCE & CHECK-INS                                         |
+---------------------------------------------------------------------------------------------------+
| Frappe HR                          | FastAPI / PostgreSQL (`apps/api`)                            |
+------------------------------------+--------------------------------------------------------------+
| Employee Checkin                   | employee_checkins (id, employee_id, timestamp, log_type,     |
|                                    |   device_id, source, latitude, longitude, shift_type_id,     |
|                                    |   shift_start, shift_end, attendance_id, is_processed)       |
| Attendance                         | attendance_records (id, employee_id, attendance_date,        |
|                                    |   shift_type_id, status, punch_in, punch_out, worked_minutes,|
|                                    |   overtime_minutes, late_minutes, early_exit_minutes,        |
|                                    |   is_late, is_early_exit, leave_application_id, ...)         |
| Attendance Request                 | attendance_requests (id, employee_id, from_date, to_date,    |
|                                    |   reason, half_day, half_day_date, explanation, status, ...)  |
| -                                  | attendance_corrections (id, attendance_record_id,            |
|                                    |   requested_in, requested_out, reason, status, approver_id)  |
+------------------------------------+--------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
|                                       LEAVE MANAGEMENT                                            |
+---------------------------------------------------------------------------------------------------+
| Frappe HR                          | FastAPI / PostgreSQL (`apps/api`)                            |
+------------------------------------+--------------------------------------------------------------+
| Leave Type                         | leave_types (id, name, code, is_paid, is_carry_forward,      |
|                                    |   max_consecutive_days, include_holidays, is_compensatory)   |
| Leave Period                       | leave_periods (id, organization_id, name, from_date, to_date)|
| Leave Allocation                   | leave_allocations (id, employee_id, leave_type_id,           |
|                                    |   leave_period_id, from_date, to_date, total_allocated,     |
|                                    |   new_allocated, carry_forwarded)                            |
| Leave Ledger Entry                 | leave_ledger_entries (id, employee_id, leave_type_id,        |
|                                    |   transaction_type, transaction_date, leaves, reference_type,|
|                                    |   reference_id, from_date, to_date)                          |
| Leave Application                  | leave_applications (id, employee_id, leave_type_id,          |
|                                    |   from_date, to_date, half_day, half_day_date,               |
|                                    |   total_leave_days, reason, status, approver_id, ...)        |
+------------------------------------+--------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
|                                       WORK ARRANGEMENT                                            |
+---------------------------------------------------------------------------------------------------+
| Frappe HR                          | FastAPI / PostgreSQL (`apps/api`)                            |
+------------------------------------+--------------------------------------------------------------+
| Attendance Request (WFH / On Duty) | work_arrangement_requests (id, employee_id, arrangement_type,|
|                                    |   from_date, to_date, reason, destination_or_location,       |
|                                    |   contact_phone, status, approver_id, actioned_at, comments) |
+------------------------------------+--------------------------------------------------------------+
```

---

## 5. Detailed Business Logic & Rules Mapping

### 5.1 Leave Management Rules
1. **Leave Day Calculation**:
   - `base_days = (to_date - from_date).days + 1` (minus 0.5 if `half_day == True`).
   - If `leave_type.include_holidays == False`: Exclude holidays and weekly offs identified in the employee's active `HolidayList`.
2. **Balance Validation**:
   - Compute available balance: `allocated_leaves - approved_used_leaves - pending_requested_leaves`.
   - Prevent application if `available_balance < requested_days` (unless leave type is marked as Loss of Pay / LWP).
3. **Overlap Validation**:
   - Disallow submission if any date in `[from_date, to_date]` overlaps with existing non-rejected leave applications or approved attendance records.
4. **Consecutive Days Limit**:
   - If `leave_type.max_consecutive_days > 0`, reject applications where `total_leave_days > max_consecutive_days`.
5. **Approval Effect on Attendance**:
   - When approved, automatically create or update `AttendanceRecord` for each covered working date with `status = "ON_LEAVE"` (or `"HALF_DAY"`).
6. **Cancellation / Rejection**:
   - Upon cancellation, restore balance in the ledger and cancel or delete the linked `AttendanceRecord`.

### 5.2 Shift & Night Shift Rules
1. **Shift Windows**:
   - A shift defined by `start_time` and `end_time` has an active punch window:
     - `actual_start = start_time - begin_check_in_before_minutes`
     - `actual_end = end_time + allow_check_out_after_minutes`
2. **Cross-Midnight Shifts (Night Shifts)**:
   - If `start_time > end_time` (e.g. 22:00 -> 06:00):
     - `start_datetime = Date(D) + 22:00`
     - `end_datetime = Date(D + 1) + 06:00`
     - `actual_start = Date(D) + (22:00 - buffer)`
     - `actual_end = Date(D + 1) + (06:00 + buffer)`
   - All check-ins occurring between `actual_start` and `actual_end` belong to the shift on `Date(D)`.
3. **Overlapping Shift Assignments**:
   - An employee can have at most one active shift assignment for any given date unless explicitly configured otherwise.

### 5.3 Attendance Processing Engine
1. **Punch Ingestion**:
   - Ingest punches via API or biometric devices (`employee_checkins`).
   - Associate each punch with the active shift matching `actual_start <= punch.timestamp <= actual_end`.
2. **Daily Aggregation**:
   - For a single shift window:
     - `in_time` = earliest check-in punch in window
     - `out_time` = latest check-out punch in window
     - `worked_minutes` = difference between in and out punches (minus lunch break if applicable)
3. **Threshold Evaluations**:
   - **Late Entry**: `in_time > (shift_start + late_entry_grace_minutes)` -> set `is_late = True`, calculate `late_minutes`.
   - **Early Exit**: `out_time < (shift_end - early_exit_grace_minutes)` -> set `is_early_exit = True`, calculate `early_exit_minutes`.
   - **Status Determination**:
     - `worked_hours < absent_threshold_hours` -> Status: **`ABSENT`**
     - `worked_hours < half_day_threshold_hours` -> Status: **`HALF_DAY`**
     - Otherwise -> Status: **`PRESENT`**
4. **Auto-Absent for Missing Records**:
   - Scheduled job marks employees as **`ABSENT`** on days where no check-ins exist, **unless** the day is a Holiday, Weekly Off, or covered by an Approved Leave or Work Arrangement.

### 5.4 Work Arrangement Module Rules
1. **Types Supported**: `OFFICE`, `WORK_FROM_HOME` (WFH), `OUT_DUTY` (OD), `FIELD_WORK`.
2. **Workflow**:
   - Employee drafts and submits request with date range, arrangement type, and reason.
   - Status: `PENDING` -> Assigned to Reporting Manager / Department Head.
   - Manager reviews -> `APPROVED` or `REJECTED`.
3. **Attendance Impact**:
   - When approved:
     - For `WORK_FROM_HOME`: Attendance status set to `WORK_FROM_HOME` (treated as present for payroll/worked day calculations).
     - For `OUT_DUTY` / `FIELD_WORK`: Attendance status set to `PRESENT` with note referencing the approved request, overriding missed punch / absent flags.

### 5.5 Approvals & Permissions
1. **Standard Workflow Statuses**: `DRAFT`, `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`.
2. **Self-Approval Prevention**: An approver cannot approve their own leave, shift, attendance, or work arrangement requests.
3. **Hierarchy-Based Routing**:
   - Level 1: Reporting Manager
   - Level 2: Department Head / Unit HR
4. **Scoped RBAC Access**:
   - `EMPLOYEE`: Access self-records only.
   - `DEPARTMENT_HEAD`: Access and approve records for employees within their department.
   - `HR_MANAGER` / `UNIT_HEAD`: Access and approve records for all employees within their unit.
   - `HR_OWNER` / `SUPER_ADMIN`: Cross-unit enterprise access.

---

## 6. Recommended FastAPI Architecture

To ensure high maintainability, testability, and separation of concerns, we adopt the standard **Controller-Service-Repository** pattern:

```text
Request
  │
  ▼
Router (FastAPI endpoint, Pydantic validation, Auth & RBAC dependencies)
  │
  ▼
Service Layer (Business rules, validations, calculations, workflows)
  │
  ▼
Repository Layer (SQLAlchemy queries, data persistence, transactions)
  │
  ▼
Database (PostgreSQL)
```

### Proposed Directory Layout in `apps/api`
```text
apps/api/
├── core/
│   ├── auth.py
│   ├── database.py
│   ├── rbac.py
│   └── settings.py
├── db/
│   ├── models/                # Modular ORM definitions
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── org.py             # Organization, Unit, Department, Designation
│   │   ├── employees.py       # Employee, WorkHistory
│   │   ├── shifts.py          # ShiftType, ShiftAssignment, ShiftRequest
│   │   ├── holidays.py        # HolidayList, Holiday
│   │   ├── attendance.py      # EmployeeCheckin, AttendanceRecord, Correction
│   │   ├── leaves.py          # LeaveType, LeavePeriod, LeaveAllocation, LeaveApplication, LeaveLedger
│   │   └── work_arrangements.py # WorkArrangementRequest
│   └── seed.py
├── repositories/              # Database persistence abstraction
│   ├── employee_repo.py
│   ├── shift_repo.py
│   ├── holiday_repo.py
│   ├── attendance_repo.py
│   ├── leave_repo.py
│   └── work_arrangement_repo.py
├── services/                  # Pure domain logic & business rules
│   ├── employee_service.py
│   ├── shift_service.py
│   ├── holiday_service.py
│   ├── attendance_service.py  # Punch processing & threshold evaluations
│   ├── leave_service.py       # Balance calculations, holiday exclusion, ledger
│   └── work_arrangement_service.py
├── routers/                   # HTTP endpoints
│   ├── org.py
│   ├── employees.py
│   ├── shifts.py
│   ├── holidays.py
│   ├── attendance.py
│   ├── leaves.py
│   └── work_arrangements.py
├── schemas/                   # Pydantic v2 schemas
│   ├── org.py
│   ├── employees.py
│   ├── shifts.py
│   ├── holidays.py
│   ├── attendance.py
│   ├── leaves.py
│   └── work_arrangements.py
└── tests/                     # Unit and integration test suites
```

---

## 7. Implementation Milestones

### Milestone 1: Organizational Foundation & Employee Master
- Create `Designation` master model and router.
- Expand `Employee` model with personal, demographic, contact, and employment fields.
- Implement Department Approvers (`department_approvers`) mapping.
- Wire `EmployeeService` and `EmployeeRepository`.

### Milestone 2: Shifts, Shift Assignments, Holiday Lists & Employee Check-ins
- Upgrade `Shift` into rich `ShiftType` with pre/post margins, late/early grace periods, and half-day/absent hour thresholds.
- Implement `ShiftAssignment` with non-overlapping date validations.
- Implement `HolidayList` and `Holiday` models (with weekly off generator and resolution hierarchy).
- Implement raw punch ingestion (`employee_checkins`) with automatic shift window matching.

### Milestone 3: Attendance Processing Engine & Corrections
- Implement `AttendanceProcessingService` to process check-ins into daily `AttendanceRecord`s.
- Implement night shift cross-midnight aggregation.
- Implement late entry, early exit, half-day, absent, and missed punch calculations.
- Implement `AttendanceCorrectionRequest` and `AttendanceRequest` regularization flows.
- Monthly attendance summary and calendar view APIs.

### Milestone 4: Leave Management & Ledger System
- Implement `LeaveType` with configurable rules (`is_paid`, `is_carry_forward`, `include_holidays`).
- Implement `LeavePeriod` and `LeaveAllocation`.
- Implement `LeaveLedgerEntry` transactions.
- Implement `LeaveApplicationService` with date validation, balance check, holiday exclusion, and automatic attendance record updating on approval.

### Milestone 5: Dedicated Work Arrangement Module
- Implement `WorkArrangementRequest` model (Office, WFH, Out Duty, Field Work).
- Create workflow endpoints (`apply`, `approve`, `reject`, `cancel`).
- Integrate approval hook with attendance engine (`AttendanceRecord.status = WORK_FROM_HOME` or `PRESENT`).

### Milestone 6: Reports, Background Schedulers & Integration Verification
- Automated background task for end-of-day attendance processing.
- Monthly attendance summaries, overtime summaries, and leave balance reports.
- Comprehensive pytest test suite for all business rules.

---

## 8. Files to Be Created / Modified

### Existing Files to Modify:
- `apps/api/db/models.py` (expand models or transition to modular `db/models/`)
- `apps/api/core/rbac.py` (add new permission codes for work arrangements and designations)
- `apps/api/db/seed.py` (seed new permissions, roles, and default leave types)
- `apps/api/routers/employees.py` (delegate to `EmployeeService`)
- `apps/api/routers/shifts.py` (delegate to `ShiftService`)
- `apps/api/routers/attendance.py` (integrate check-in processing & summary engine)
- `apps/api/routers/leaves.py` (integrate ledger & holiday-aware calculations)
- `apps/api/schemas/*` (update and expand request/response models)
- `apps/api/main.py` (register new routers and background tasks)

### New Files to Create:
- `apps/api/services/attendance_service.py`
- `apps/api/services/shift_service.py`
- `apps/api/services/leave_service.py`
- `apps/api/services/holiday_service.py`
- `apps/api/services/work_arrangement_service.py`
- `apps/api/services/employee_service.py`
- `apps/api/repositories/attendance_repo.py`
- `apps/api/repositories/leave_repo.py`
- `apps/api/repositories/shift_repo.py`
- `apps/api/repositories/employee_repo.py`
- `apps/api/routers/work_arrangements.py`
- `apps/api/routers/holidays.py`
- `apps/api/schemas/work_arrangements.py`
- `apps/api/schemas/holidays.py`
- `apps/api/alembic/versions/<timestamp>_full_hrms_features.py`

---

## 9. Conflicts Between Existing `apps` and Frappe HR

1. **User Identity vs. Employee Identity**:
   - In `apps/api`, authentication details (email, first_name, last_name, mobile_number) belong to `users`. `Employee` is an optional secondary record linked by `user_id`.
   - In Frappe HR, `Employee` is the primary master with full names and contact info, optionally linked to a `User`.
   - *Resolution*: Keep `User` for portal authentication, but replicate core employee identity fields (`first_name`, `last_name`, `official_email`, `mobile_number`) on `Employee` so non-user factory employees can exist without requiring portal login accounts.
2. **Attendance Statuses**:
   - In `apps/api`: `PRESENT`, `ABSENT`, `ON_LEAVE`, `HOLIDAY`, `WEEKLY_OFF`, `HALF_DAY`, `LATE`, `MISSED_PUNCH`, `ATTENDANCE_PENDING`.
   - In Frappe HR: Status is `Present`, `Absent`, `Half Day`, `On Leave`, `Work From Home`. `Late Entry` and `Early Exit` are separate boolean indicators rather than standalone mutually exclusive statuses.
   - *Resolution*: Adopt Frappe's clean separation: primary status is `PRESENT`, `ABSENT`, `HALF_DAY`, `ON_LEAVE`, `WORK_FROM_HOME`, `HOLIDAY`, `WEEKLY_OFF`, while `is_late`, `is_early_exit`, and `missed_punch` are boolean flags accompanied by minute counters.
3. **Leave Balance Model**:
   - In `apps/api`: Mutable table `leave_balances` directly edited.
   - In Frappe HR: Dynamic calculation via `Leave Ledger Entry` or snapshot ledger balance.
   - *Resolution*: Maintain `LeaveAllocation` and `LeaveLedgerEntry` so historical adjustments, carry-forward, and cancellations have a 100% auditable trail.

---

## 10. Questions & Decisions for Approval

1. **Biometric Punch Source**: Will biometric machines push records to our FastAPI backend via `POST /api/v1/attendance/punches` or `POST /api/v1/checkins`, or will an external daemon query the machine DB and post to our API?
2. **Shift Assignment Granularity**: In manufacturing factories, shift assignments are often generated by rotating rosters or weekly patterns. Should we support bulk shift assignments by Unit/Department in Milestone 2?
3. **Self-Service Portal Accounts**: Should creating an `Employee` automatically invite/create a corresponding `User` account with role `EMPLOYEE`, or should user accounts be created on demand?
