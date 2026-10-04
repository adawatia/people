# FastAPI HRMS Backend Feature Reference & Architecture Guide

A complete technical manual and feature catalog of the **FastAPI HRMS Backend** (`apps/api`). This backend is built using **Python 3.14 / FastAPI / SQLAlchemy 2.0 (Async) / PostgreSQL / Pydantic v2 / FastAPI-Users**, designed to provide 100% functional parity with the core workflows of **Frappe HR 16.18.1**.

---

## 1. System & Core Infrastructure

The foundation of the backend is designed for high reliability, async non-blocking execution, structured observability, and strict separation of concerns.

### Architecture Layering
```
HTTP Request 
    │
    ▼
FastAPI Routers (`apps/api/routers/`)
    │ (Validates HTTP params & Pydantic Request Models)
    ▼
Service Layer (`apps/api/services/`)
    │ (Business logic, state machines, workflow rules, permissions checks)
    ▼
Repository Layer (`apps/api/repositories/`)
    │ (Encapsulated SQLAlchemy 2.0 select/insert/update/delete operations)
    ▼
Database Models (`apps/api/db/models.py`) ──▶ PostgreSQL
```

- **Asynchronous Database Engine**: Built on `SQLAlchemy 2.0` with `asyncpg` / `psycopg3` async driver. Supports selector loop policies across Linux and Windows (`asyncio.WindowsSelectorEventLoopPolicy` / `SelectorEventLoop`).
- **Lifespan Startup & Seed Engine**: Automatic table reflection/creation and idempotent seeding of baseline roles (`SUPER_ADMIN`, `HR_ADMIN`, `EMPLOYEE`), permissions, and initial admin account on application boot.
- **Request/Response JSON Logging Middleware**: Formats all incoming HTTP requests into machine-readable JSON logs with response codes, processing latency in milliseconds, client IP, and User-Agent.
- **Rate Limiting**: Integrated `slowapi` limiter protecting sensitive endpoints (e.g. health checks, auth routes).
- **CORS Middleware**: Flexible environment-based origin whitelisting (`CORS_ORIGINS`).
- **System Health Diagnostics**:
  - `GET /`: Basic API status ping.
  - `GET /health`: Comprehensive health monitor reporting database latency, service uptime, timestamp, and connection state.
  - `GET /db-health`: Dedicated database connectivity probe for Kubernetes/Docker container health checks.
- **Asynchronous Background Tasks**:
  - Notification garbage collection loop running continuously in the background to purge notifications older than 30 days.

---

## 2. Authentication, Invitation & Password Management

Identity management is handled by `fastapi-users` combined with custom invitation and password complexity workflows.

### Endpoints (`/api/v1/auth`)

| Endpoint | Method | Purpose |
| :--- | :---: | :--- |
| `/auth/jwt/login` | `POST` | Authenticates username/password and issues a secure JWT bearer token. |
| `/auth/jwt/logout` | `POST` | Invalidates active user session token. |
| `/auth/forgot-password` | `POST` | Initiates password recovery email with secure reset token. |
| `/auth/reset-password` | `POST` | Consumes reset token and applies a new password. |
| `/auth/request-verify-token` | `POST` | Dispatches account verification email token. |
| `/auth/verify` | `POST` | Verifies user email address. |
| `/auth/invitation/validate` | `GET` | Validates an administrative onboarding token for new employee signups. |
| `/auth/invitation/set-password` | `POST` | Activates invited account, validates password strength, and sets credentials. |

### Key Features
- **Public Registration Disabled**: All user accounts are provisioned by authorized administrators (`user.create` permission).
- **Admin-Invited Onboarding**: When an employee is created, an invitation token is generated, and an invitation email is queued asynchronously via `EmailService`.
- **Password Policy Engine**: Enforces a minimum of 8 characters, rejects compromised and personal-information-based values, and requires a `zxcvbn` strength score $\ge 3$ without composition rules.

---

