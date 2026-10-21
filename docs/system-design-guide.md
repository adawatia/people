# People HRMS — System Design Guide

**Purpose:** Study this codebase, understand its architecture, and identify issues.

**Scope:** `app/api/` (FastAPI backend) + `app/web/` (Nuxt frontend)

---

## PART 1: HIGH-LEVEL SYSTEM DESIGN

### 1.1 System Context

```
Browser (desktop/tablet/mobile web)
    │ HTTPS, httpOnly cookies (people_session, people_refresh)
    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ app/web — Nuxt 4 + Nitro (:3000)                                              │
│  • App shell, pages, layouts, components, composables                        │
│  • BFF layer: server/api/hrms/[...path].ts proxies EVERY business call       │
│    (browser never holds bearer token, never talks to FastAPI directly)       │
└──────────────────────────────────────────────────────────────────────────────┘
    │ Bearer <access token> · NUXT_HRMS_API_BASE (:8000)
    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ app/api — FastAPI (:8000) · all routes under /api/v1                         │
│  routers/  → HTTP shape, auth dependencies, scoping entry point              │
│  services/ → domain rules, transactions, cross-entity side effects           │
│  repositories/ → focused queries & persistence primitives                    │
│  core/     → auth, RBAC, row-level access, settings, logging, audit, email    │
│  db/       → SQLAlchemy models + dev seed                                    │
└──────────────────────────────────────────────────────────────────────────────┘
    │ SQLAlchemy async (psycopg)
    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL (DATABASE_URL) + Alembic migrations (app/api/alembic/versions)   │
└──────────────────────────────────────────────────────────────────────────────┘
    ▲
    │ Scoped HMAC headers · /api/v1/integrations/erp/**
┌──────────────────────────────────────────────────────────────────────────────┐
│ ERP (external system of record) — one-way authoritative writes INTO HRMS     │
│   employees · logins · units/departments/designations · shifts & assignments │
│   attendance records · holidays · overtime · leave balances                  │
│   ← HRMS publishes leave status changes for ERP to pull & acknowledge        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Ownership Boundary (Most Important Rule)

> **"ERP is the source of truth for employee and organization master data."**

| Data | Owner | HRMS Role |
|------|-------|-----------|
| Organization, units, departments, designations | **ERP** | Read-only mirrors (`GET /org/**`) |
| Employees (profile, hierarchy, salary, status) | **ERP** | Read; operational fields only |
| Login accounts, usernames, mobile numbers, passwords | **HRMS** | Created for employee at ERP request |
| Attendance punches, processed attendance | **ERP** | Ingest, store, reconcile |
| Shifts + employee shift assignments | **ERP** | Read + resolve windows |
| Holidays / weekly-offs | **ERP** | Read + resolve |
| Leave types, periods, allocations, balances | **ERP → HRMS** | Balances synced in; applications/approvals live in HRMS |
| Leave *status outcomes* | **HRMS → ERP** | Published on change feed for ERP to pull & ack |
| Overtime records | **ERP** | Approve/decline inside HRMS |
| Work-from-home requests, leave requests | **HRMS** | Fully owned in HRMS |

**Critical:** Anything ERP-owned returns `403` with explanatory detail on HRMS write path (deliberate, documented in code).

### 1.3 Technology Stack

**Backend:**
- FastAPI (Python 3.12+)
- SQLAlchemy 2.0 (async, psycopg)
- Alembic (8 migrations)
- fastapi-users (auth framework base)
- Pydantic (schemas)
- slowapi (rate limiting)
- JWT (HS256) for access tokens
- Redis optional for shared throttle state

**Frontend:**
- Nuxt 4 + Nitro
- @nuxt/ui v4 (125+ Vue components, Tailwind CSS theming)
- Vue 3 (Composition API)
- TypeScript
- echarts/nuxt-echarts for charts
- qrcode for MFA QR rendering

**Infrastructure:**
- PostgreSQL
- Optional Redis (throttle sharing, nonce storage)
- SMTP (Zoho) for emails

---

## PART 2: ARCHITECTURE DECOMPOSITION

### 2.1 Layer Map and Rules

| Layer | Location | Responsibility | Must Never |
|-------|----------|----------------|------------|
| **Routers** | `app/api/routers/*.py` | HTTP shape, request/response schemas, auth dependency wiring, scope resolution entry point, tag assignment | Contain business rules or raw SQL aggregates |
| **Services** | `app/api/services/*.py` | Domain invariants, state transitions, multi-entity side effects (attendance marking, ledger, balance), notifications | Know about HTTP (HTTPException is used, but not Request/Response) |
| **Repositories** | `app/api/repositories/*.py` | Named queries, existence checks, persistence primitives, eager-load options | Contain business policy |
| **Core** | `app/api/core/*.py` | Auth, RBAC, row-level scoping, settings, logging, audit, email, pagination helpers | Import services |
| **DB** | `app/api/db/models.py` | SQLAlchemy models, IST timestamps, constraints, sync columns | Contain queries |
| **Schemas** | `app/api/schemas/*.py` | Pydantic contracts for every request/response | Contain DB access |
| **Utils** | `app/api/utils/` | Background cleanup loop, number-to-words | — |

### 2.2 Request Lifecycle

```
1. CORSMiddleware        allow_origins from CORS_ORIGINS + regex for localhost/127.0.0.1/10.x/192.168.x
2. SlowAPI rate limit     default 200/minute per client IP ("memory://" storage)
                          /health overridden to 10/minute
3. log_requests           request_started → request_completed (duration_ms, status, ip, UA)
                          exception path logs request_failed with stack trace
4. Auth dependency        fastapi_users.current_user(active=True)  → JWT (aud fastapi-users:auth)
                          OR  require_permission("code")            → 403 "Missing permission: code"
                          OR  authenticate_erp_client (scoped HMAC signature)
5. Scope resolution       get_permission_scope / require_employee_access → 403 on out-of-scope rows
6. Service call           domain rules + transaction
7. Response model         Pydantic serialization; HTTPException → {"detail": ...}
```

### 2.3 Key Architectural Decisions

#### Decision 1: Stateless Access Tokens, Stateful Refresh Sessions
- Access tokens are short-lived JWTs (15 min business, 5 min privileged)
- **No permissions embedded** — re-resolved from DB every request
- Refresh tokens are opaque, hashed (SHA-256), stored in `auth_sessions`
- Rotation on every use with replay detection

**Why:** Short token lifetime + server-side authorization re-resolution means role changes apply immediately.

#### Decision 2: Three Authentication Domains
```
                    ┌─ business users  → /login        (all workforce roles)
PEOPLE HRMS auth ───┼─ Super Admin     → /admin/login   (password + MFA, stricter session policy)
                    └─ ERP machines   → /api/v1/integrations/erp/**  (scoped HMAC)
```

#### Decision 3: Role + Scope Model (No Role-Assignment Tables)
- Employee holds **at most one** elevated business role
- Permissions = base set + role bundle
- Scope = SELF | DEPARTMENT | UNIT | ORGANIZATION
- No per-user permissions, no deny overrides, no policy languages

#### Decision 4: BFF Pattern (Browser Never Talks to API Directly)
- Nuxt server proxy (`server/api/hrms/[...path].ts`)
- Tokens in HttpOnly cookies (`__Host-people_session`, `__Host-people_refresh` in production)
- Browser JavaScript never sees bearer tokens
- Refresh logic handled server-side with in-flight deduplication

#### Decision 5: ERP Sync Pattern
- ERP writes master data via scoped HMAC authentication
- HRMS publishes leave status changes on change feed for ERP to pull
- ERP-synced entities carry `erp_*` id columns for idempotency
- Corrections flow through `PENDING_ERP_RECONCILIATION` status

---

## PART 3: DATA MODEL

### 3.1 Entity Relationship Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│  users      │     │ organizations│    │   units         │
│  (auth)     │     │  (singleton) │     │   (org children)│
└──────┬──────┘     └─────────────┘     └────────┬────────┘
       │                                         │
       │ 1:1                                     │ 1:N
       ▼                                         ▼
┌─────────────────┐     ┌─────────────┐     ┌─────────────────┐
│  employees      │     │ departments │     │   shifts        │
│  (business id)  │     │ (unit child)│     │   (unit child)  │
└──────┬──────────┘     └──────┬──────┘     └────────┬────────┘
       │                       │                       │
       │ 1:N                   │ 1:N                   │ 1:N
       ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────┐     ┌─────────────────┐
│ leave_applications│   │attendance   │     │ shift_assignments│
│ attendance_records│   │  records    │     │ (dated windows)  │
└─────────────────┘     └─────────────┘     └─────────────────┘
```

### 3.2 Core Tables

**Identity & Access (4 tables):**
- `users` — 30+ columns including MFA fields (encrypted secret, pending secret, recovery code hashes, last_used_step)
- `auth_sessions` — Hash-only refresh token storage, rotation chain via `replaced_by_id`, revocation reasons
- `audit_logs` — Append-only: actor, action, entity, filters_json, request_id, ip_address
- `notifications` + `notification_receipts` — Per-user read state for shared broadcasts

**Org Structure (ERP-owned, 5 tables):**
- `organizations` — Singleton enforced by `singleton_key` unique constraint
- `units` — FK to organization
- `departments` — FK to unit
- `designations` — Standalone, referenced by employees
- `department_approvers` — LEAVE/SHIFT/EXPENSE/WORK_ARRANGEMENT approver types

**Workforce (10+ tables):**
- `employees` — The operational core. Authorization identity in `business_role`, `access_scope`, `access_scope_id`
- `employee_work_histories` — Transfers/promotions history

**Scheduling (4 tables):**
- `shifts` — Start/end, grace minutes, break minutes, cross-midnight, Frappe-HR-style thresholds
- `shift_assignments` — Dated windows, status
- `holiday_lists` + `holidays` — With `erp_holiday_id`, `is_weekly_off`, `is_organization_wide`

**Leave (7 tables):**
- `leave_periods`, `leave_types`
- `leave_allocations` — Unique (employee, type, period)
- `leave_ledger_entries` — Double-entry: ALLOCATION/APPLICATION/REVERSAL/EXPIRY
- `leave_balances` — Current-year read model (allocated, used, pending)
- `leave_applications` — Full cancellation workflow, `erp_event_id`/`erp_sync_status`

**Attendance (5 tables):**
- `attendance_records` — Unique (employee, date), status, punch in/out, worked/overtime/late/early minutes
- `attendance_punches` — Raw punches with resolved shift window, geolocation
- `attendance_discrepancies`, `attendance_correction_requests` — `PENDING_ERP_RECONCILIATION`

**Overtime (2 tables):**
- `overtime_records` — `calculated_minutes`, `approved_minutes`, status, `erp_event_id`
- `overtime_approvals` — Audit of each approval action

**Work Arrangements (1 table):**
- `work_arrangement_requests` — WFH/OUT_DUTY/FIELD_WORK/OFFICE, status, actioner, rejection reason

### 3.3 Key Design Patterns in Schema

1. **ERP Sync Columns:** `erp_id`, `erp_event_id`, `erp_sync_status`, `erp_synced_at` on synced entities
2. **IST Timestamps:** All `DateTime(timezone=True)` default to `now_ist()` (Asia/Kolkata)
3. **Numeric Precision:** Leave quantities `Numeric(5,1)`, money `Numeric(12,2)`
4. **Unique Constraints:** Employee+date on attendance, employee+type+period on allocations, transaction_type+transaction_id on ledger
5. **Indexes:** `ix_auth_sessions_live_user_created` (partial index on non-revoked sessions), `ix_attendance_records_date_employee` (date-first for dashboards)

---

## PART 4: AUTHENTICATION & AUTHORIZATION DEEP DIVE

### 4.1 Authentication Flow

#### Business Login (`POST /api/v1/auth/employee/login`)
```
1. Throttle check (ip+account, account, ip keys)
2. Identity normalization (mobile → E.164 or username)
3. User lookup (username OR normalized mobile)
   - Unknown user: dummy hash to prevent timing enumeration
4. Password verification (with opportunistic hash upgrade)
5. Employee existence check (403 if technical account)
6. MFA check:
   - If required: return MfaChallenge {mfa_token, enrollment_required, expires_in}
   - If not: issue session directly
7. Session issuance:
   - Create AuthSession (hash refresh token, set expires_at/absolute_expires_at)
   - Mint access JWT (sid = session_id)
   - Return {access_token, refresh_token, expires_in, session_id, ...}
```

#### Super Admin Login (`POST /api/v1/auth/super-admin/login`)
- Same flow but:
  - Username only (rejects @, digits, +)
  - Must have is_superuser
  - Stricter session policy (5 min access, 15 min idle, 2h absolute)
  - Same generic 401 for non-superuser (enumeration resistance)

### 4.2 Session State Machine

```
              issue                refresh                logout / password change / reset
  (none) ─────────▶ ACTIVE ─────────────▶ ROTATED   ACTIVE ─────────────▶ REVOKED
                     │  ▲                                        │
                     │  └── rotation is atomic; one descendant  │
                     ▼                                          ▼
              idle / absolute deadline                    ROTATED token reused
                     ▼                                          ▼
                  EXPIRED  ◀───────────────────────────  COMPROMISE DETECTED
                                                          (all live sessions revoked)
```

**Key behaviors:**
- Rotation: `UPDATE ... WHERE id = :id AND revoked_at IS NULL` — DB decides race
- Replay detection: rotated token reused → revoke ALL user sessions (`reuse_detected`)
- Idle timeout checked on every refresh
- Absolute deadline never extended by refreshing
- Password change revokes all sessions but does NOT mint replacement

### 4.3 MFA Architecture

**TOTP Implementation:**
- RFC 6238, constant-time verification with ±1 step window (30s)
- Seeds encrypted at rest (AES-256-GCM) under `MFA_ENCRYPTION_KEY`
- Format: `v1:<base64url(nonce‖ciphertext‖tag)>`
- Legacy plaintext seeds re-encrypted on next write
- Wrong key → fail closed (fallback to recovery codes)

**Single-Use Code Enforcement:**
- Matched step recorded in `mfa_last_used_step`
- Same step or earlier → rejected as replay
- Recovery codes stored as SHA-256 hashes (like refresh tokens)

**Enrollment Flow:**
1. `POST /auth/mfa/enroll` (challenge token required) → returns secret, otpauth URI, 10 recovery codes
2. Client renders QR from URI (seed never in URL/query string)
3. `POST /auth/mfa/activate` with code → promotes pending secret, sets mfa_enabled

**Replacement Flow:**
- `mfa_pending_secret` written first, active seed untouched until proven
- Prevents: abandoned "issue new secret" from disabling factor entirely

**Recovery Flow:**
- Start: identity → uniform response (no account enumeration)
- Verify: TOTP or recovery code (separate from normal login)
- Reset: one-time password reset capability, revokes all sessions, keeps MFA enrolled

### 4.4 Authorization Model

#### Permission Hierarchy

```
BASE_EMPLOYEE_PERMISSIONS (every employee):
  employee.view_self, attendance.view_self, leave.apply, leave.view_self, leave.cancel,
  work_arrangement.apply, work_arrangement.view_self, work_arrangement.cancel,
  shift.view_self, overtime.view_self

DEPARTMENT_MANAGER adds:
  employee.view, attendance.view_department, leave.approve, leave.reject,
  work_arrangement.approve, work_arrangement.reject, overtime.view_department,
  overtime.approve, reports.attendance, reports.leave

HR_ADMIN adds:
  user.view/create/update/deactivate, employee.view/create/update/deactivate,
  designation.view/create/update/delete,
  attendance.view/view_unit/view_department/process/correct,
  leave.manage/approve/reject, work_arrangement.manage/approve/reject,
  shift.assign/update, overtime.approve/view_department,
  reports.view/attendance/leave/overtime/salary_cost,
  system.configure, audit.view, salary_cost.view_unit/view_department

ORGANIZATION_OWNER adds:
  employee.view, attendance.view/view_unit/view_department,
  overtime.view/view_department,
  reports.view/attendance/leave/overtime, dashboard.view_organization
```

#### Scope Resolution

```python
# From core/business_roles.py: resolve_business_access(employee)
user.is_superuser            → organization scope
business_role HR_ADMIN       → access_scope ORGANIZATION → organization scope
                               access_scope UNIT (+ id)  → unit scope
business_role DEPARTMENT_MANAGER → department scope
business_role ORGANIZATION_OWNER → organization scope
no business role             → SELF scope: {caller's own employee_id}
```

**Key details:**
- Defaults: HR admin without explicit scope → UNIT on own unit_id
- Manager → DEPARTMENT on own department_id
- Owner → ORGANIZATION
- Illegal scope for role → falls back to role default (doesn't widen access)
- Organization HR must be explicit (blank unit_id ≠ whole organization)

#### Row-Level Access Check

```python
# require_employee_access(user, employee, permission_code, session, allow_self=False)
# Merges scopes for multiple permission codes (any code covering row = access granted)
```

### 4.5 Dashboard Widget Gating

| Widget key | Gate |
|------------|------|
| `my_profile`, `my_leave_balance` | always |
| `pending_approvals`, `team_leave_requests` | `leave.approve` |
| `attendance_overview` | `attendance.view_department` |
| `unit_overview` | `employee.view` |
| `organization_overview` | `dashboard.view_organization` |
| `system_health` | `system.configure` |

---

## PART 5: DOMAIN SERVICES DEEP DIVE

### 5.1 Attendance Engine (`services/attendance_service.py`)

**Processing Pipeline:**
```
1. Resolve shift window for date (dated assignment beats ERP default shift; handles cross-midnight)
2. Classify day: WEEKLY_OFF, HOLIDAY, ON_LEAVE (from approved leave), WORK_FROM_HOME (from approved arrangement)
3. Compute worked_minutes minus break_minutes
4. Derive late_minutes (beyond late_entry_grace_minutes) and early_exit_minutes
5. Apply thresholds:
   - < absent_threshold_hours → ABSENT
   - < half_day_threshold_hours → HALF_DAY
   - otherwise → PRESENT
   - Single missing punch → MISSED_PUNCH
   - Unpunched day → WEEKLY_OFF/ON_LEAVE/ABSENT as applicable
6. Overtime minutes beyond shift end → overtime_records
```

**Correction Flow:**
- `POST /attendance/corrections` requires `attendance.correct` + row scope
- Always writes `sync_status = PENDING_ERP_RECONCILIATION`
- No approve/reject endpoints — ERP confirmation is the approval
- Self-correction prevention (can't correct own record)

**Ingest:**
- Raw punches: `record_punch` (idempotent by employee/time/type or erp_event_id)
- Processed attendance: `POST /integrations/erp/attendance/records/bulk` only

### 5.2 Leave Engine (`services/leave_service.py` — 730 lines, largest service)

**Apply Flow:**
```
1. to_date >= from_date; employee exists
2. Reject overlap with existing PENDING/APPROVED application
3. Resolve active leave_period for from_date
4. calculate_leave_days:
   - half day → 0.5
   - include_holidays → calendar days
   - else → count days excluding holidays AND weekly-offs
5. Check max_consecutive_days limit
6. For paid leave: check balance (allocated - used - pending >= days_count)
7. Create application (status=PENDING), increment balance.pending
```

**Approve Flow:**
```
1. Status must be PENDING
2. Self-approval prevention
3. Set status=APPROVED, erp_event_id, erp_sync_status=PENDING
4. For paid leave: balance.pending -= days, balance.used += days
5. Debit ledger entry (APPLICATION, -days_count)
6. Update/create AttendanceRecord for each approved day (ON_LEAVE or HALF_DAY)
   - Skip holidays if include_holidays=False
```

**Cancel Flow:**
```
1. Status must be PENDING or APPROVED
2. If APPROVED and today >= from_date → 409 (must use early-return request)
3. For paid leave: balance.used -= days (if approved) or balance.pending -= days (if pending)
4. If was approved: reversal ledger entry + revert attendance records
5. Set status=CANCELLED, erp_event_id, erp_sync_status=PENDING
```

**Allocation Flow:**
```
1. Double-entry ledger: ALLOCATION credit (+total)
2. Upsert leave_balances (allocated += total)
3. Both in same transaction
```

### 5.3 Shift Resolution

- Dated `shift_assignments` beat ERP default `shift_id` on employee
- Cross-midnight shifts: actual_start/actual_end span across midnight
- `begin_check_in_before_minutes` / `allow_check_out_after_minutes` for punch window margins

### 5.4 Holiday/Weekly-Off Resolution

- `is_holiday_or_weekly_off(employee_id, date)` checks:
  1. Organization-wide holidays
  2. Unit-specific holidays
  3. Weekly off day from holiday list

---

## PART 6: API ENDPOINTS MAP

### 6.1 Authentication & Sessions (23+ endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/employee/login` | POST | Business login (OAuth2 form) |
| `/auth/super-admin/login` | POST | Super Admin login |
| `/auth/password-recovery/start` | POST | Start recovery (identity → uniform response) |
| `/auth/password-recovery/verify` | POST | Verify authenticator for recovery |
| `/auth/password-recovery/reset` | POST | Set new password |
| `/auth/change-password` | POST | Change own password (step-up) |
| `/auth/super-admin/username` | PATCH | Change Super Admin username (step-up) |
| `/auth/session` | POST | Create additional session |
| `/auth/session/refresh` | POST | Rotate refresh token |
| `/auth/session` | DELETE | Revoke current session |
| `/auth/sessions` | GET | List my sessions |
| `/auth/sessions` | DELETE | Logout everywhere |
| `/auth/sessions/{id}` | DELETE | Revoke one session |
| `/auth/session` | GET | Describe current session |
| `/auth/mfa/enroll` | POST | Start MFA enrollment (challenge token) |
| `/auth/mfa/activate` | POST | Activate enrollment (with code) |
| `/auth/mfa/verify` | POST | Verify TOTP/recovery code |
| `/auth/mfa/reset` | POST | Reset MFA (password re-verified) |
| `/auth/mfa/confirm` | POST | Confirm from session |
| `/auth/mfa/disable` | POST | Disable MFA (password re-verified) |
| `/auth/mfa/status` | GET | Get MFA status |
| `/auth/mfa/recovery/regenerate` | POST | Regenerate recovery codes |
| `/hr/employees/{id}/password-reset` | POST | HR set employee temp password |

### 6.2 ERP Integration Endpoints (Scoped HMAC)

| Endpoint | Purpose |
|----------|---------|
| `/integrations/erp/employees` | Employee provisioning sync |
| `/integrations/erp/employees/bulk`, `/units/bulk`, `/departments/bulk`, `/designations/bulk` | Bulk upsert with per-item `accepted`/`failed` |
| `/integrations/erp/employees/{id}/password-reset` | ERP set temp password |
| `/integrations/erp/attendance/records/bulk` | Processed attendance sync |
| `/integrations/erp/shifts` | Shift sync |
| `/integrations/erp/shifts/assignments` | Shift assignment sync |
| `/integrations/erp/holidays` | Holiday sync |
| `/integrations/erp/overtime` | Overtime records sync |
| `/integrations/erp/leaves` | Leave status change ack |
| `/integrations/erp/master-data` | Org/unit/dept/designation upserts |

### 6.3 Business Resource Endpoints

**Employees:** `GET/POST/PATCH/DELETE /employees`, `GET /employees/{id}`, `GET /employees/{id}/history`

**Attendance:** `GET /attendance`, `GET /attendance/checkins`, `GET /attendance/records/{id}`, `GET /attendance/employee/{id}/calendar`, `GET /attendance/employee/{id}/summary`, `POST /attendance/process`, `POST /attendance/corrections`, `GET /attendance/corrections`

**Leave:** `GET/POST /leaves`, `GET /leaves/{id}`, `PATCH /leaves/{id}/approve`, `PATCH /leaves/{id}/reject`, `PATCH /leaves/{id}/cancel`, `PATCH /leaves/{id}/cancellation/approve`, `PATCH /leaves/{id}/cancellation/reject`, `GET /leaves/types`, `GET /leaves/types/{id}`, `GET /leaves/balance/employee/{id}`, `GET /leaves/periods`

**Shifts:** `GET/POST /shifts`, `GET /shifts/{id}`, `PATCH /shifts/{id}`, `DELETE /shifts/{id}`, `GET /shifts/assignments`, `POST /shifts/assignments`, `DELETE /shifts/assignments/{id}`

**Holidays:** `GET/POST /holidays`, `GET /holidays/{id}`, `DELETE /holidays/{id}`, `GET /holidays/lists`, `POST /holidays/lists`, `GET /holidays/lists/{id}`, `DELETE /holidays/lists/{id}`

**Overtime:** `GET/POST /overtime`, `GET /overtime/{id}`, `PATCH /overtime/{id}/approve`, `PATCH /overtime/{id}/reject`, `GET /overtime/corrections`

**Work Arrangements:** `GET/POST /work-arrangements`, `GET /work-arrangements/{id}`, `PATCH /work-arrangements/{id}/approve`, `PATCH /work-arrangements/{id}/reject`, `PATCH /work-arrangements/{id}/cancel`

**Dashboard:** `GET /dashboard/widgets`, `GET /dashboard/metrics`, `GET /dashboard/owner`, `GET /dashboard/owner/exceptions`, `GET /dashboard/technical-metrics`

**Reports:** `GET /reports/attendance`, `GET /reports/leave`, `GET /reports/overtime`, `GET /reports/employee/{id}/attendance`, `GET /reports/employee/{id}/leave`

**Org:** `GET /org/organization`, `GET /org/units`, `GET /org/units/{id}`, `GET /org/departments`, `GET /org/departments/{id}`, `GET /org/designations`, `GET /org/designations/{id}`

**Notifications:** `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/read`, `POST /notifications/read-all`, `GET /notifications/{id}`

**Users (technical):** `GET /users`, `GET /users/{id}`, `GET /users/me`, `PATCH /users/{id}`, `POST /users`, `DELETE /users/{id}`, `POST /users/{id}/deactivate`, `POST /users/{id}/reactivate`

**Audit:** `GET /audit/events`, `GET /audit/events/{id}`

---

## PART 7: FRONTEND ARCHITECTURE

### 7.1 Nuxt Structure

```
app/web/
├── app/
│   ├── app.vue                    # Root: UApp > NuxtLayout > NuxtPage
│   ├── app.config.ts              # Design tokens (colors, typography, spacing...)
│   ├── error.vue                  # Error page
│   ├── assets/css/main.css        # Global styles
│   ├── components/                # Vue components
│   ├── composables/
│   │   ├── useAuth.ts             # Auth state (user, hasPermission, login, logout...)
│   │   ├── useHrmsApi.ts          # API request helper (auto 401 redirect)
│   │   ├── useWorkspace.ts        # Workspace switching logic
│   │   ├── useListState.ts        # List UI state
│   │   ├── useRetainedData.ts     # Stale-data retention
│   │   └── useChartTheme.ts       # ECharts theme
│   ├── layouts/
│   │   ├── default.vue            # Main platform shell (sidebar, header, content)
│   │   └── auth.vue               # Auth layout (no shell)
│   └── pages/                     # kebab-case routes
│       ├── login.vue              # Workforce login
│       ├── admin/login.vue        # Super Admin login
│       ├── forgot-password.vue    # Password recovery
│       ├── index.vue              # Dashboard (/)
│       ├── profile.vue
│       ├── settings.vue
│       ├── notifications.vue
│       ├── attendance/
│       ├── leaves/
│       ├── employees/
│       ├── approvals/
│       ├── organization/
│       ├── reports/
│       ├── overtime/
│       ├── shifts/
│       └── work-arrangements/
├── server/
│   ├── api/
│   │   ├── hrms/[...path].ts      # BFF proxy: attaches Bearer token from cookie
│   │   └── session/
│   │       ├── login.post.ts      # Signs in, stores cookies
│   │       ├── mfa.post.ts        # Completes MFA challenge
│   │       ├── me.get.ts          # Current user
│   │       └── index.delete.ts    # Logout
│   └── utils/
│       └── hrms.ts                # Cookie names, refresh logic, error mapping
├── shared/
│   └── types/                     # 12 TypeScript type files
│       ├── auth.ts                # CurrentUser, LoginPayload, MfaChallenge...
│       ├── workforce.ts           # Shift, Holiday, HolidayList...
│       ├── attendance.ts
│       ├── leave.ts
│       ├── dashboard.ts
│       ├── employee.ts
│       ├── notification.ts
│       ├── organization.ts
│       ├── overtime.ts
│       ├── pagination.ts
│       ├── report.ts
│       └── work-arrangement.ts
└── public/
    └── branding/                  # SVG symbols, icons
```

### 7.2 BFF Proxy Pattern

```typescript
// server/api/hrms/[...path].ts
export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path')
  const token = getCookie(event, SESSION_COOKIE)
  const refresh = getCookie(event, REFRESH_COOKIE)
  
  try {
    if (!token) throw createError({ statusCode: 401 })
    return await call(token)  // $fetch with Authorization: Bearer
  } catch (error) {
    if (status === 401 && refresh && path !== 'auth/session/refresh') {
      // Single-flight refresh
      refreshed = await refreshSession(event, refresh)
      setAccessCookie(event, refreshed.access_token, refreshed.expires_in)
      setRefreshCookie(event, refreshed.refresh_token, refreshed.absolute_expires_at)
      return await call(refreshed.access_token)
    }
    if (status === 401) clearSessionCookies(event)
    throw upstreamError(error)
  }
})
```

**Refresh coordination:**
- `inFlightRefreshes` Map: concurrent callers share one rotation
- `recentRefreshes` Map: 2-second result cache for late SSR subrequests
- Prevents replay detection from revoking session on concurrent calls

### 7.3 Auth Composable

```typescript
// useAuth.ts
export function useAuth() {
  const user = useState<CurrentUser | null>('auth-user', () => null)
  const hasPermission = (permission: string) => 
    Boolean(user.value?.is_superuser || user.value?.permissions?.includes(permission))
  
  async function login(payload: LoginPayload): Promise<LoginResult>
  async function completeMfa(credential: { mfa_token, code, enrollment? })
  async function logout()  // DELETE /api/session, navigate to login
  // ...
}
```

### 7.4 Navigation Gating

**Workspace-based nav in `default.vue`:**
- `MY` workspace: employee self-service pages
- `TEAM` workspace: manager pages (filtered by permissions)
- `HR` workspace: HR admin pages
- `EXECUTIVE` workspace: organization owner analytics
- `TECHNICAL` workspace: superuser

**Permission filtering:**
```typescript
const visibleItems = computed(() => 
  (navByWorkspace[workspace.current.value] || [])
    .filter(item => !item.permissions || item.permissions.some(hasPermission))
)
```

**Important:** Nav gating is presentation-only. Every endpoint re-checks permission + row scope.

### 7.5 Design System

From `app.config.ts`:
- **Brand:** Editorial violet, warm paper/ink neutrals
- **Primary:** Violet (`ui-primary: #5637a5`)
- **Semantic:** Success/mint, warning/yellow, error/rose, info/blue
- **Typography:** Newsreader (auth), system sans (platform)
- **Sizes:** 44px minimum controls, 52px desktop table rows, 60px mobile
- **Responsive:** 256px sidebar (1024px+), 76px collapsed, bottom nav on mobile

---

## PART 8: ISSUES & TECHNICAL DEBT

### 8.1 Known Issues from Architecture Doc (§8)

#### 8.1.1 Dead UI Actions (Frontend Shows Actions That Return 403)

The frontend offers operations that the API deliberately rejects because ERP owns the data:

| UI Action | Why It's Dead | API Behavior |
|-----------|---------------|--------------|
| Create employee | ERP owns employee creation | 403 |
| Create/update/delete designation | ERP owns designations | 403 |
| Create/update/delete unit | ERP owns units | 403 |
| Create/update/delete department | ERP owns departments | 403 |
| Create shift | ERP owns shifts | 403 |
| Assign shift | ERP owns shift assignments | 403 |
| Sync holidays | ERP owns holidays | 403 |
| Create overtime record | ERP owns overtime creation | 403 |

**Impact:** Users see buttons/forms that fail. Need either: hide in UI when ERP-owned, or show clear "ERP manages this" messaging.

#### 8.1.2 Missing Endpoints

- **No attendance correction approve/reject:** Corrections stay `PENDING` forever until ERP confirms. No HR approval path exists.
- **No early-return request endpoint:** Canceling approved leave that has started returns 409 with message about "approved early-return request" but no such endpoint exists.
- **No overtime correction workflow:** Similar gap to attendance corrections.

#### 8.1.3 Permission Gaps (Codes Granted But Never Enforced)

These permission codes exist but don't gate any behavior:
- `employee.view_self`, `attendance.view_self`, `leave.view_self`, `overtime.view_self`, `shift.view_self`
- `reports.view`, `reports.overtime`, `reports.salary_cost`
- `salary_cost.*`, `audit.view`, `user.*`
- `employee.update`, `employee.deactivate`
- `overtime.view`

#### 8.1.4 Session Concurrency Limitations

- **Multi-worker BFF deployments need shared rotation coordination or sticky sessions** — the in-flight refresh deduplication is per-process
- Access token revocation window: access token valid until expiry even after session revoked

### 8.2 Security Considerations

#### 8.2.1 Positive Security Stances

1. **Timing attack resistance:** Dummy hash for unknown users in login
2. **Replay protection:** Refresh token rotation with cascade revocation on reuse
3. **Enumeration resistance:** Same generic 401 for all credential failures
4. **MFA replay prevention:** Step counter recording, single-use codes
5. **Encrypted MFA seeds:** AES-256-GCM, key outside database
6. **Recovery codes hashed:** SHA-256 like refresh tokens
7. **Password policy:** zxcvbn, personal info check, breached password lookup (fail-open)
8. **Step-up re-verification:** Password re-check for sensitive operations
9. **Audit logging:** Append-only, correlation IDs, no secrets logged
10. **Throttling:** Per-IP, per-account, per-pair with progressive delays
11. **ERP HMAC:** Timestamp window, nonce replay protection, body hash

#### 8.2.2 Areas to Watch

1. **Rate limiter is in-process memory** — multiple workers = per-worker limits
2. **Throttle state:** `AUTH_THROTTLE_BACKEND=memory` is per-worker; production needs Redis
3. **Access tokens can't be revoked before expiry** — 15-min window after logout/password change
4. **Development shortcuts:** `ERP_API_KEY` legacy key, development MFA encryption key, dev defaults refused in production but must be guarded
5. **`TRUST_PROXY_HEADERS` default false** — must be explicitly enabled behind proxy
6. **Breach check is fail-open** — `remote` mode fails to `local` or `off`

### 8.3 Performance Considerations

#### 8.3.1 Known Bottlenecks

1. **Attendance processing is row-by-row:** `process_attendance_batch` loops employees × dates, one `process_attendance_for_employee_date` call per combo
2. **Leave balance queries:** Per-employee, per-type balance lookups during apply/approve
3. **No query result caching:** Every request re-resolves permissions from DB
4. **Pagination page sizes:** Up to 100, but some list queries may not be optimized for large offsets

#### 8.3.2 Indexes Present

- `users.username` (unique), `users.mobile_number` (unique)
- `employees.user_id`, `employees.employee_code`, `employees.department_id`, `employees.unit_id`, `employees.reporting_manager_id`
- `auth_sessions.user_id`, `auth_sessions.token_hash` (unique), `auth_sessions.revoked_at`
- `attendance_records.employee_id`, `attendance_records.attendance_date`, composite `(attendance_date, employee_id)`
- `attendance_punches.employee_id + punch_time + punch_type`
- `leave_applications.employee_id`, `leave_ledger_entries.employee_id + leave_type_id`
- Partial index: `auth_sessions.live_user_created` (non-revoked only)

### 8.4 Scalability Concerns

1. **Single organization singleton:** `organizations` table has unique `singleton_key=1` — designed for one org per DB
2. **In-process rate limiter:** Can't share state across workers without Redis
3. **Nonce storage:** Memory-based nonces for ERP auth; Redis needed for multi-worker
4. **Notification cleanup:** Background task, single instance

### 8.5 Testing Coverage

**15 test modules in `app/api/tests/`:**
- `test_auth_primitives.py` — Token/crypto tests
- `test_auth_sessions.py` — Session lifecycle, rotation, replay
- `test_auth_hardening_http.py` — Throttling, enumeration resistance
- `test_mfa_totp.py` — TOTP verification, replay, recovery codes
- `test_security_integrity_hardening.py` — Integration security tests
- `test_business_role_authorization.py` — Permission/scope resolution
- `test_business_role_provisioning.py` — Role column management
- `test_employee_access.py` — Row-level scope checks
- `test_permission_grants.py` — Permission catalogue assertions
- `test_attendance_corrections_http.py` — Correction workflow
- `test_overtime_approval_validation.py` — Overtime workflow
- `test_notifications.py` — Notification system
- `test_notification_audience.py` — Receipt/per-user read state
- `test_erp_upserts.py` — ERP sync idempotency
- `test_milestone_1 through test_milestone_6.py` — Feature milestones

**Frontend:** Playwright auth tests (`playwright.auth.config.ts`)

---

## PART 9: MIGRATION HISTORY

8 Alembic migrations showing evolution:

| Migration | Purpose |
|-----------|---------|
| `0a1b2c...security_integrity_hardening` | Auth hardening |
| `1b2c3d...half_day_leave_balances` | Half-day leave support |
| `2c3d4e...performance_indexes` | Query performance indexes |
| `4f2c1a...enforce_single_organization` | Singleton org constraint |
| `5b7c2d...add_master_data_updated_at` | Audit timestamps on master data |
| `6c8d3e...add_erp_leave_sync` | ERP leave sync columns |
| `7d9e4f...add_erp_holiday_id` | ERP holiday IDs |
| `8d57e4...clean_fixed_role_baseline` | Role permission baseline |
| `8e0f5a...add_erp_overtime_fields` | ERP overtime fields |
| `9a1d2e...add_audit_logs` | Audit log table |
| `a2b3c4...add_leave_cancellation_workflow` | Leave cancellation |
| `b3c4d5...add_business_role_and_access_scope` | Role/scope columns |
| `c4d5e6...harden_auth_sessions_and_add_mfa` | Session hardening + MFA |
| `d5e6f7...mfa_replay_and_encryption` | MFA replay prevention + encryption |
| `e6f7a8...expire_pending_mfa` | Expire unconfirmed pending MFA |
| `f7a8b9...reconcile_password_recovery_columns` | Password recovery cleanup |

---

## PART 10: CONFIGURATION

### 10.1 Required Environment Variables (Production)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | postgresql+psycopg://... |
| `JWT_SECRET` | Signing key for tokens |
| `ERP_API_CLIENTS` | JSON map of client_id → {secret, scopes} |
| `MFA_ENCRYPTION_KEY` | AES-256 key for TOTP seed encryption |

### 10.2 Session Policy Settings

| Setting | Business | Privileged |
|---------|----------|------------|
| Access token TTL | 15 min | 5 min |
| Refresh token TTL | 30 days | 30 days |
| Idle timeout | 60 min | 15 min |
| Absolute timeout | 12 hours | 2 hours |

### 10.3 Throttle Settings

| Setting | Value |
|---------|-------|
| Default rate limit | 200/minute per IP |
| Login max failures | 5 (ip+account), 10 (account), 100 (ip) |
| Login block start | 60s, doubling to 3600s max |
| Refresh max failures | 20 |
| Block window | 900s sliding |

---

## PART 11: diagram OF REQUEST FLOW

### 11.1 Login Flow

```
Browser                    Nuxt Server (BFF)              FastAPI Backend           Database
   │                            │                              │                     │
   ├───────────────────────────►│                              │                     │
   │  POST /api/session/login   │                              │                     │
   │  {identity, password}      │                              │                     │
   │                            ├──────────────────────────────►│                     │
   │                            │  POST /api/v1/auth/employee/ │                     │
   │                            │  login (OAuth2 form)         │                     │
   │                            │                              │  Lookup user         │
   │                            │                              │  Verify password     │
   │                            │                              │  Check employee      │
   │                            │                              │                     │
   │                            │◄──────────────────────────────┤                     │
   │                            │  {mfa_required: true,        │                     │
   │                            │   mfa_token: "...",          │                     │
   │                            │   enrollment_required: false}│                     │
   │◄────────────────────────────┤                              │                     │
   │  Return MFA challenge      │                              │                     │
   │                            │                              │                     │
   │  POST /api/session/mfa     │                              │                     │
   │  {mfa_token, code}         │                              │                     │
   │                            ├──────────────────────────────►│                     │
   │                            │  POST /api/v1/auth/mfa/verify│  Verify TOTP        │
   │                            │                              │  Issue session       │
   │                            │◄──────────────────────────────┤  Create AuthSession │
   │                            │  {access_token, refresh_token}│  Hash refresh token │
   │                            │                              │                     │
   │                            │  GET /api/v1/users/me        │                     │
   │                            │  (with access token)         │  Resolve permissions │
   │                            │◄──────────────────────────────┤  Return user+roles  │
   │                            │                              │                     │
   │◄────────────────────────────┤                              │                     │
   │  Set-Cookie: people_session │                              │                     │
   │  Set-Cookie: people_refresh │                              │                     │
   │  Return user object         │                              │                     │
   │                            │                              │                     │
   │  Subsequent requests:      │                              │                     │
   │  GET /api/hrms/leaves      │                              │                     │
   │  (cookies auto-sent)       │  GET /api/v1/leaves          │  Check scope        │
   │                            │  (Bearer from cookie)        │  Query leaves       │
   │◄────────────────────────────┤                              │                     │
   │  Return leaves             │                              │                     │
```

### 11.2 ERP Sync Flow (Attendance)

```
ERP System                   FastAPI Backend           Database
   │                            │                     │
   │  POST /api/v1/integrations/│                     │
   │  /erp/attendance/records/ │                     │
   │  bulk                      │                     │
   │  Headers:                  │                     │
   │    X-ERP-Client-ID         │                     │
   │    X-ERP-Timestamp         │                     │
   │    X-ERP-Nonce             │                     │
   │    X-ERP-Signature         │                     │
   │                            │                     │
   │                            ├────────────────────►│  authenticate_erp_client:
   │                            │                     │    - Validate HMAC-SHA256
   │                            │                     │    - Check timestamp window
   │                            │                     │    - Consume nonce (single-use)
   │                            │                     │    - Verify scopes
   │                            │                     │
   │                            │◄────────────────────┤  Return ErpPrincipal
   │                            │                     │
   │                            │  Process records... │
   │                            │  Upsert attendance  │
   │                            │  (idempotent by     │
   │                            │   erp_record_id)    │
   │                            │                     │
   │◄────────────────────────────┤                     │
   │  {synced: N, errors: [...]}│                     │
```

---

## PART 12: QUICK REFERENCE — FILES THAT MATTER MOST

### For Understanding Auth
- `app/api/core/auth.py` — UserManager, permission helpers, rate limiter
- `app/api/core/session_policy.py` — Session TTL configuration
- `app/api/core/tokens.py` — Token creation/hashing
- `app/api/core/totp.py` — TOTP verification
- `app/api/core/secret_box.py` — MFA seed encryption
- `app/api/core/auth_throttle.py` — Throttle implementation
- `app/api/core/password_policy.py` — Password rules
- `app/api/services/auth_service.py` — Session state machine

### For Understanding Authorization
- `app/api/core/business_roles.py` — Role/scope resolution
- `app/api/core/employee_access.py` — Row-level scope
- `app/api/core/rbac.py` — Dashboard widget gating

### For Understanding Domain Logic
- `app/api/services/attendance_service.py` — Attendance engine
- `app/api/services/leave_service.py` — Leave workflow
- `app/api/services/shift_service.py` — Shift resolution
- `app/api/services/holiday_service.py` — Holiday resolution

### For Understanding API Surface
- `app/api/routers/auth_login.py` — Login endpoints
- `app/api/routers/auth_sessions.py` — Session management
- `app/api/routers/auth_mfa.py` — MFA endpoints
- `app/api/routers/leaves.py` — Leave API
- `app/api/routers/attendance.py` — Attendance API
- `app/api/routers/erp_attendance.py` — ERP attendance sync
- `app/api/routers/dashboard.py` — Dashboard API

### For Understanding Data Model
- `app/api/db/models.py` — All 28 tables

### For Understanding Frontend
- `app/web/app/layouts/default.vue` — Shell + nav gating
- `app/web/app/composables/useAuth.ts` — Auth state
- `app/web/server/api/hrms/[...path].ts` — BFF proxy
- `app/web/server/utils/hrms.ts` — Cookie/refresh logic

---

## PART 13: COMMON PATTERNS TO RECOGNIZE

### Pattern 1: Permission + Scope Gate
```python
@router.get("/...")
async def endpoint(
    current_user: User = Depends(require_permission("leave.approve")),
    session: AsyncSession = Depends(get_async_session),
):
    application = await service.repo.get_application_by_id(app_id)
    await require_employee_access(current_user, application.employee, "leave.approve", session)
    return await service.approve_leave(app_id, current_user.id)
```

### Pattern 2: Self-Service with allow_self
```python
await require_employee_access(current_user, employee, "leave.apply", session, allow_self=True)
```

### Pattern 3: Scope Resolution for List Endpoints
```python
scope = await _leave_management_scope(current_user, session)
if scope.self_only:
    employee_id = (await get_current_employee(current_user, session)).id
return await service.list_applications_page(
    employee_id=employee_id,
    unit_ids=None if scope.organization else scope.unit_ids,
    department_ids=None if scope.organization else scope.department_ids,
)
```

### Pattern 4: ERP-Only Endpoint
```python
@router.post("/integrations/erp/employees/{id}/password-reset",
    dependencies=[Depends(require_erp_scope("identity:write"))]
)
```

### Pattern 5: Idempotent ERP Upsert
```python
# Check erp_event_id or erp_*_id first, update if exists, create if not
```

### Pattern 6: Double-Entry Ledger
```python
# On allocation: credit ledger + upsert balance (same transaction)
# On application: debit ledger + update balance
# On cancellation: reversal ledger + reverse balance change
```

### Pattern 7: Single-Flight Refresh (BFF)
```typescript
const pending = inFlightRefreshes.get(token)
if (pending) return pending
// ... create promise, store in map, return
```

---

## PART 14: FRONTEND PAGE → API MAP

### 14.1 Page Routes and Their Backend Dependencies

| Frontend Page | Route | Backend Endpoint(s) | Permission Required |
|---------------|-------|---------------------|---------------------|
| Dashboard | `/` | `GET /dashboard/widgets`, `GET /dashboard/metrics` | Varies by widget |
| Attendance | `/attendance` | `GET /attendance/`, `GET /attendance/checkins` | `attendance.view*` |
| Leave | `/leaves` | `GET /leaves/`, `POST /leaves/`, `PATCH /leaves/{id}/approve` | `leave.*` |
| Employees | `/employees` | `GET /employees`, `GET /employees/{id}` | `employee.view` |
| Approvals | `/approvals` | Aggregated: leave + work arrangement + overtime pending | `leave.approve`, `work_arrangement.approve`, `overtime.approve` |
| Work Arrangements | `/work-arrangements` | `GET /work-arrangements/`, `POST /work-arrangements/` | `work_arrangement.*` |
| Overtime | `/overtime` | `GET /overtime/`, `POST /overtime/`, `PATCH /overtime/{id}/approve` | `overtime.*` |
| Shifts | `/shifts` | `GET /shifts/`, `GET /shifts/assignments/` | `shift.*` |
| Holidays | `/holidays` | `GET /holidays/`, `GET /holidays/lists/` | — (read-only mirror) |
| Organization | `/organization` | `GET /org/organization`, `GET /org/units`, `GET /org/departments` | `employee.view`, `designation.view` |
| Reports | `/reports` | `GET /reports/attendance`, `GET /reports/leave`, `GET /reports/overtime` | `reports.*` |
| Profile | `/profile` | `GET /users/me`, `PATCH /users/me` | `user.update` (self) |
| Settings | `/settings` | `GET /auth/sessions`, `POST /auth/session/refresh`, `POST /auth/mfa/*`, `POST /auth/change-password` | Authenticated |
| Notifications | `/notifications` | `GET /notifications/`, `POST /notifications/read-all` | — |
| Admin Login | `/admin/login` | `POST /auth/super-admin/login` | — |
| Forgot Password | `/forgot-password` | `POST /auth/password-recovery/start`, `POST /auth/password-recovery/verify`, `POST /auth/password-recovery/reset` | — |

### 14.2 API Proxy Routes (Browser → BFF → Backend)

All frontend API calls go through `server/api/hrms/[...path].ts` which prefixes with `/api/hrms/`:

```
Browser → Nuxt Server
  /api/hrms/auth/session/login      → POST /api/v1/auth/employee/login
  /api/hrms/auth/super-admin/login  → POST /api/v1/auth/super-admin/login
  /api/hrms/auth/session/refresh    → POST /api/v1/auth/session/refresh
  /api/hrms/auth/session            → DELETE /api/v1/auth/session
  /api/hrms/auth/sessions           → GET/DELETE /api/v1/auth/sessions...
  /api/hrms/auth/mfa/*              → POST /api/v1/auth/mfa/*
  /api/hrms/users/me                → GET /api/v1/users/me
  /api/hrms/leaves/*                → /api/v1/leaves/*
  /api/hrms/attendance/*            → /api/v1/attendance/*
  /api/hrms/employees/*             → /api/v1/employees/*
  /api/hrms/dashboard/*             → /api/v1/dashboard/*
  /api/hrms/notifications/*         → /api/v1/notifications/*
  /api/hrms/org/*                   → /api/v1/org/*
  ... (every /api/v1/* route)
```

---

## PART 15: DEBUGGING CHECKLIST

### When Login Fails
1. Check identity format: mobile must be E.164 (`+91...`) or username
2. Check throttle status: 5 failures on ip+account = 60s block
3. Check employee linkage: technical account without Employee row = 403
4. Check MFA: if enrolled, login returns challenge, not session
5. Check super admin: username only, no mobile/email

### When Permission Denied (403)
1. Check business role on Employee row: `business_role`, `access_scope`, `access_scope_id`
2. Check permission in effective_permissions(business_role)
3. Check row scope: does employee fall within access_scope?
4. Check allow_self for self-service operations
5. Remember: Super Admin has NO workforce row scope

### When Session Issues
1. Access token expiry: 15 min (business) / 5 min (privileged)
2. Refresh token expiry: 30 days outer bound
3. Idle timeout: 60 min (business) / 15 min (privileged) — checked on refresh
4. Absolute timeout: 12h (business) / 2h (privileged) — never extended
5. Replay detection: using rotated token revokes ALL sessions

### When ERP Sync Fails
1. Check HMAC signature: method + path + query + timestamp + nonce + body_hash
2. Check timestamp: within 5 minutes (ERP_SIGNATURE_MAX_AGE_SECONDS)
3. Check nonce: single-use, can't replay
4. Check client_id: must be in ERP_API_CLIENTS with valid secret (≥32 chars)
5. Check scopes: client must have required scope

---

## PART 16: KEY INSIGHTS FOR NEW DEVELOPERS

### 16.1 The Two Most Important Concepts

**1. Authentication ≠ Authorization ≠ Scope**
- Authentication: who are you? (login, session)
- Authorization: can you do this action? (permission code)
- Scope: which rows does this apply to? (SELF/DEPARTMENT/UNIT/ORGANIZATION)

These are resolved independently and all three must pass.

**2. ERP is Source of Truth for Master Data**
- HRMS is a reader/mirror for org structure, employees, shifts, holidays
- HRMS is the system of record for: leave applications/approvals, work arrangements, overtime approvals, attendance corrections (pending ERP ack)
- Writing to ERP-owned data returns 403 — this is intentional

### 16.2 Common Mistakes to Avoid

1. **Don't check roles in routers** — use `require_permission(code)` + `require_employee_access(user, employee, code, session)`
2. **Don't embed permissions in tokens** — they're re-resolved from DB every request for a reason
3. **Don't assume blank unit_id means organization** — organization HR must be explicit
4. **Don't write to ERP-owned tables from HRMS** — return 403 with explanation
5. **Don't cache permission decisions** — role changes must take effect immediately
6. **Don't log secrets** — tokens, passwords, TOTP seeds, recovery codes
7. **Don't skip throttling on auth endpoints** — all login/MFA/recovery paths are throttled

### 16.3 Where to Add New Features

| If adding... | Put it in... |
|--------------|--------------|
| New HTTP endpoint | `app/api/routers/*.py` |
| New business logic | `app/api/services/*.py` |
| New database query | `app/api/repositories/*.py` |
| New auth behavior | `app/api/core/*.py` (not services) |
| New Pydantic schema | `app/api/schemas/*.py` |
| New DB column/table | `app/api/db/models.py` + Alembic migration |
| New frontend page | `app/web/app/pages/*/` |
| New frontend component | `app/web/app/components/` |
| New TypeScript type | `app/web/shared/types/*.ts` |
| New BFF proxy route | Automatic via `[...path].ts` — no new file needed |

### 16.4 Testing New Features

1. **Backend:** Add test in `app/api/tests/test_*.py`
   - Use `conftest.py` fixtures for test database
   - Test permission gates: what happens with/without permission?
   - Test scope gates: what happens with different scopes?
   - Test domain rules: overlaps, thresholds, state transitions
2. **Frontend:** Add Playwright test if UI workflow is affected
3. **Run before committing:**
   ```bash
   # Backend
   cd app/api && uv sync && uv run pytest && uv run ruff check .
   
   # Frontend
   cd app/web && pnpm install && pnpm build && pnpm lint && pnpm typecheck
   ```

---

## APPENDIX A: PERMISSION CODE CATALOGUE

### Enforced Permissions (Actually Gate Behavior)

| Permission | Granted To | Gates |
|------------|------------|-------|
| `leave.apply` | BASE (all employees) | Apply for leave |
| `leave.cancel` | BASE | Cancel own leave |
| `leave.approve` | MANAGER, HR_ADMIN | Approve leave |
| `leave.reject` | MANAGER, HR_ADMIN | Reject leave |
| `leave.manage` | HR_ADMIN | HR leave management |
| `attendance.view` | HR_ADMIN, OWNER | View all attendance |
| `attendance.view_unit` | HR_ADMIN (unit), OWNER | View unit attendance |
| `attendance.view_department` | MANAGER, HR_ADMIN, OWNER | View dept attendance |
| `attendance.process` | HR_ADMIN | Run attendance processing |
| `attendance.correct` | HR_ADMIN | Submit attendance corrections |
| `employee.view` | MANAGER, HR_ADMIN, OWNER | View employees |
| `employee.create` | HR_ADMIN | Create employee (HRMS side) |
| `employee.update` | HR_ADMIN | Update employee |
| `employee.deactivate` | HR_ADMIN | Deactivate employee |
| `work_arrangement.apply` | BASE | Apply for work arrangement |
| `work_arrangement.cancel` | BASE | Cancel own arrangement |
| `work_arrangement.approve` | MANAGER, HR_ADMIN | Approve arrangements |
| `work_arrangement.reject` | MANAGER, HR_ADMIN | Reject arrangements |
| `work_arrangement.manage` | HR_ADMIN | HR arrangement management |
| `overtime.view_self` | BASE | View own overtime |
| `overtime.view_department` | MANAGER, HR_ADMIN | View dept overtime |
| `overtime.view` | OWNER | View all overtime |
| `overtime.approve` | MANAGER, HR_ADMIN | Approve overtime |
| `shift.view_self` | BASE | View own shift |
| `shift.assign` | HR_ADMIN | Assign shifts |
| `shift.update` | HR_ADMIN | Update shifts |
| `designation.view` | HR_ADMIN | View designations |
| `designation.create` | HR_ADMIN | Create designations |
| `designation.update` | HR_ADMIN | Update designations |
| `designation.delete` | HR_ADMIN | Delete designations |
| `reports.attendance` | MANAGER, HR_ADMIN, OWNER | Attendance reports |
| `reports.leave` | MANAGER, HR_ADMIN, OWNER | Leave reports |
| `reports.overtime` | HR_ADMIN, OWNER | Overtime reports |
| `reports.salary_cost` | HR_ADMIN | Salary cost reports |
| `reports.view` | HR_ADMIN, OWNER | General reports access |
| `dashboard.view_organization` | OWNER | Organization dashboard |
| `system.configure` | HR_ADMIN | System configuration |
| `audit.view` | HR_ADMIN | Audit log access |
| `user.view` | HR_ADMIN | View users |
| `user.create` | HR_ADMIN | Create users |
| `user.update` | HR_ADMIN | Update users |
| `user.deactivate` | HR_ADMIN | Deactivate users |
| `salary_cost.view_unit` | HR_ADMIN | Unit salary costs |
| `salary_cost.view_department` | HR_ADMIN | Dept salary costs |

### Technical Admin Permissions (Superuser Only)

| Permission | Gates |
|------------|-------|
| `technical.account.view` | View technical accounts |
| `technical.account.manage` | Manage technical accounts |
| `technical.system.view` | View system metrics |
| `technical.system.configure` | System configuration |
| `technical.audit.view` | Audit log access |

### Unenforced Permissions (Vocabulary Only)

These exist in code but don't currently gate any behavior:
- `employee.view_self`, `attendance.view_self`, `leave.view_self`
- `overtime.view_self`, `shift.view_self`
- `reports.view`, `reports.overtime`, `reports.salary_cost`
- `salary_cost.*`, `audit.view`, `user.*`
- `employee.update`, `employee.deactivate`, `overtime.view`

---

*This guide reflects the codebase as of the `development` branch. The canonical living document is `docs/system-architecture-and-flows.md`. For architecture changes, update that document in the same PR.*