## 3. Dynamic Scoped RBAC & Role Management

Dynamic Role-Based Access Control decouples roles from hardcoded permissions, supporting organization-, unit-, and department-scoped privileges.

### Endpoints (`/api/v1/roles`, `/api/v1/users`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/roles/permissions` | `GET` | `role.view` | Retrieves all registered system permissions across HR domains. |
| `/roles/` | `GET` | `role.view` | Lists all defined roles with their attached permission codes. |
| `/roles/` | `POST` | `role.create` | Creates a custom role with arbitrary permission bundles. |
| `/roles/{role_id}` | `PATCH` | `role.update` | Modifies role details and updates assigned permission codes. |
| `/roles/{role_id}` | `DELETE` | `role.delete` | Deletes a custom role (blocks if currently assigned to users). |
| `/users/{id}/assignments` | `GET` | `user.view` | Lists scoped role assignments for a given user. |
| `/users/{id}/assignments` | `POST` | `role.assign` | Assigns a role with optional scope (`GLOBAL`, `UNIT`, `DEPARTMENT`). |
| `/users/{id}/assignments/{aid}` | `DELETE` | `role.assign` | Revokes a specific scoped role assignment. |

### Key Features
- **System Role Protection**: Default system roles (`SUPER_ADMIN`, `HR_ADMIN`, `EMPLOYEE`) cannot be deleted, and only Super Administrators can modify system roles or assign the `SUPER_ADMIN` role.
- **Hierarchical Scope Inheritance**: A permission granted at `UNIT` level cascades to all departments within that unit; a `GLOBAL` scope applies across the entire enterprise.

---

## 4. User Profiles & Employee Linkage

Manages system user accounts and links authentication identities with HR employee records.

### Endpoints (`/api/v1/users`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/users/` | `GET` | `user.view` | Paginated listing with search (name, email, username) and role/status filters. |
| `/users/` | `POST` | `user.create` | Creates a new user profile and triggers optional invitation email. |
| `/users/stats` | `GET` | `user.view` | Aggregates total, active, and inactive user counts. |
| `/users/me` | `GET` | Active User | Returns current user profile, effective permissions, and linked `employee_id` / `employee_code`. |
| `/users/me/permissions` | `GET` | Active User | Returns distinct list of all effective permissions for current session. |
| `/users/{id}/resend-invitation`| `POST` | `user.create` | Re-dispatches onboarding invitation email if token is unconsumed. |

---

## 5. In-App Notification System

Real-time notification engine for alerts, task assignments, and approval updates.

### Endpoints (`/api/v1/notifications`)

| Endpoint | Method | Purpose |
| :--- | :---: | :--- |
| `/notifications` | `GET` | Retrieves recent notifications for current user or user's role. |
| `/notifications/unread-count` | `GET` | Returns count of unread notifications for badge counters. |
| `/notifications/{id}/read` | `PATCH` | Marks a specific notification as read. |
| `/notifications/mark-all-read` | `POST` | Bulk marks all active notifications as read. |

### Key Features
- **Role-Wide Broadcasts**: Notifications can target a specific `user_id`, or broadcast to target roles (`ALL`, `STAFF`, `HR`, `MANAGER`, `EMPLOYEE`).
- **Automated Retention Worker**: Background loop regularly removes read notifications older than 30 days to optimize database performance.

---

## 6. Organization Master Data & Hierarchies (Phase 1)

Encapsulates organizational structures: Organization $\rightarrow$ Units $\rightarrow$ Departments.

### Endpoints (`/api/v1/org`, `/api/v1/designations`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/org/organizations` | `GET` | Active User | Lists enterprise organizations. |
| `/org/units` | `GET` | Active User | Lists operational units/branches with eager-loaded departments. |
| `/org/units/{unit_id}` | `GET` | Active User | Retrieves details of a specific unit. |
| `/org/units` | `POST` | `system.configure`| Creates a new operational unit under an organization. |
| `/org/units/{unit_id}` | `PATCH` | `system.configure`| Updates unit code, name, or address. |
| `/org/departments` | `GET` | Active User | Lists departments, optionally filtered by `unit_id`. |
| `/org/departments/{dept_id}`| `GET` | Active User | Retrieves details of a specific department. |
| `/org/departments` | `POST` | `system.configure`| Creates a department under an existing unit. |
| `/org/departments/{dept_id}`| `PATCH` | `system.configure`| Updates department details. |
| `/designations/` | `GET` | Active User | Lists job designations with active status filter. |
| `/designations/{id}` | `GET` | Active User | Retrieves details of a specific designation. |
| `/designations/` | `POST` | `designation.create`| Creates a new job designation. |
| `/designations/{id}` | `PATCH` | `designation.update`| Updates designation title or description. |
| `/designations/{id}` | `DELETE` | `designation.delete`| Soft-deactivates or deletes designation. |

---

## 7. Employee Master & Lifecycle Management (Phase 2)

Comprehensive employee records with lifecycle state transitions, reporting hierarchies, and position tracking.

### Endpoints (`/api/v1/employees`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/employees/` | `GET` | Active User | Paginated search across employees with unit, department, designation, and status filters. |
| `/employees/` | `POST` | `employee.create` | Onboards employee with auto-generated code, validation, and optional user linking. |
| `/employees/{id}` | `GET` | Active User | Returns enriched employee profile with manager and statutory details. |
| `/employees/{id}` | `PATCH` | `employee.update` | Updates employee profile; records position movement if department/unit changes. |
| `/employees/{id}/deactivate` | `PATCH` | `employee.deactivate` | Formal separation workflow; sets status to `INACTIVE` with `exit_date` and `exit_reason`. |
| `/employees/{id}/activate` | `PATCH` | `employee.update` | Reactivates an employee profile. |
| `/employees/{id}/work-history`| `GET` | Active User | Retrieves timeline of internal movements and title changes. |

### Key Features
- **Circular Reporting Prevention**: Validates manager assignments by walking the hierarchy tree to guarantee zero circular dependency loops.
- **Automatic Work History**: Automatically closes previous positions and logs new entries in `EmployeeWorkHistory` upon designation, unit, or department modifications.

---

## 8. Shift Scheduling & Roster Engine (Phase 3)

Configurable shifts, cross-day overnight shift support, and automated schedule resolution.

### Endpoints (`/api/v1/shifts`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/shifts/` | `GET` | Active User | Lists available shifts filtered by unit and active status. |
| `/shifts/{shift_id}` | `GET` | Active User | Retrieves shift timing rules, break durations, and grace periods. |
| `/shifts/` | `POST` | `shift.assign` | Defines a new shift schedule. |
| `/shifts/{shift_id}` | `PATCH` | `shift.update` | Updates shift times, late tolerance, or overnight flags. |
| `/shifts/assignments` | `GET` | Active User | Lists shift assignments filtered by employee, shift, or date. |
| `/shifts/assignments` | `POST` | `shift.assign` | Assigns an employee to a shift for a date interval. |
| `/shifts/assignments/bulk` | `POST` | `shift.assign` | Bulk assigns shifts across multiple employees simultaneously. |
| `/shifts/assignments/{id}/cancel`| `PATCH`| `shift.assign` | Cancels an active shift assignment. |
| `/shifts/employee/{id}/schedule` | `GET` | Active User | Resolves exact shift schedule for an employee at any given timestamp. |

---

## 9. Holiday Calendar & Weekly-Off Management (Phase 3/4)

Unit-specific and enterprise-wide holiday lists with weekly-off auto-generation.

### Endpoints (`/api/v1/holidays`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/holidays/lists` | `GET` | Active User | Lists holiday calendars filtered by unit. |
| `/holidays/lists/{list_id}` | `GET` | Active User | Retrieves calendar details and complete holiday roster. |
| `/holidays/lists` | `POST` | `system.configure`| Creates holiday list; automatically generates weekly offs (e.g. Sundays). |
| `/holidays/lists/{list_id}/holidays`| `POST`| `system.configure`| Adds ad-hoc national or regional holidays to a list. |

---

## 10. Biometric Attendance Processing & Regularization (Phase 3)

Biometric punch ingestion, daily batch processor, calendar views, and attendance regularization requests.

### Endpoints (`/api/v1/attendance`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/attendance/checkins` | `GET` | Active User | Queries raw punch logs with employee, time, and processed filters. |
| `/attendance/` | `GET` | Active User | Lists consolidated attendance records with pagination and status filters. |
| `/attendance/records/{id}` | `GET` | Active User | Retrieves a specific attendance record. |
| `/attendance/employee/{id}/calendar`| `GET`| Active User | Returns day-by-day month records for visual calendar views. |
| `/attendance/employee/{id}/summary` | `GET`| Active User | Computes monthly attendance counts (Present, Absent, Leave, Late, OT). |
| `/attendance/process` | `POST` | `attendance.process` | Executes daily automated attendance calculation batch engine. |
| `/attendance/corrections` | `POST` | Active User | Submits attendance regularization request with requested punch times and reason. |
| `/attendance/corrections` | `GET` | Active User | Lists pending and processed attendance correction requests. |

### Key Features
- **ERP attendance synchronization**: processed daily records enter through `POST /api/v1/integrations/erp/attendance/records/bulk`; browser punch writes are not supported.
- **Remote Work Recognition**: The batch attendance processor queries approved Work Arrangements (WFH/OD) and marks employees `WORK_FROM_HOME` instead of falsely penalizing them as `ABSENT`.
- **Self-Approval Prevention**: Approvers cannot approve their own regularization requests.

---

## 11. Leave Management & Balance Ledger (Phase 4)

Complete leave lifecycle supporting multiple fiscal periods, double-entry leave ledger, and auto-rollback on cancellation.

### Endpoints (`/api/v1/leaves`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/leaves/periods` | `GET` | Active User | Lists defined fiscal leave periods. |
| `/leaves/periods` | `POST` | `leave.manage` | Creates a new fiscal leave period. |
| `/leaves/types` | `GET` | Active User | Lists configured leave policies (Casual, Sick, Earned). |
| `/leaves/types/{type_id}` | `GET` | Active User | Retrieves details of a specific leave type. |
| `/leaves/types` | `POST` | `leave.manage` | Creates a new leave type with holiday and carry-forward rules. |
| `/leaves/types/{type_id}` | `PATCH` | `leave.manage` | Updates leave limits, encashability, or paid status. |
| `/leaves/allocations` | `GET` | Active User | Lists employee leave allocations for a period. |
| `/leaves/allocations` | `POST` | `leave.manage` | Allocates leaves and credits double-entry ledger. |
| `/leaves/balance/employee/{id}`| `GET` | Active User | Returns real-time available, used, and pending leave balances. |
| `/leaves/` | `GET` | Active User | Lists leave applications with employee, status, and date filters. |
| `/leaves/{app_id}` | `GET` | Active User | Retrieves details of a single leave application. |
| `/leaves/` | `POST` | Active User | Submits leave application with balance check and overlap validation. |
| `/leaves/{app_id}/approve` | `PATCH` | `leave.approve` | Approves leave, debits ledger, and generates `ON_LEAVE` attendance records. |
| `/leaves/{app_id}/reject` | `PATCH` | `leave.reject` | Rejects application with reason and releases pending balance hold. |
| `/leaves/{app_id}/cancel` | `PATCH` | Active User | Cancels approved leave, restores ledger balance, and rolls back attendance. |

### Key Features
- **Sandwich Rule Calculation**: Optionally includes or excludes weekly offs and holidays during leave intervals based on policy definition (`include_holidays`).
- **Double-Entry Ledger Integrity**: Every allocation, approval, and cancellation logs a corresponding debit/credit entry in `LeaveLedgerEntry`.
- **Cancellation Rollback**: Cancelling an approved leave automatically purges the associated `ON_LEAVE` attendance records.

---

## 12. Work Arrangements / Remote Work (Phase 5)

Work From Home (WFH), On-Duty (OD), and Field Work request management.

### Endpoints (`/api/v1/work-arrangements`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/work-arrangements/` | `GET` | Active User | Lists work arrangement requests with status and type filters. |
| `/work-arrangements/{id}` | `GET` | Active User | Retrieves details of a specific work arrangement request. |
| `/work-arrangements/` | `POST` | Active User | Applies for WFH/OD with date range, reason, and contact phone. |
| `/work-arrangements/{id}/approve`| `PATCH`| `leave.approve` | Approves request; generates `WORK_FROM_HOME` or `PRESENT` records. |
| `/work-arrangements/{id}/reject` | `PATCH`| `leave.reject` | Rejects request with rejection remarks. |
| `/work-arrangements/{id}/cancel` | `PATCH`| Active User | Cancels request and reverts/cleans generated attendance records. |

### Key Features
- **Conflict Validation**: Prevents overlapping WFH/OD submissions if the employee already has active leave or another approved work arrangement for those dates.
- **Attendance Reversion**: Cancellation automatically cleans up generated attendance records to prevent ghost attendance.

---

## 13. Overtime Authorization (Phase 5)

Tracks and authorizes surplus working minutes calculated beyond shift thresholds.

### Endpoints (`/api/v1/overtime`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/overtime/` | `GET` | Active User | Lists overtime records with employee and status filters. |
| `/overtime/{ot_id}` | `GET` | Active User | Retrieves details of an overtime record. |
| `/overtime/{ot_id}/approve` | `PATCH` | `overtime.approve` | Authorizes overtime minutes with approver remarks and audit timestamp. |
| `/overtime/{ot_id}/reject` | `PATCH` | `overtime.approve` | Rejects overtime request with rejection reason. |
| `/overtime/employee/{id}/summary`| `GET` | Active User | Aggregates calculated vs approved OT minutes for a specific month/year. |

### Key Features
- **Audit Logging**: Approvals and rejections record `actioned_by`, `actioned_at`, and `rejection_reason`.
- **Self-Approval Block**: Managers cannot approve their own overtime records.

---

## 14. Executive Dashboard & Metrics

Dynamic permission-aware widget configurations and aggregated KPIs.

### Endpoints (`/api/v1/dashboard`)

| Endpoint | Method | Purpose |
| :--- | :---: | :--- |
| `/dashboard/widgets` | `GET` | Returns list of widget keys the current user is permitted to see. |
| `/dashboard/metrics` | `GET` | Returns aggregated metrics across unit-level operations and employee self-service. |

### Key Features
- **Unit Operational KPIs**: Total active headcount, today's attendance breakdown (Present, Absent, Leave, Weekly Off, Missed Punch), attendance rate percentage, pending leaves count, pending attendance corrections count, and approved today's/monthly overtime hours.
- **Unified Approvals Stream**: Combines pending leave applications and pending attendance corrections enriched with employee name, employee code, actual department name, and submission time.
- **Employee Self-Service Metrics**: Current shift schedule, today's punch in/out timestamps, monthly attendance counters, overtime hours, and active leave balance cards.

---

## 15. Reports & Analytics Matrix (Phase 6 Foundation)

High-density aggregated reports for payroll, compliance, and management audits.

### Endpoints (`/api/v1/reports`)

| Endpoint | Method | Permission | Purpose |
| :--- | :---: | :---: | :--- |
| `/reports/attendance-matrix`| `GET` | `reports.attendance` | Full calendar attendance matrix: day-by-day status grid ($1 \dots 31$) per employee with monthly summary totals. |
| `/reports/leave-summary` | `GET` | `reports.leave` | Enterprise annual leave balance report detailing allocated, used, pending, and available days per policy. |
