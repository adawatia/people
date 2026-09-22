# People HRMS — System Architecture, API & Role Flows

**Status:** living document · **Last verified against:** `development` branch, commit `63f00f1`
**Scope:** everything in this repository — `app/api/` (FastAPI backend) and `app/web/` (Nuxt frontend)

---

## 0. How to read this document

This is the single reference that explains **how the codebase is wired** (architecture), **how a request travels** (API flow), **what a user sees and can do** (UI flow), and **what happens end-to-end for each role** (login → daily work → approvals → ERP sync).

| Audience | Read first | Decisions you own |
|---|---|---|
| **Architecture lead** | §1, §2.1, §2.6, §5, §8, §9 | ERP vs HRMS ownership boundary, role/permission model, layering rules, the gaps in §8 |
| **Backend lead** | §2 (all), §4, §5, §7, §8 | Service/repo boundaries, transaction & idempotency behaviour, missing endpoints, test coverage |
| **Frontend lead** | §3 (all), §4, §8 | BFF proxy contract, session/refresh behaviour, nav gating model, broken UI actions in §8.1 |
| **Flow / integration engineer** | §2.8, §4.6, §5, §8.2 | ERP contract (idempotency keys, ack loop, ordering), reconciliation & retries |
| **UI/UX engineer** | §3.4, §3.5, §4.1–4.5, §8.1 | Information architecture per role, empty/error states, which actions are currently dead |
| **QA / test engineer** | §7, §5, §8 | Test-to-feature map, state-machine edge cases, regression list |
| **Product / delivery** | §1, §4, §8, §9 | Scope of "ERP is source of truth", which flows ship next |

> **How to keep this current:** when you add a router, a permission code, a page, or an ERP endpoint, update the corresponding table here. The tables in §2.9, §3.5, §6 and §10 are the ones that drift fastest.

---

## 1. System context

### 1.1 Two workspaces, one product

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Browser (desktop / tablet / mobile web)                                      │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ HTTPS  · httpOnly cookies (people_session, people_refresh)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ app/web — Nuxt 4 + Nitro (default :3000)                                     │
│  • App shell, pages, layouts, components, composables                        │
│  • BFF layer: server/api/hrms/[...path].ts proxies EVERY business call       │
│    (browser never holds a bearer token, never talks to FastAPI directly)     │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ Bearer <access token>  · NUXT_HRMS_API_BASE (default :8000)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ app/api — FastAPI (default :8000)  · all routes under /api/v1                │
│  routers/  → HTTP shape, auth dependencies, scoping entry point              │
│  services/ → domain rules, transactions, cross-entity side effects           │
│  repositories/ → focused queries & persistence primitives                    │
│  core/     → auth, RBAC, row-level access, settings, logging, audit, email    │
│  db/       → SQLAlchemy models + dev seed                                    │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ SQLAlchemy async (psycopg)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL (DATABASE_URL) + Alembic migrations (app/api/alembic/versions)    │
└──────────────────────────────────────────────────────────────────────────────┘
                ▲
                │ X-API-Key  · /api/v1/integrations/erp/**
┌───────────────┴──────────────────────────────────────────────────────────────┐
│ ERP (external system of record) — one-way authoritative writes INTO HRMS     │
│   employees · logins · units/departments/designations · shifts & assignments │
│   attendance records · holidays · overtime · leave balances                  │
│   ← HRMS publishes leave status changes for ERP to pull & acknowledge        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Run & verify

```bash
# backend (from app/api)
uv sync
uv run fastapi dev main.py          # http://localhost:8000  · /docs, /redoc, /openapi.json
uv run pytest                       # 15 test modules (see §7)
uv run ruff check .                 # 120-char line length

# frontend (from app/web)
pnpm install
pnpm dev                            # http://localhost:3000
pnpm build && pnpm lint && pnpm typecheck
```

### 1.3 Ownership boundary — the single most important rule

The API description in `app/api/main.py` states it plainly: *"ERP is the source of truth for employee and organization master data."* Everything else follows from that:

| Data | Owner | HRMS role |
|---|---|---|
| Organization, units, departments, designations | **ERP** | Read-only mirrors (`GET /org/**`) |
| Employees (profile, hierarchy, salary, status) | **ERP** | Read; operational fields only |
| Login accounts, usernames, mobile numbers, passwords | **HRMS** | Created for an employee at ERP request |
| Attendance punches, processed attendance | **ERP** | Ingest, store, reconcile |
| Shifts + employee shift assignments | **ERP** | Read + resolve windows |
| Holidays / weekly-offs | **ERP** | Read + resolve |
| Leave types, periods, allocations, balances | **ERP → HRMS** | Balances synced in; applications/approvals live in HRMS |
| Leave *status outcomes* | **HRMS → ERP** | Published on a change feed for ERP to pull & ack |
| Overtime records | **ERP** | Approve/decline inside HRMS |
| Work-from-home requests, leave requests | **HRMS** | Fully owned in HRMS |

Anything that is ERP-owned responds **`403` with an explanatory detail string** on the HRMS write path (deliberate, documented in code) rather than silently succeeding. See §8.1 for where the UI still offers those dead actions.

---

## 2. Backend architecture

### 2.1 Layer map and rules

| Layer | Location | Responsibility | Must never |
|---|---|---|---|
| **Routers** | `app/api/routers/*.py` | HTTP shape, request/response schemas, auth dependency wiring, scope resolution entry point, tag assignment | Contain business rules or raw SQL aggregates |
| **Services** | `app/api/services/*.py` | Domain invariants, state transitions, multi-entity side effects (attendance marking, ledger, balance), notifications | Know about HTTP (`HTTPException` is used, but not `Request`/`Response`) |
| **Repositories** | `app/api/repositories/*.py` | Named queries, existence checks, persistence primitives, eager-load options | Contain business policy |
| **Core** | `app/api/core/*.py` | Auth, RBAC, row-level scoping, settings, logging, audit, email, pagination helpers | Import services |
| **DB** | `app/api/db/models.py` | SQLAlchemy models, IST timestamps, constraints, sync columns | Contain queries |
| **Schemas** | `app/api/schemas/*.py` | Pydantic contracts for every request/response | Contain DB access |
| **Utils** | `app/api/utils/` | Background cleanup loop, number-to-words | — |

Module inventory:

| File | Purpose / notable content |
|---|---|
| `main.py` | App factory, lifespan, routers, CORS, middleware, custom OpenAPI security schemes, `/`, `/health`, `/db-health` |
| `core/auth.py` | fastapi-users wiring, `UserManager` (password policy, 3-way login lookup), JWT strategy (8 h), `FIXED_ROLE_PERMISSIONS`, `require_permission`, ERP API-key check, rate limiter |
| `core/rbac.py` | `DASHBOARD_WIDGETS` + `get_visible_widgets` (permission-filtered widget keys) |
| `core/employee_access.py` | `EmployeeAccessScope`, `get_permission_scope`, `require_employee_access` — **row-level** visibility |
| `core/attendance_access.py` | `require_hr_admin` (role-based, not permission-based), `require_hr_unit_access` |
| `core/audit.py` | `record_audit_event` → append-only `audit_logs` |
| `core/invitation.py` | 48 h invitation tokens, SHA-256 hashed at rest, single-use |
| `core/mobile.py` | `normalize_indian_mobile` → E.164 `+91…` (login identity + ERP ingest) |
| `core/pagination.py` | `PaginatedResponse[T]` |
| `core/settings.py` | Pydantic settings + `validate_runtime_secrets()` (refuses dev defaults outside development) |
| `core/logging.py` | Structured stdout/file logging, request-scoped events |
| `core/email.py` → `legacy/email.py` | SMTP sender + Jinja-less `.html`/`.txt` templates in `app/api/templates/email/` |
| `utils/notifications_cleanup.py` | Background retention loop (see §2.7.9) |

### 2.2 Request lifecycle

```
1. CORSMiddleware        allow_origins from CORS_ORIGINS + regex for localhost/127.0.0.1/10.x/192.168.x
2. SlowAPI rate limit     default 200/minute per client IP ("memory://" storage)
                          /health overridden to 10/minute
3. log_requests           request_started → request_completed (duration_ms, status, ip, UA)
                          exception path logs request_failed with stack trace
4. Auth dependency        fastapi_users.current_user(active=True)  → JWT (aud fastapi-users:auth)
                          OR  require_permission("code")            → 403 "Missing permission: code"
                          OR  verify_erp_api_key (X-API-Key, constant-time compare)
5. Scope resolution       get_permission_scope / require_employee_access → 403 on out-of-scope rows
6. Service call           domain rules + transaction
7. Response model         Pydantic serialization; HTTPException → {"detail": ...}
```

Notes that matter operationally:

* **Rate limiter is in-process memory.** Multiple API workers ⇒ per-worker limits. Move to Redis before horizontal scale.
* **JWTs are stateless and last 8 hours** for the login token, while browser sessions issue **15-minute** access tokens (§2.5.3). Revoking a refresh session does not invalidate an outstanding 8 h bearer token.
* Custom OpenAPI adds a `SuperAdminOAuth2` password flow and mirrors it onto every bearer-protected operation so Swagger can authorize both account types.

### 2.3 Configuration & startup

`core/settings.py` (env file `.env`, reference `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://dev:SuperAdmin@localhost:5432/hrms` | async driver; sync variant derived for Alembic |
| `JWT_SECRET` | dev default | must be replaced outside development |
| `ENVIRONMENT` | `development` | `development/dev/test` relax startup rules |
| `ERP_API_KEY` | `""` (empty) | **empty means every ERP call is rejected** — no dev fallback |
| `BOOTSTRAP_SEED_DATA` | `false` | opt-in seeding in non-dev environments |
| `SUPER_ADMIN_*` | admin@hrms.com / superadmin / SuperAdmin@123 | bootstrap technical account |
| `MAIL_*`, `FRONTEND_URL` | Zoho SMTP, `http://192.168.103.20:3000` | invitation / reset / alert emails |
| `CORS_ORIGINS` | localhost:5173, 8081, 3000, 19006 | Expo/mobile origins included |
| `LOG_*` | stdout console, file appender opt-in | keep `LOG_TO_FILE=false` in dev (watcher loop) |
| `TIMEZONE` (documented) | `Asia/Kolkata` | code uses `ZoneInfo("Asia/Kolkata")` via `now_ist()` |

**Lifespan (`main.py`)** — in order: log start → `create_db_and_tables()` **only in development** → `ensure_seed_data()` in dev or when `BOOTSTRAP_SEED_DATA=true` → start `notification_cleanup_loop()` as a task → on shutdown cancel the task cleanly.

`validate_runtime_secrets()` runs at import-time startup of `main.py` and raises `RuntimeError` outside development if `JWT_SECRET`, `DATABASE_URL`, `SUPER_ADMIN_PASSWORD` are still defaults, or `ERP_API_KEY` is empty.

**Schema management:** Alembic (`app/api/alembic/versions/`, 8 migrations). `create_all` is a development convenience only. Production releases must run `alembic upgrade head` first.

### 2.4 Data model

28 tables. Grouped by concern, with the fields that drive behaviour:

**Identity & access**
| Table | Key points |
|---|---|
| `users` | `user_id` PK, unique `username`, unique nullable `mobile_number` (E.164), `must_change_password`, `created_by`, invitation metadata (hash, sent/expires/used), fastapi-users fields (`is_active`, `is_verified`, `is_superuser`) |
| `auth_sessions` | Only the **SHA-256 hash** of the refresh token; `expires_at` (30 d), `last_used_at`, `revoked_at`, `replaced_by_id` (rotation chain) |
| `audit_logs` | Append-only: actor, action, entity, `filters_json`, `request_id`, `ip_address` |

**Org structure (ERP-owned)**
`organizations` (single row enforced by unique `singleton_key`), `units`, `departments`, `designations`, `department_approvers` (`approver_type`: LEAVE / SHIFT / EXPENSE / WORK_ARRANGEMENT).

**Workforce**
`employees` — the operational core. Role lives here (`role`: `EMPLOYEE` | `DEPARTMENT_MANAGER` | `HR_ADMIN` | `ORGANIZATION_OWNER`), plus `user_id` (login), `unit_id`, `department_id`, `designation_id` + cached `designation` string, `reporting_manager_id` (self-FK), `shift_id` (ERP default shift), `status` (`ACTIVE`/…), `overtime_eligible`, `monthly_salary`, exit fields.
`employee_work_histories` — transfers/promotions history.

**Scheduling**
`shifts` — start/end, `grace_minutes`, `break_minutes`, `is_cross_midnight`, and the Frappe-HR-style thresholds: `begin_check_in_before_minutes`, `allow_check_out_after_minutes`, `late_entry_grace_minutes`, `early_exit_grace_minutes`, `half_day_threshold_hours`, `absent_threshold_hours`, `enable_auto_attendance`.
`shift_assignments` — dated windows (`effective_from`/`effective_to`), `status`, `assigned_by`.
`holiday_lists` (with `weekly_off_day`, `is_default`) and `holidays` (unique `erp_holiday_id`, `is_weekly_off`, `is_organization_wide`).

**Leave**
`leave_periods`, `leave_types` (`is_paid`, `annual_allocation`, `max_consecutive_days`, `carry_forward`, `include_holidays`), `leave_allocations`, `leave_ledger_entries` (double-entry: positive = credit, negative = debit; types `ALLOCATION` | `APPLICATION` | `REVERSAL` | `EXPIRY`), `leave_balances` (`allocated`, `used`, `pending`), `leave_applications` (status + full cancellation workflow columns + `erp_event_id` / `erp_sync_status` / `erp_synced_at`).

**Attendance**
`attendance_records` — unique (`employee_id`, `attendance_date`); status, punch in/out, `worked_minutes`, `overtime_minutes`, `late_minutes`, `early_exit_minutes`, `source`, unique `erp_record_id`, `sync_status`.
`attendance_punches` — raw device/app punches with resolved `shift_start`/`shift_end`, `is_processed`, geolocation.
`attendance_discrepancies`, `attendance_correction_requests` (requested punches, `PENDING_ERP_RECONCILIATION` sync status, unique `erp_correction_id`).

**Overtime** — `overtime_records` (`calculated_minutes`, `approved_minutes`, status, `erp_event_id`, `source`) and `overtime_approvals` (audit of each approval action).

**Work arrangements** — `work_arrangement_requests` (type `WORK_FROM_HOME` | `OUT_DUTY` | `FIELD_WORK` | `OFFICE`), status, actioner, rejection reason, plus read-only `employee_name`/`employee_code` properties.

**Notifications** — `notifications` (title, message, `notification_type`, `user_id` **or** `target_role`, `reference_id`/`reference_type`, `link`, `is_read`).

Conventions: all timestamps are `DateTime(timezone=True)` defaulted by `now_ist()` (Asia/Kolkata); leave quantities use `Numeric(5,1)` (half days); money `Numeric(12,2)`; ERP-synced entities carry an `erp_*` id column for idempotency.

### 2.5 Authentication architecture

#### 2.5.1 Two login doors (same users table)

| Endpoint | Tag | Identity accepted | Extra rule |
|---|---|---|---|
| `POST /api/v1/auth/employee/login` | `auth-employee` | Indian mobile (any input is normalized to E.164) or email or username | **must** have a linked `Employee`, else `403 "This account is not linked to an employee"` |
| `POST /api/v1/auth/super-admin/login` | `auth-super-admin` | username **only** (rejects `@`, digits, `+`) | must have `is_superuser`, else `403` |

Both are OAuth2 password-form endpoints and both return `{access_token, token_type, must_change_password}`. `UserManager.authenticate()` is overridden to resolve `email → username → normalized mobile`, and it performs a **dummy hash** for unknown users to flatten timing differences.

#### 2.5.2 Password policy (enforced on register, change, and HR/ERP temporary-password set)

1. ≥ 12 characters
2. must contain upper, lower, digit, special character
3. must not contain the user's email local part / username / first / last name (≥ 3 chars)
4. `zxcvbn` score ≥ 3 with those personal inputs supplied
Failure raises `InvalidPasswordException`; routers convert it to `400 {"detail": "…reason…"}`.

#### 2.5.3 Token & session model

| Artifact | TTL | Stored where | Notes |
|---|---|---|---|
| Login bearer token (JWT, `HS256`, aud `fastapi-users:auth`) | 8 h | returned to client only | stateless; used once by the BFF to create a session |
| Session access token | 15 min | BFF cookie `people_session` | minted by `/auth/session` |
| Refresh token (opaque, `token_urlsafe(48)`) | 30 d | SHA-256 hash in `auth_sessions`; raw in BFF cookie `people_refresh` | rotated on every use |

`POST /auth/session` (create) · `POST /auth/session/refresh` (rotate) · `DELETE /auth/session` (revoke).

**Rotation & replay defence:** presenting an already-rotated (revoked) refresh token is treated as theft — **all** of that user's live sessions are revoked and `401 "Refresh token reuse detected"` is returned. The new session is linked via `replaced_by_id`.

**Bulk revocation:** setting an HR/ERP temporary password revokes every active `AuthSession` for that user (`_reset_password`) and sets `must_change_password = true`.

#### 2.5.4 ERP machine authentication

`X-API-Key` header validated with `secrets.compare_digest` against `settings.erp_api_key`; empty/mismatched ⇒ `403 Could not validate API KEY`. There is **no** fallback key outside development, and the key must never reach a browser.

### 2.6 Authorization: roles, permissions, and row scope

Two orthogonal mechanisms — get this right or you will mis-scope a feature:

| Mechanism | Question it answers | Implemented in |
|---|---|---|
| **Permission** (`require_permission`, `hasPermission`) | *May this user perform this kind of action at all?* | `core/auth.py` → `FIXED_ROLE_PERMISSIONS` |
| **Scope** (`EmployeeAccessScope`, `get_permission_scope`, `require_employee_access`) | *Which employees/rows does it apply to?* | `core/employee_access.py` |

#### 2.6.1 Role → scope resolution

```
user.is_superuser            → organization scope (and full HR_ADMIN permission set)
role ORGANIZATION_OWNER      → organization scope
role HR_ADMIN                → unit scope        ({their unit_id})
role DEPARTMENT_MANAGER      → department scope  ({their department_id})
role EMPLOYEE (or no profile)→ empty scope
                               …except allow_self=True short-circuits when
                               employee.user_id == user.id
```

`require_employee_access(user, employee, code_or_tuple, session, allow_self=…)` merges the scope of several permission codes, so `("attendance.view_self", "attendance.view_unit")` grants access if *any* code covers the row. Routes commonly fall back to "if the caller has no management scope, restrict the query to their own employee_id" (`leaves`, `attendance`, `work-arrangements`, `overtime`, `shifts`).

#### 2.6.2 Fixed role → permission matrix (source of truth: `core/auth.py`)

| Permission | EMPLOYEE | DEPT MANAGER | HR ADMIN | ORG OWNER |
|---|:--:|:--:|:--:|:--:|
| `employee.view_self` | ✅ | ✅ | — | — |
| `employee.view` | — | ✅ | ✅ | ✅ |
| `employee.create` / `employee.update` / `employee.deactivate` | — | — | ✅ | — |
| `attendance.view_self` | ✅ | ✅ | — | — |
| `attendance.view` / `view_unit` / `view_department` | — | department | ✅ all + unit + dept | ✅ all + unit + dept |
| `attendance.process` / `attendance.correct` | — | — | ✅ | — |
| `leave.apply` / `leave.view_self` / `leave.cancel` | ✅ | ✅ | ✅ (cancel) | — |
| `leave.approve` / `leave.reject` / `leave.manage` | — | approve/reject | ✅ all | — |
| `work_arrangement.apply` / `view_self` / `cancel` | ✅ | ✅ | cancel | — |
| `work_arrangement.approve` / `reject` | — | ✅ | ✅ | — |
| `work_arrangement.manage` | — | — | ✅ | — |
| `overtime.view_self` | ✅ | ✅ | — | — |
| `overtime.view_department` / `overtime.approve` | — | ✅ | approve + dept | view + dept |
| `overtime.view` | — | — | — | ✅ |
| `shift.view_self` | ✅ | ✅ | — | — |
| `shift.assign` / `shift.update` | — | — | ✅ | — |
| `designation.view` | — | — | ✅ | — |
| `designation.create/update/delete` | — | — | ✅ | — |
| `reports.attendance` / `reports.leave` | — | ✅ | ✅ | ✅ |
| `reports.view` / `reports.overtime` / `reports.salary_cost` | — | — | ✅ | view + overtime |
| `salary_cost.view_unit` / `view_department` | — | — | ✅ | — |
| `system.configure` / `audit.view` | — | — | ✅ | — |
| `dashboard.view_organization` | — | — | — | ✅ |
| `user.view/create/update/deactivate` | — | — | ✅ | — |

**Caveat:** several granted codes are never enforced by the API — `employee.view_self`, `attendance.view_self`, `attendance.correct`, `leave.view_self`, `overtime.view_self`, `overtime.approve`, `shift.view_self`, `shift.assign`, `shift.update`, `reports.view`, `reports.overtime`, `reports.salary_cost`, `salary_cost.*`, `audit.view`, `user.*`, `employee.update`, `employee.deactivate`. They are forward-compatible vocabulary today; only the codes referenced in §2.9 gate real behaviour (full list in Appendix A).

Derived rules worth remembering:

* **Super Admin ⇒ exactly the HR_ADMIN permission set** (`get_user_permissions` short-circuits). There is no superuser-only permission.
* **A user with no `Employee` row ⇒ EMPLOYEE permission set.** Safe default; also means a "technical" account that is not a superuser sees only self-service.
* Permissions are **read from the DB on every request** (`get_user_permissions` queries the employee row) — changing `Employee.role` takes effect on the next call, but the *client's cached permission list* is only refreshed on `/users/me`.

#### 2.6.3 Dashboard widget gating

`core/rbac.py` maps widget keys to a permission (or `None` = always visible):

| Widget key | Gate |
|---|---|
| `my_profile`, `my_leave_balance` | always |
| `pending_approvals`, `team_leave_requests` | `leave.approve` |
| `attendance_overview` | `attendance.view_department` |
| `unit_overview` | `employee.view` |
| `organization_overview` | `dashboard.view_organization` |
| `system_health` | `system.configure` |

`GET /dashboard/widgets` returns the visible keys; superusers get all. Note the **UI does not currently consume `/dashboard/widgets`** — `pages/index.vue` branches on `role` directly (§8.1 A9).

### 2.7 Domain services

#### 2.7.1 Attendance engine (`services/attendance_service.py`)

* **Ingest**: `POST /attendance/checkins` and `/checkins/bulk` now return **403** — punches are ERP-supplied. Raw punches still exist in the model and repository (`AttendancePunchRepository.find_duplicate`) for the ERP ingest path.
* **Processing** (`process_attendance_for_employee_date` / `process_attendance_batch`, exposed as `POST /attendance/process` with `attendance.process`):
  1. Resolve the shift window for the date (dated assignment beats the ERP default shift; handles cross-midnight and `begin_check_in_before_minutes`).
  2. Classify the day: `WEEKLY_OFF`, `HOLIDAY`, `ON_LEAVE` (from approved leave), `WORK_FROM_HOME` (from approved arrangement) before computing work time.
  3. Compute `worked_minutes` minus `break_minutes`; derive `late_minutes` (beyond `late_entry_grace_minutes`) and `early_exit_minutes`.
  4. Apply thresholds: `< absent_threshold_hours` → `ABSENT`; `< half_day_threshold_hours` → `HALF_DAY`; otherwise `PRESENT`. A single missing punch → `MISSED_PUNCH`. Unpunched day → `WEEKLY_OFF` / `ON_LEAVE` / `ABSENT` as applicable.
  5. Overtime minutes beyond shift end feed `overtime_records`.
* **Corrections**: `POST /attendance/corrections` requires the **HR_ADMIN role** (`require_hr_admin`, plus `require_hr_unit_access` unit check) and always writes `sync_status = PENDING_ERP_RECONCILIATION`. Approve/reject endpoints exist but return **403 "ERP confirmation is the attendance correction approval"** — HRMS raised the request, ERP confirms it.
* **Reads**: `GET /attendance/`, `/records/{id}`, `/employee/{id}/calendar`, `/employee/{id}/summary`, `/corrections` — all scoped through `ATTENDANCE_READ_PERMISSIONS = (attendance.view, attendance.view_unit, attendance.view_department)` with `allow_self=True`.

#### 2.7.2 Leave engine (`services/leave_service.py`, 730 lines — the largest service)

Config: `create_period`, `create_type`, `update_type`, `allocate_leaves` (writes an `ALLOCATION` ledger credit and upserts `leave_balances`).

**Apply** (`apply_leave`):
1. `to_date >= from_date`; employee exists.
2. Reject any overlap with an existing `PENDING`/`APPROVED` application.
3. Resolve the active `leave_period` for `from_date`.
4. `calculate_leave_days` — half day ⇒ `0.5`; `include_holidays` ⇒ calendar days; otherwise count days excluding holidays **and** weekly-offs.
5. Enforce `max_consecutive_days`.
6. Paid types: check `allocated - used - pending`; insufficient ⇒ `400 "Insufficient leave balance"`.
7. Insert `PENDING` application and increment `balance.pending`.

**Approve** (`approve_leave`): blocks **self-approval**; moves `pending → used`; writes an `APPLICATION` **debit** ledger entry; marks every day in range as `ON_LEAVE` / `HALF_DAY` on `attendance_records` (creating rows when absent, skipping holidays when `include_holidays` is false); sets `erp_event_id = LEAVE-{id}-APPROVED` and `erp_sync_status = PENDING`.

**Reject**: releases `pending`, records `rejection_reason`, emits `LEAVE-{id}-REJECTED`.

**Cancel / early return** (via `PATCH /leaves/{id}/cancel` → `request_leave_cancellation`):
| Case | Behaviour |
|---|---|
| `PENDING` | immediate `CANCELLED`, `pending` released, event `LEAVE-{id}-CANCELLED` |
| `APPROVED`, start date in the future | immediate `CANCELLED`, `used` refunded, `REVERSAL` ledger credit, attendance rows reverted (delete if unpunched, else `PRESENT`) |
| `APPROVED`, leave already started (today inside range) | must go through an **early-return request**: requires a reason and `effective_date == today`, status → `CANCELLATION_PENDING` for an approver |
| `APPROVED`, fully in the past | `409` — "Completed leave cannot be cancelled; ask HR to create an attendance correction instead" |

**Approve/reject the early return** (`approve_leave_cancellation`, `reject_leave_cancellation`): recomputes the refundable days from `cancellation_effective_date → to_date`, refunds `used`, writes a `REVERSAL` credit, marks the already-taken days as `PRESENT`/`HALF_DAY`, and releases the remainder. Self-approval is blocked.

**Reads**: `GET /leaves/` (filter by employee/status/date, scoped by `LEAVE_MANAGEMENT_PERMISSIONS = (leave.manage, leave.approve, leave.reject)`, `allow_self`), `GET /leaves/{id}`, `GET /leaves/balance/employee/{id}` (self-service allowed via `leave.apply`).

#### 2.7.3 Work arrangements (`services/work_arrangement_service.py`)

* Only `WORK_FROM_HOME` is accepted today; other types ⇒ `400 "Only work-from-home requests are currently supported"`. The UI's `typeConfig` knows all four labels, but its request form is hard-coded to `WORK_FROM_HOME`, so no dead option is reachable from the UI today.
* Creation rejects overlapping arrangements **and** overlapping pending/approved leave.
* Approval marks each day `WORK_FROM_HOME` on `attendance_records` (creating rows as needed) and blocks self-approval.
* Cancelling an approved request deletes the auto-created attendance rows **only if they carry no punches**.

#### 2.7.4 Shifts (`services/shift_service.py`)

* `get_shift_window(shift, date)` builds concrete start/end datetimes and flags `is_cross_midnight` (end < start ⇒ +1 day).
* `resolve_shift_for_timestamp` / `get_shift_window_for_date`: **dated `shift_assignments` win over `Employee.shift_id`**, with `effective_from ≤ date ≤ effective_to`.
* `get_employee_shift_schedule(employee_id, for_timestamp)` returns `assigned_shift` + `upcoming_shift` in **one batched context** (`load_schedule_context`, `_window_for_date`) — this batching was introduced to remove per-date N+1 lookups (regression-tested in `tests/test_shift_schedule_batching.py` and used by the dashboard).
* Assignment creation prevents overlapping assignments per employee (`find_overlapping_assignment`).
* Public router is **read-only** (see §8.1 A1).

#### 2.7.5 Holidays (`services/holiday_service.py`)

`create_holiday_list` can auto-generate a year of `is_weekly_off` rows from `weekly_off_day`; `resolve_holiday_list_for_employee` picks unit list → default list; `is_holiday_or_weekly_off` and `get_holidays_in_range` (with `skip_weekly_offs`) are the primitives used by the leave calculator and the attendance engine. Public API is read-only (`GET /holidays/lists`, `GET /holidays/lists/{id}`).

#### 2.7.6 Overtime (`services/overtime_service.py`)

`list_overtime`, `get_overtime`, `get_overtime_summary` (month filtering, approved minutes only), `approve_overtime` / `reject_overtime` with self-approval prevention and an `overtime_approvals` audit row. **The approve/reject service methods are not exposed by any router** (§8.1 A2).

#### 2.7.7 Reports (`services/report_service.py`)

* `GET /reports/attendance-matrix?year&month` → day-by-day matrix + aggregates, scoped: OWNER = whole org, HR_ADMIN = forced to own unit, DEPARTMENT_MANAGER = forced to own department.
* `GET /reports/leave-summary?year` → allocated/used/pending/available per employee, same scoping rule.

#### 2.7.8 Notifications & audit

* `routers/notifications.py` exposes `create_notification()` for services plus `GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}/read`, `POST /notifications/mark-all-read`.
* Visibility filter: superuser sees all; everyone else sees `user_id == me` **or** `target_role ∈ {ALL, STAFF, HR, MANAGER, EMPLOYEE}` **or** `notification_type == "system"`.
* `mark_notification_read` forbids marking another user's notification.
* Audit: `GET /dashboard/owner` and `/dashboard/owner/exceptions` write `ORGANIZATION_DASHBOARD_VIEWED` / `ORGANIZATION_EXCEPTION_DRILLDOWN_VIEWED` rows with filters, request id and IP.

#### 2.7.9 Background work

`utils/notifications_cleanup.py` starts after a 60-second delay and repeats every 6 hours:
1. delete everything older than 7 days,
2. delete read notifications older than 3 days,
3. keep at most the 50 newest notifications per `user_id`/`target_role` partition (window function).

### 2.8 ERP integration contract (`/api/v1/integrations/erp/**`, all `X-API-Key`)

| Method & path | Purpose | Idempotency / notes |
|---|---|---|
| `POST /employees` | Create employee **and** linked login atomically (`phone_number` + strong `initial_password` required) | `409` on duplicate code/mobile/email/username |
| `PATCH /employees/{id}` | Update employee + sync `first_name`/`last_name`/`mobile_number` onto the login | partial updates (`exclude_unset`) |
| `PATCH /employees/{id}/deactivate` / `/activate` | Lifecycle with optional `exit_date`/`exit_reason` | — |
| `POST /employees/{id}/password-reset` (in `auth_login.py`) | Set temporary password | revokes all refresh sessions; sets `must_change_password` |
| `PATCH /organization` | Update the single organization record | — |
| `POST/PATCH/DELETE /units`, `/departments`, `/designations` | Master-data CRUD | deletes blocked by dependent-count checks |
| `POST /shifts`, `PATCH /shifts/{id}` | Shift definitions | — |
| `POST /shifts/assignments`, `/assignments/bulk`, `PATCH /assignments/{id}/cancel` | Assign/rotate shifts | overlap prevention; batching added for bulk |
| `POST /attendance/records`, `/records/bulk` | Ingest **processed** attendance | `erp_record_id` makes re-sends idempotent; per-item `accepted`/`duplicates`/`failed` result |
| `POST /holidays/bulk` | Sync holidays per unit | keyed by `erp_holiday_id` |
| `POST /overtime/records/bulk` | Sync overtime records | keyed by `erp_event_id` |
| `GET /leaves/changes?since&limit` | **ERP pulls** leave outcomes (`erp_sync_status != ACKNOWLEDGED`) | ordered by `actioned_at`; `has_more` cursor |
| `POST /leaves/changes/ack` | ERP acknowledges event ids | marks `ACKNOWLEDGED` + `erp_synced_at`; returns `unknown[]` |
| `POST /leaves/balances`, `/balances/bulk` | Sync leave balances (allocated/used/pending) | per-item `accepted`/`failed`; upserts by employee + leave code + year |

**Ingestion discipline:** bulk endpoints are intentionally *partial-success* — a bad row lands in `failed[]` with its error string and the rest are committed. Callers must inspect the result, not just the HTTP status.

**Outbound discipline:** HRMS never calls the ERP. Leave approvals/rejections/cancellations queue an event that the ERP polls. Until the ERP acks, `erp_sync_status` stays `PENDING`; rows are visible in `GET /leaves/changes` indefinitely.

### 2.9 Public API index (grouped by tag)

Every tag below is also an OpenAPI tag declared in `main.py`. Auth column: **E** = employee login, **SA** = super admin, **Any** = any active user, **perm(x)** = `require_permission`, **role:HR** = `require_hr_admin`, **ERP** = API key.

| Group | Endpoint | Auth | Scope rule |
|---|---|---|---|
| **account** | `GET /users/me` | Any | returns permissions + employee_id/code + role |
| | `GET /users/me/permissions` | Any | — |
| **auth** | `POST /auth/employee/login` | public | mobile/email/username |
| | `POST /auth/super-admin/login` | public | username only |
| | `POST /auth/change-password` | Any | clears `must_change_password` |
| | `PATCH /auth/super-admin/username` | SA | conflict-checked |
| | `POST /auth/hr/employees/{id}/password-reset` | role:HR + unit check | revokes sessions |
| | `GET /auth/invitation/validate`, `POST /auth/invitation/set-password` | public | 48 h, single-use token |
| **auth-session** | `POST /auth/session`, `POST /auth/session/refresh`, `DELETE /auth/session` | Any / public / public | refresh rotation + replay kill |
| **dashboard** | `GET /dashboard/metrics` | Any | self metrics; unit/dept metrics when the caller has `leave.approve`/`attendance.approve_correction`/`employee.view` |
| | `GET /dashboard/widgets` | Any | permission-filtered keys |
|  | `GET /dashboard/technical-metrics` | SA | counts only; no audit row is written |
| | `GET /dashboard/owner`, `/owner/exceptions` | perm(`dashboard.view_organization`) | organization-wide + audit row |
| **employees** | `GET /employees/` | Any | OWNER all · HR unit · DM department · EMPLOYEE self only |
| | `GET /employees/{id}`, `/work-history` | Any | `employee.view` + `allow_self` |
| | `POST /employees/onboard` | perm(`employee.create`) | **returns 410** (ERP-only) |
| **designations / org / units / departments** | `GET` list + detail | Any | read-only mirrors |
| **holidays** | `GET /holidays/lists`, `GET /holidays/lists/{id}` | Any | read-only |
| **shifts** | `GET /shifts/`, `/assignments`, `/assignments/{id}`, `/employee/{id}/schedule`, `/{id}` | Any | EMPLOYEE is forced to self; HR/owner see all |
| **attendance** | `GET /attendance/`, `/records/{id}`, `/employee/{id}/calendar`, `/employee/{id}/summary`, `/checkins`, `/corrections` | Any | read-permission scope + `allow_self` |
| | `POST /attendance/checkins`, `/checkins/bulk` | — | **403 — ERP supplied** |
| | `POST /attendance/process` | perm(`attendance.process`) | HR unit scope |
| | `POST /attendance/corrections` | role:HR + unit | → `PENDING_ERP_RECONCILIATION` |
|  | `PATCH /attendance/corrections/{id}/approve\|reject` | perm(`attendance.approve_correction`) | **403 — ERP confirms** |
| **leaves** | `GET /leaves/periods`, `/types`, `/types/{id}`, `/balance/employee/{id}`, `/`, `/{id}` | Any | self-service via `leave.apply`/`allow_self`; management scope otherwise |
| | `POST /leaves/`, `PATCH /leaves/{id}/cancel` | Any | self via `leave.apply`/`leave.cancel` |
| | `POST /leaves/periods`, `/types`, `PATCH /types/{id}` | perm(`leave.manage`) | HR |
|  | `PATCH /leaves/{id}/approve\|reject` | perm(`leave.approve`/`reject`) | scope + no self-approval |
|  | `PATCH /leaves/{id}/cancellation/approve\|reject` | perm(`leave.approve`/`reject`) | scope + no self-approval |
| **work-arrangements** | `GET /` , `GET /{id}` | Any | management scope else self |
| | `POST /`, `PATCH /{id}/cancel` | Any | self via apply/cancel |
|  | `PATCH /{id}/approve\|reject` | perm(`work_arrangement.approve`/`reject`) | scope + no self-approval |
| **overtime** | `GET /overtime/`, `/{id}`, `/employee/{id}/summary` | Any | OWNER/DM/HR scope, self fallback |
| **reports** | `GET /reports/attendance-matrix`, `/leave-summary` | perm(`reports.attendance`/`reports.leave`) | role-forced scope inside the route |
| **notifications** | `GET /notifications`, `/unread-count`, `PATCH /{id}/read`, `POST /mark-all-read` | Any | user + role broadcasts |
| **health** | `GET /health` (10/min), `GET /db-health`, `GET /` | public | DB probe + uptime |

**Error conventions:** `400` invalid state/policy · `401` bad credentials/expired token · `403` missing permission, out-of-scope row, or ERP-owned action · `404` not found · `409` conflict (duplicate, started leave, balance race) · `410` retired endpoint · `422` validation (Pydantic) · `503` (db-health). `detail` is a string, or an object `{code, reason}` for password-policy failures surfaced by `legacy/email.py`-era endpoints.

---

## 3. Frontend architecture

### 3.1 Stack and structure

Nuxt 4 (`app/` directory layout) with `@nuxt/ui`, `@nuxt/icon`, `@nuxt/image`, `nuxt-auth-utils`, `nuxt-echarts` (only `BarChart`, `LineChart`, `PieChart` + a small component set are registered — keeps the owner dashboard bundle small).

```
app/web
├─ app/
│  ├─ app.vue, app.config.ts          # root + UI theme config
│  ├─ assets/css/main.css             # People design tokens (--people-*)
│  ├─ layouts/auth.vue                # split-screen unauthenticated shell (currently unused: login.vue sets layout:false)
│  ├─ layouts/default.vue             # sidebar + topbar + bottom mobile nav + nav gating
│  ├─ middleware/auth.global.ts       # route guard (session required, public paths)
│  ├─ composables/useAuth.ts          # shared auth state, permissions, login/logout
│  ├─ composables/useHrmsApi.ts       # typed wrapper over /api/hrms/** (+ 401 → /login)
│  ├─ components/dashboard/OwnerDashboard.vue
│  ├─ components/attendance/AttendanceStatusBadge.vue
│  └─ pages/…                         # see §3.5
├─ server/
│  ├─ api/session/login.post.ts       # login → cookies → /users/me
│  ├─ api/session/me.get.ts           # current user
│  ├─ api/session/index.delete.ts     # revoke + clear cookies
│  ├─ api/hrms/[...path].ts           # single BFF proxy with transparent refresh
│  └─ utils/hrms.ts                   # apiUrl, SESSION_COOKIE, REFRESH_COOKIE, upstreamError
└─ shared/types/*.ts                  # 11 type modules shared by app & server
```

### 3.2 The BFF session proxy (why the browser never sees a token)

Cookies (all `httpOnly`, `sameSite=lax`, `secure` outside dev):

| Cookie | TTL | Content |
|---|---|---|
| `people_session` | 15 min (8 h only between login and session creation) | access JWT |
| `people_refresh` | 30 days | opaque refresh token |

**Login** (`POST /api/session/login`):
```
browser ──▶ Nitro: POST /api/session/login {identity, password, accountType}
   Nitro ──▶ FastAPI POST /auth/(employee|super-admin)/login   (form-urlencoded)
   Nitro ──▶ FastAPI POST /auth/session  (Bearer login token)  → access 15 m + refresh 30 d
   Nitro ──▶ FastAPI GET  /users/me      (Bearer access)
   Nitro ──▶ browser: Set-Cookie people_session + people_refresh, body = CurrentUser
```

**Any business call** (`/api/hrms/<path>`):
```
1. forward method/query/body with Authorization: Bearer <people_session>
2. on 401 and a refresh cookie exists (and path ≠ auth/session/refresh):
     POST /auth/session/refresh → rotate cookies → retry the original request once
3. still 401 → delete both cookies and surface the upstream error
```
This means **token refresh is transparent to every page**: a 15-minute access token never logs a user out during a working session, and a replayed refresh token (rotation violation) does — correctly — kill the session.

**Logout** (`DELETE /api/session`): revoke server-side refresh, clear cookies, `204`.

**Error translation** (`server/utils/hrms.ts → upstreamError`): FastAPI `detail` (string or `{reason}`) becomes the Nitro `statusMessage`, so pages can display `error.data.statusMessage` verbatim. Default status when upstream status is unknown: `502`.

### 3.3 Auth state and route guard

`useAuth()` stores `auth-user`, `auth-initialized`, `auth-loading` in `useState` (SSR-safe, shared by all components) and exposes:

| Member | Behaviour |
|---|---|
| `displayName`, `initials` | display helpers |
| `hasPermission(code)` | true when `is_superuser` **or** `permissions` contains the code |
| `hasRole(role)` | true when `is_superuser` **or** `user.role === role` |
| `fetchUser(force = false)` | one `GET /api/session/me` per request; errors ⇒ signed-out state (never throws) |
| `login(payload)` | posts to the BFF, sets the user, exposed `loading` |
| `logout()` | revokes session, clears state, `navigateTo('/login')` |

`middleware/auth.global.ts` runs on every navigation: `await fetchUser()` → unauthenticated and not a public path ⇒ `/login?redirect=<fullPath>`; authenticated visiting `/login` ⇒ `/`. Public paths: `/login`, `/forgot-password`, `/reset-password`, `/invitation`, `/verify-email`, `/auth/invitation` (only the first exists as a page today).

`useHrmsApi().request()` additionally hard-handles `401` mid-session: clears `auth-user` and redirects to `/login?redirect=<current>`, then rethrows.

### 3.4 Navigation & visibility — the two-gate model

`layouts/default.vue` builds `navItems`, and each item may declare **both** `roles` and `permissions`. An item is visible when the **role gate passes AND at least one permission in the list is held** (when specified):

| Nav item | roles | permissions (any-of) | Effective audience |
|---|---|---|---|
| Dashboard | — | — | everyone |
| Employees | DM, HR, OWNER | `employee.view` | DM, HR, OWNER |
| Attendance | — | — | everyone (self-scoped by the API) |
| Leave | — | — | everyone |
| Work arrangements | — | — | everyone |
| Overtime | — | — | everyone |
| Approvals | DM, HR | `leave.approve`, `attendance.approve_correction`, `work_arrangement.approve` | DM, HR |
| Shifts | HR | `shift.assign`, `shift.update` | HR |
| Holidays | — | — | everyone |
| Organization | HR | `system.configure`, `designation.view`, `employee.view` | HR |
| Reports | DM, HR, OWNER | `reports.attendance`, `reports.leave` | DM, HR, OWNER |
| System administration (link) | superuser only | — | Super Admin |

Super Admin gets **only** Dashboard + System administration — the business nav is replaced, because master data lives in ERP.

Mobile: the 4 first non-dashboard visible items become the bottom bar, plus Profile; the sidebar collapses into a drawer.

**Important consequence:** the nav gate is *presentation only*. Every endpoint re-checks permission and row scope (§2.6), so a hidden link is convenience, never security. Conversely, an item without a permission list (Attendance, Leave, Work arrangements, Overtime, Holidays) is visible to plain employees and must be self-service-safe on the server — which it is today.

### 3.5 Page inventory → API map

| Page | Primary endpoint(s) | Key UI capabilities | Broken/limited (see §8) |
|---|---|---|---|
| `pages/login.vue` | `POST /api/session/login` | employee⇄super-admin toggle, password reveal, `redirect` honouring, inline error text | no forgot-password page (copy says "Password reset: contact HR") |
| `pages/index.vue` | `dashboard/metrics`, `dashboard/technical-metrics` (SA only), `dashboard/owner` via component | role-specific hero copy, 4 KPI cards, shift + today's attendance cards, pending-approvals list (managers), owner analytics branch | ignores `/dashboard/widgets` |
| `pages/employees/index.vue` | `employees/`, `org/units`, `org/departments`, `designations/` | paginated directory, filters, activate/deactivate, delete | PATCH/DELETE endpoints **do not exist** → 405 |
| `pages/employees/[id].vue` | `employees/{id}`, `employees/{id}/work-history` | profile, org placement, work history | — |
| `pages/attendance/index.vue` | `attendance/employee/{id}/calendar`, `…/summary`, `attendance/corrections` | month calendar, status pie, summary tiles, correction request dialog | dialog POSTs require **HR_ADMIN**; employee submits get 403 |
| `pages/leaves/index.vue` | `leaves/`, `leaves/types`, `leaves/balance/employee/{id}` | apply leave (type/date/reason/half-day), balance cards, own history, cancel/early-return | — |
| `pages/work-arrangements/index.vue` | `work-arrangements/` | request WFH, list, cancel | only WFH accepted server-side |
| `pages/approvals/index.vue` | `attendance/corrections`, `attendance/records/{id}`, `leaves/?status=PENDING`, `leaves/?status=CANCELLATION_PENDING`, `work-arrangements/?status=PENDING` | tabs per queue (permission-driven), approve, reject with reason modal | attendance tab approve → 403 ERP; no overtime tab |
| `pages/shifts/index.vue` | `shifts/`, `shifts/assignments`, `org/units`, `employees/` | shift definitions + assignments tables, "New shift"/"Assign shift" dialogs | POST endpoints **do not exist** → 405 |
| `pages/holidays/index.vue` | `holidays/lists`, `org/units` | calendar + holiday list viewer | `canManage` hard-coded `false` (correct, ERP-owned) |
| `pages/organization/index.vue` | `org/organization`, `org/units`, `org/departments`, `designations/` | tabs per entity, enable/disable, delete | PATCH/DELETE are ERP-only → 405 |
| `pages/overtime/index.vue` | `overtime/`, `overtime/employee/{id}/summary` | own + scoped overtime records and monthly summary | read-only (no approve path) |
| `pages/reports/index.vue` | `reports/attendance-matrix`, `reports/leave-summary` | month picker, attendance matrix, leave summary; tabs gated by permission | — |
| `pages/notifications.vue` | `notifications`, `notifications/{id}/read`, `notifications/mark-all-read` | list, read, mark-all | — |
| `pages/profile.vue` | `users/me` (via composable) | identity, role label, employee code | — |
| `pages/settings.vue` | `auth/change-password`, `auth/super-admin/username` | password change for everyone; username change for superuser only | — |

### 3.6 Design system & responsive rules

* Tokens in `app/assets/css/main.css` (`--people-canvas`, `--people-surface`, `--people-border`, `--people-blue/mint/lavender/peach/yellow` + `-ink` pairs) drive every card/icon tone; `people-card`, `people-icon`, `people-icon--*` are the shared class contracts.
* Every page header follows: eyebrow label → `h2` title → one-line subtitle → right-aligned primary action.
* Skeletons (`USkeleton`) for first paint, `UAlert` "taking a short break" pattern with a retry action for failed dashboards, `UToast` for action results, `confirm()` for destructive actions.
* Breakpoints: single column → `sm:grid-cols-2` → `xl:grid-cols-3/4`; sidebar is fixed ≥ `lg`, drawer below; bottom nav < `lg`; `min-h-11` tap targets; safe-area padding on mobile nav.
* Dark mode via `UColorModeButton`; charts use `nuxt-echarts` with SVG/canvas renderers registered in `nuxt.config.ts`.

---

## 4. End-to-end flows

Each flow lists **trigger → UI → HTTP → backend path → DB effects → notifications/audit → failure modes**.

### 4.0 F0 — Session bootstrap (everything starts here)

Every page load and navigation runs the same preamble:

```
1. middleware/auth.global.ts → useAuth().fetchUser()
2. GET /api/session/me → Nitro reads people_session cookie → GET /users/me (Bearer)
3. FastAPI: current_user(active=True) → User row
4. GET /users/me also: get_user_permissions(user)  [Employee.role → FIXED_ROLE_PERMISSIONS]
                       + employee lookup → employee_id, employee_code, role
5. Nitro returns CurrentUser → useState('auth-user') → nav + page permission gates resolve
6. Page then fires its own /api/hrms/** calls (SSR `useAsyncData`), each subject to transparent refresh
```
Failure modes: no cookie → `401` → `/login?redirect=…` · access expired + refresh valid → silent rotate (one retry) · refresh replayed → all sessions revoked → `401` → login.

### 4.1 F1 — EMPLOYEE (self-service day)

**Login.** `/login`, employee tab, mobile `9876543210` + password.
`POST /api/session/login` → FastAPI normalizes to `+919876543210` → `UserManager.authenticate` → `Employee` link check → JWT → `POST /auth/session` → `GET /users/me`.
Result: role `EMPLOYEE`, permissions = self-service set (`employee.view_self`, `attendance.view_self`, `leave.apply`, `leave.view_self`, `leave.cancel`, `work_arrangement.*` self-service, `shift.view_self`, `overtime.view_self`).

**Dashboard (`/`).** `GET /dashboard/metrics`:
* `has_mgr_access` = false (no `leave.approve`/`employee.view`) ⇒ unit metrics stay 0 and `pendingApprovals` is empty.
* Employee block fills: `currentShift`/`upcomingShift` from the batched schedule context, today's status + punch in/out, month present/absent/leave/holiday counts, monthly OT hours, and `leaveBalances` computed as `allocated - used - pending`.
* UI: "Here's your workday at a glance" + 4 KPI cards + *Your shifts* + *Today* cards. No approvals card.

**Apply leave (`/leaves`).** `POST /leaves/` with `employee_id`, type, dates, reason (allow_self passes because it is their own row).
Backend: overlap check → period lookup → working-day maths (skips holidays/weekly-offs) → `max_consecutive_days` → paid balance check → `PENDING` insert + `balance.pending += days`.
**No notification is emitted on apply** (§8.2) — the approver only sees it in queues.
UI: optimistic refresh of "My requests", balance cards now show the reduced available figure.

**Work from home (`/work-arrangements`).** `POST /work-arrangements/` → overlap + leave-conflict checks → `PENDING`.
On approval, each day becomes `WORK_FROM_HOME` in attendance, so the calendar stops showing absent.

**Cancel / early return (`/leaves`).** `PATCH /leaves/{id}/cancel`:
* pending ⇒ gone immediately, `pending` released.
* approved, future ⇒ instant cancel + `REVERSAL` ledger credit + attendance rows reverted.
* approved, already started ⇒ becomes `CANCELLATION_PENDING` (reason + today's date required) and waits for the manager; the UI labels the toast accordingly.

**Attendance (`/attendance`).** `GET /attendance/employee/{id}/calendar` + `/summary` + `attendance/corrections` → month grid, status pie, tiles.
⚠️ Tapping **Request correction** POSTs to `POST /attendance/corrections`, which requires the `HR_ADMIN` **role** → `403 "HR Admin access required"` for an employee today (§8.1 A3).

**Overtime (`/overtime`).** `GET /overtime/` self-scoped + monthly summary (approved minutes only). Read-only.

**Notifications (`/notifications`).** `GET /notifications` (user + role broadcasts), `PATCH …/{id}/read`, `POST …/mark-all-read`; server prunes with the retention rules in §2.7.9.

**Security (`/settings`).** `POST /auth/change-password` → policy validated → hash replaced, `must_change_password = false`. Note: existing 8 h/session tokens are *not* revoked on password change (§8.3).

### 4.2 F2 — DEPARTMENT_MANAGER (approve & report for one department)

**Login/Dashboard.** Same door; `hasPermission('leave.approve')` and `employee.view` make it a "manager".
`GET /dashboard/metrics` → `has_mgr_access = true`; scope = **their department** (`emp.role == DEPARTMENT_MANAGER` ⇒ `dept_scope_ids`), thus: headcount, today's attendance breakdown, attendance rate, today/month OT hours, pending leave + correction counts (excluding self), and up to 5 items *each* from leave, correction, overtime and work-arrangement queues merged into `pendingApprovals` with `type`, employee name/code, department, detail, `timeAgo`.
UI: 4 KPI cards (department members, present, on leave, needs attention) + *Pending approvals* card linking to `/approvals`.

**Approvals (`/approvals`).** Tabs are permission-driven: `attendance.approve_correction` (see gap), `leave.approve` (+`leave.reject` for the reject button), `work_arrangement.approve`.
* Leave queue loads `PENDING` **and** `CANCELLATION_PENDING` in parallel and picks the right endpoint per row (`/approve` vs `/cancellation/approve`).
* Approve ⇒ attendance rows become `ON_LEAVE`/`HALF_DAY`, ledger debit, `erp_event_id` queued for ERP, balance `pending → used`.
* Reject ⇒ modal with mandatory reason → `PATCH …/reject` → `pending` released.
* Self-approval is impossible: the service returns `400` even if the UI were bypassed.

**Reports (`/reports`).** Tabs by permission; the route **forces** `department_id` for a DM, so a DM cannot widen scope by passing `unit_id`.

**People.** `GET /employees/` is silently limited to their department (route logic), and `GET /employees/{id}` outside the department returns `403 "You do not have access to this employee"`.

### 4.3 F3 — HR_ADMIN (unit operations)

**Dashboard.** Scope = **their unit** (`unit_scope_ids`). KPI labels switch to "Unit members"; same 4 cards, but `pendingApprovals` includes unit-wide leave/correction/overtime/WFH items minus their own.

**Employees (`/employees`).** Unit-limited directory with search/filters, pagination (`page_size` ≤ 100), detail page with work history. Provisioning is ERP-only: `POST /employees/onboard` returns `410`, and the page's own activate/deactivate/delete buttons hit non-existent routes (§8.1 A1).

**Attendance (`/attendance`).** Read scope covers `attendance.view`, `view_unit`, `view_department`; can run the engine with `POST /attendance/process` (`attendance.process`) for an authorized unit/employee, and can raise corrections for records inside their unit (`require_hr_admin` + `require_hr_unit_access` → `403 "Employee is outside your unit"` otherwise).

**Shifts (`/shifts`).** Definitions + assignments are read from HRMS; creating them is ERP-only, so the "New shift"/"Assign shift" buttons currently 405 (§8.1 A4). Employees' schedules come from ERP assignments, so this page is effectively a viewer today.

**Password operations.** `POST /auth/hr/employees/{id}/password-reset` sets a temporary password (policy-validated), sets `must_change_password`, and revokes all of the user's refresh sessions. This is the supported "reset a locked-out employee" path; the login page tells users to contact HR for exactly this reason.

**Organization (`/organization`) / Holidays (`/holidays`).** Viewer-only by design; writes live under `/integrations/erp/**`.

**Reports.** Attendance matrix and leave summary forced to their unit; HR is the only role with `salary_cost.*`, `reports.overtime`, `system.configure`, `audit.view`.

### 4.4 F4 — ORGANIZATION_OWNER (analytics only)

**Dashboard (`/`)** renders `components/dashboard/OwnerDashboard.vue` instead of the standard stats grid, and never the approvals card.

```
GET /dashboard/owner            (from_date, to_date, unit_id)
  → permission check dashboard.view_organization
  → OwnerDashboardService.dashboard(): date-range defaulting, org rollups, pending-requests count,
    approved overtime, per-unit rows
  → record_audit_event(ORGANIZATION_DASHBOARD_VIEWED, filters, request_id, ip)

GET /dashboard/owner/exceptions (kind, target_date, unit_id, page, page_size)
  → OwnerDashboardService.exceptions(): drill-down rows, paginated (≤100)
  → record_audit_event(ORGANIZATION_EXCEPTION_DRILLDOWN_VIEWED, …)

GET /org/units                  → unit filter options
```
Owner permissions deliberately exclude every approval and self-service permission (`test_organization_owner_has_analytics_but_no_operational_approval_permissions` asserts this). Reports give them whole-organization attendance/leave/overtime.

### 4.5 F5 — SUPER_ADMIN (technical administrator)

1. `/login` → **Super Admin login** toggle → username only (`mobile`/`email` inputs are rejected with `400 "This sign-in uses a username"`), must pass `is_superuser` or `403`.
2. `/` shows the technical workspace: `GET /dashboard/technical-metrics` → users (non-superuser), active employees, active units/departments/designations; plus "ERP ownership" explainer cards. Nav = Dashboard + System administration.
3. `/settings` → `PATCH /auth/super-admin/username` (uniqueness checked) and `POST /auth/change-password`.
4. Permissions resolve to the full HR_ADMIN set, and `get_permission_scope` returns **organization** scope — a superuser can read any employee/attendance/leave record. Scope checks are the only guard, so treat this account as break-glass.
5. Bootstrap: `db/seed.py` creates/repairs this account from `SUPER_ADMIN_*` env values on startup when seeding runs; `reset_super_admin_password.py` exists for recovery.

### 4.6 F6 — ERP machine flows

| # | Flow | Calls | Notes |
|---|---|---|---|
| 1 | **Provision an employee + login** | `POST /integrations/erp/employees` | phone + strong `initial_password` mandatory; atomic employee+login; `409` on duplicates; `must_change_password = true` so the first human login is forced to change it |
| 2 | **Daily attendance ingest** | `POST /integrations/erp/attendance/records/bulk` | one row per employee/date; `erp_record_id` idempotent; inspect `accepted/duplicates/failed` |
| 3 | **Shift & roster sync** | `POST /integrations/erp/shifts`, `/shifts/assignments/bulk`, `PATCH /shifts/assignments/{id}/cancel` | overlap prevention; dated assignments override `Employee.shift_id` |
| 4 | **Holiday calendar sync** | `POST /integrations/erp/holidays/bulk` | keyed by `erp_holiday_id`; weekly-off generation lives in `holiday_admin` lists |
| 5 | **Overtime sync** | `POST /integrations/erp/overtime/records/bulk` | keyed by `erp_event_id`; HRMS owns approve/decline |
| 6 | **Leave outcome pull + ack** | `GET /integrations/erp/leaves/changes?since=&limit=` → `POST /leaves/changes/ack` | HRMS-produced events (`LEAVE-{id}-APPROVED/REJECTED/CANCELLED`) remain `PENDING` until acked; `has_more` signals another page |
| 7 | **Leave balance sync** | `POST /integrations/erp/leaves/balances/bulk` | ERP is the balance authority; upserts `allocated/used/pending` per employee+code+year |
| 8 | **Password reset from ERP** | `POST /integrations/erp/employees/{id}/password-reset` | revokes sessions, forces change |

---

## 5. State machines & invariants

```
LeaveApplication
  PENDING ──approve──▶ APPROVED ──cancel(future)──▶ CANCELLED
     │                    │
     │                    └──cancel(started)──▶ CANCELLATION_PENDING ──approve──▶ CANCELLED
     │                                                    └────reject────▶ APPROVED
     ├──reject──▶ REJECTED
     └──cancel(pending)──▶ CANCELLED
  Invariants: no overlapping PENDING/APPROVED. Paid types move pending→used on approve.
              APPROVED ⇒ ledger debit + attendance ON_LEAVE/HALF_DAY + erp_event PENDING.
              Cancel of approved ⇒ REVERSAL credit + attendance revert (delete if unpunched).

WorkArrangementRequest   PENDING ──▶ APPROVED ──cancel──▶ CANCELLED   |   PENDING ──▶ REJECTED
  Invariant: no overlap with another arrangement or with PENDING/APPROVED leave.

AttendanceRecord  ATTENDANCE_PENDING ──process──▶ PRESENT | ABSENT | HALF_DAY | MISSED_PUNCH
                  WEEKLY_OFF | HOLIDAY | ON_LEAVE (leave) | WORK_FROM_HOME (WFH)
  One row per (employee, date) — unique constraint. ERP ingest can overwrite status and set ERP_CONFIRMED.

AttendanceCorrectionRequest  status: PENDING (one per attendance_record) ──┬─▶ APPROVED (service path)
                                                                    └─▶ REJECTED (service path)
  sync_status starts at PENDING_ERP_RECONCILIATION; ERP confirmation is the real gate.
  HTTP approve/reject endpoints are disabled by design (§8.1 A3), so in production the row leaves
  PENDING only when ERP confirms it.

ShiftAssignment  ACTIVE ──cancel──▶ CANCELLED   ·   no overlapping ACTIVE windows per employee.

OvertimeRecord  PENDING ──approve/reject──▶ (service only; no HTTP surface today)
```

---

## 6. Cross-cutting concerns

| Concern | Where | Behaviour |
|---|---|---|
| **Correlation** | `core/logging.py`, `log_requests` | structured events; `x-request-id` header is stored on audit rows |
| **Audit** | `core/audit.py` | only owner dashboards/drill-downs today; columns exist for far wider use |
| **Rate limiting** | `core/auth.py` | 200/min default, `/health` 10/min, in-process storage |
| **CORS** | `main.py` | explicit origin list + LAN regex; `allow_credentials=True` |
| **Secrets** | `core/settings.py` | startup refusal of dev defaults outside development; ERP key fails closed |
| **Email** | `legacy/email.py` + `templates/email/` | password reset, invitation, verification, email-changed alert (HTML + text). The invitation *send* path is wired in the email service but **no router currently sends invitations**, so the `/auth/invitation/*` endpoints are reachable only for users created by another path (§8.3) |
| **Timezone** | `db/models.now_ist()` | IST defaulting/`onupdate` for every timestamp |
| **Background jobs** | `utils/notifications_cleanup.py` | retention loop; no other scheduled work (attendance processing is on-demand) |
| **Observability** | `GET /health`, `GET /db-health` | uptime, DB reachability, `response_time_ms` |

---

## 7. Testing & verification

`uv run pytest` in `app/api` — 15 modules, mostly async end-to-end service/API tests against a real (test) database.

| Test module | Covers |
|---|---|
| `test_main.py` | root + health endpoints |
| `test_auth_setup.py` | limiter wiring, user schemas, OWNER permission boundary, invalid-login robustness, CORS preflight |
| `test_invitation_flow.py` | invitation token creation/hashing/validation, password policy (`None` guard) |
| `test_email_service.py` | MIME construction, STARTTLS, reset/invitation/verification/email-changed templates |
| `test_employee_access.py` | permission scope from fixed role, org scope, self-access, out-of-scope rejection |
| `test_milestone_1.py` | designation CRUD, employee profile + hierarchy |
| `test_milestone_2.py` | shifts (night shift), assignment overlap, cross-midnight window, holiday lists/weekly offs, punch ingest + dedupe |
| `test_milestone_3.py` | attendance processing: full day, late/early exit, half-day/absent thresholds, missed punch, unpunched weekly-off/leave/absent, correction workflow |
| `test_milestone_4.py` | leave period/type, allocation + ledger credit, holiday-aware day count, insufficient balance, approval ledger debit + attendance marking |
| `test_milestone_5.py` | WFH creation/overlap, approval + attendance marking, rejection & cancellation |
| `test_milestone_6.py` | attendance matrix report, leave balance summary report |
| `test_notifications.py` | notification lifecycle |
| `test_audit_and_workflows.py` | self-approval prevention (leave/correction/overtime/WFH), early-return day accounting, overtime self-approval + monthly summary filtering, WFH-aware processor, org CRUD validation, detail endpoints, notification + manager dashboard |
| `test_shift_schedule_batching.py` | batched schedule context equals per-date resolution, fallback outside context, upcoming search + schema, single-query employee shift listing |
| `test_migration_setup.py` | Postgres config + Alembic files present |

Frontend: `pnpm typecheck` + `pnpm lint` only (no component/E2E framework yet — a stated gap in `AGENTS.md`).

---

## 8. Gaps, mismatches, and risks

These are verified against the current code and are the highest-value item in this document for leads: **each one is a decision waiting to be made.**

### 8.1 Frontend ↔ backend mismatches (dead UI actions)

| # | Symptom | Root cause | Severity | Decision owner |
|---|---|---|---|---|
| **A1** | Employees page "activate/deactivate" and "delete" fail | `routers/employees.py` exposes only `GET /`, `POST /onboard` (410), `GET /{id}`, `GET /{id}/work-history`. Lifecycle writes exist only at `/integrations/erp/employees/{id}/deactivate` and `…/activate`. Delete exists only in `EmployeeService.delete_employee` (unused by any router) | High | Backend + Frontend lead |
| **A2** | Overtime can never be approved in the product | `OvertimeService.approve_overtime/reject_overtime` are unreachable: `routers/overtime.py` is read-only and the Approvals page has no overtime tab even though DM/HR hold `overtime.approve` | High | Product + Backend lead |
| **A3** | "Request correction" in Attendance fails for employees; Approvals → Attendance approve always fails | `POST /attendance/corrections` requires the **HR_ADMIN role**; the `approve` and `reject` endpoints return `403 "ERP confirmation is the attendance correction approval"`. The Approvals UI still calls them and shows a success toast path | High | Product (governance) + Frontend lead |
| **A4** | Shifts page create/assign fail | `routers/shifts.py` is read-only; writes live at `/integrations/erp/shifts/**` | Medium | Backend lead |
| **A5** | Organization page enable/disable/delete fail | `org/units`, `org/departments` and `designations/` routers expose GET only; writes are ERP-only | Medium | Frontend lead |
| **A6** | Holidays create/add buttons | Hidden by `canManage = false` (correct today) — the code remains and will 405 if ever enabled | Low | Frontend lead |
| **A7** | `attendance.approve_correction` is **held by nobody** | The code is referenced by the attendance router, the Approvals page, and the nav gate but is absent from every role set in `FIXED_ROLE_PERMISSIONS` — so even Super Admin (HR_ADMIN set) cannot satisfy it | High | Architecture lead |
| **A8** | `POST /attendance/checkins` + `/checkins/bulk` are 403 stubs | Intentional (ERP supplies punches) but the punch ingestion path is therefore untested through HTTP; publishing them for ERP would be cleaner than a separate ERP route | Low/Medium | Architecture lead |
| **A9** | Dashboard widget API is unused | `GET /dashboard/widgets` exists and is permission-aware while `pages/index.vue` hard-codes role branches, duplicating the gating logic in two places | Medium | Frontend lead |
| **A10** | Invitation UI missing | `/auth/invitation/*` + email templates exist, `middleware` lists `/invitation` and `/auth/invitation` as public, but no page/route exists and no router calls `create_invitation_for_user` | Medium | Product + Frontend lead |

### 8.2 Functional gaps (backend behaviour)

* **No notification is created for any workflow** — `create_notification` is only used by tests. Applying/approving/rejecting leave or WFH notifies nobody in-app; approvers rely on dashboard/queue polling.
* **`department_approvers` is decorative** — the table exists but no leave/WFH/shift/expense routing consults it; approvals are driven purely by role + unit/department scope.
* **Attendance processing is manual** — no scheduler calls `process_attendance_batch`; someone (or a cron outside this repo) must POST `/attendance/process`.
* **Overtime never reaches attendance end-to-end in-product**: ERP bulk-syncs records; there is no HRMS-computed-to-approve path exposed.
* **`leave.manage` grants allocation/type/period writes but allocation has no HTTP endpoint for org-wide bulk runs** — it is service-level only (`LeaveService.allocate_leaves`), exercised by tests.
* **`attendance_discrepancies`** is modelled and seeded but never written by the engine.

### 8.3 Security & correctness notes

* **Session vs token TTL mismatch.** A logged-in browser holds a 15-minute access token (good), but the login-issued JWT is 8 h and remains valid even after logout/refresh revocation, because JWT validation is stateless (`core/auth.py`) — the only compensating control is that clients never see it (BFF). Treat any leaked bearer token as valid for up to 8 h.
* **Password change does not revoke sessions** (`auth_login.change_password`): other refresh sessions keep working.
* **Refresh endpoint is unauthenticated by design** and protected only by the opaque token hash; brute force is infeasible, but there is no per-IP rate limit tighter than the global 200/min.
* **Super Admin has organization-wide read scope** via `get_permission_scope`; production posture depends on keeping that account break-glass only.
* **Anonymous `/health`** leaks DB reachability + uptime (rate-limited to 10/min).
* `ensure_permission(email, path, method)` in `core/auth.py` returns `bool(email)` for everything — dead/placeholder authorization helper; do not build on it.
* Seed defaults (`SuperAdmin@123`, dev JWT secret) are guarded by `validate_runtime_secrets()` **only** when `ENVIRONMENT` is not development — a mis-set `ENVIRONMENT` silently accepts them.

---

## 9. Decision register (for architecture / backend / frontend leads)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | **Is this "employees read-only + ERP writes" a temporary migration state or the target?** | (a) target — delete dead UI actions; (b) temporary — implement HRMS write endpoints guarded by `employee.update` | Pick explicitly, then make §8.1 A1/A4/A5 consistent with it. If (a): remove the buttons so users never see 405s |
| D2 | **Attendance correction governance** | (a) ERP-only confirmation (current server behaviour) — remove approve/reject from UI and stop offering employee submission; (b) allow employee submission + manager approval inside HRMS, ERP reconciles async | (b) matches the product's own permissions and queue UI, but requires deciding who wins conflicts with ERP. Ship (a) as the interim truthful UI |
| D3 | **Overtime approval surface** | (a) add `PATCH /overtime/{id}/approve` and `/reject` + an Approvals tab + notifications; (b) leave overtime read-only | (a) — the service, permissions, and months of summary UI already exist; it is the cheapest complete workflow |
| D4 | **Notifications on workflow events** | (a) emit on apply/approve/reject/cancel to the actor + approver + employee; (b) keep polling dashboards | (a) — `create_notification` already exists; wire it in the four services and reuse `link`/`reference_id` |
| D5 | **Approver routing** | (a) keep role+scope routing; (b) use `department_approvers` | Decide before exposing more approval types; today the table is misleading |
| D6 | **`attendance.approve_correction`** | (a) add it to DEPARTMENT_MANAGER + HR_ADMIN; (b) remove the code and gate everything on `attendance.correct` + role checks | Whichever you choose, remove the current impossible state in §8.1 A7 |
| D7 | **Access-token TTL policy** | (a) keep 8 h login JWT + 15 min session access; (b) shorten the login JWT to 15 min and issue sessions from it; (c) add a JWT denylist/jti check on logout | (b) or (c) to close the §8.3 revocation gap |
| D8 | **Scheduler** | (a) external cron calling `/attendance/process`; (b) in-process loop like notifications cleanup; (c) Celery/APScheduler | (b) for now (one fewer moving part, matches existing precedent), (c) before horizontal scale |
| D9 | **Rate limiting & sessions at scale** | (a) in-memory limiter + DB sessions (today); (b) Redis for both | (b) is required the moment you run more than one API worker |
| D10 | **Frontend test strategy** | (a) keep lint/typecheck only; (b) add component tests for the approval queue + login; (c) Playwright E2E over the BFF proxy | (b) now, (c) when D1/D2 stabilise the action surface |
| D11 | **Invitations** | (a) finish the invitation UX (page + send on ERP create, replacing temporary passwords); (b) drop the invitation code path | (a) — templates and token lifecycle are already built and tested |
| D12 | **Docs ownership** | Keep §2.9/§3.5/§8 tables updated in the PR template | Assign a reviewer per area (backend/frontend lead) |

---

## 10. Appendices

### A. Permission catalog (48 codes in `FIXED_ROLE_PERMISSIONS` — EMPLOYEE 10, DEPT MANAGER 20, HR ADMIN 38, ORG OWNER 11)

`employee.view_self`, `employee.view`, `employee.create`, `employee.update`, `employee.deactivate`,
`user.view`, `user.create`, `user.update`, `user.deactivate`,
`attendance.view_self`, `attendance.view`, `attendance.view_unit`, `attendance.view_department`, `attendance.process`, `attendance.correct`,
`leave.apply`, `leave.view_self`, `leave.cancel`, `leave.approve`, `leave.reject`, `leave.manage`,
`work_arrangement.apply`, `work_arrangement.view_self`, `work_arrangement.cancel`, `work_arrangement.approve`, `work_arrangement.reject`, `work_arrangement.manage`,
`overtime.view_self`, `overtime.view_department`, `overtime.view`, `overtime.approve`,
`shift.view_self`, `shift.assign`, `shift.update`,
`designation.view`, `designation.create`, `designation.update`, `designation.delete`,
`reports.view`, `reports.attendance`, `reports.leave`, `reports.overtime`, `reports.salary_cost`,
`salary_cost.view_unit`, `salary_cost.view_department`,
`system.configure`, `audit.view`, `dashboard.view_organization`

**Checked in the API but granted to no role:** `attendance.approve_correction` (§8.1 A7) — the only dead-end code.

**Granted to some role but never enforced in the API** (safe to keep as forward-compatible vocabulary, hazardous to treat as a security control):
`user.view`, `user.create`, `user.update`, `user.deactivate`, `employee.update`, `employee.deactivate`, `employee.view_self`, `attendance.view_self` *(docstring mention only)*, `attendance.correct`, `leave.view_self`, `overtime.view_self`, `overtime.approve`, `shift.view_self`, `shift.assign`, `shift.update`, `reports.view`, `reports.overtime`, `reports.salary_cost`, `salary_cost.view_unit`, `salary_cost.view_department`, `audit.view`.

*Frontend-only gates:* `shift.assign` (nav + Shifts page) is not checked by any route — which is why the Shifts page renders create buttons whose endpoints do not exist (§8.1 A4).

*Enforced today:* `employee.view`, `employee.create`, `attendance.view/view_unit/view_department`, `attendance.process`, `leave.apply/approve/reject/cancel/manage`, `work_arrangement.apply/view_self/approve/reject/cancel/manage`, `overtime.view/view_department`, `reports.attendance/reports.leave`, `dashboard.view_organization`, `system.configure` (dashboard widget gating).

### B. Database tables (28)

`users`, `auth_sessions`, `audit_logs`, `notifications`,
`organizations`, `units`, `departments`, `designations`, `department_approvers`,
`employees`, `employee_work_histories`,
`shifts`, `shift_assignments`, `holiday_lists`, `holidays`,
`leave_periods`, `leave_types`, `leave_allocations`, `leave_ledger_entries`, `leave_balances`, `leave_applications`,
`work_arrangement_requests`,
`attendance_records`, `attendance_punches`, `attendance_discrepancies`, `attendance_correction_requests`,
`overtime_records`, `overtime_approvals`

### C. Environment variables (backend)

`DATABASE_URL`, `POSTGRES_HOST/PORT/USER/PASSWORD/DB`, `JWT_SECRET`, `ENVIRONMENT`, `ERP_API_KEY`, `API_KEY`, `BOOTSTRAP_SEED_DATA`, `ORGANIZATION_NAME/CODE`, `TIMEZONE`, `CORS_ORIGINS`, `SUPER_ADMIN_EMAIL/USERNAME/PASSWORD/FIRST_NAME/LAST_NAME`, `MAIL_SERVER/PORT/USERNAME/PASSWORD/FROM`, `MAIL_STARTTLS`, `MAIL_SSL_TLS`, `USE_CREDENTIALS`, `VALIDATE_CERTS`, `FRONTEND_URL`, `LOG_LEVEL`, `LOG_FORMAT`, `LOG_TO_FILE`, `LOG_DIR`, `LOG_FILE_NAME`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`. Frontend: `NUXT_HRMS_API_BASE` (default `http://127.0.0.1:8000`).

### D. Glossary

| Term | Meaning |
|---|---|
| **BFF** | Backend-for-frontend: `server/api/**` in Nuxt that owns cookies and proxies to FastAPI |
| **ERP** | External system of record for workforce master data and raw attendance |
| **Punch** | Raw check-in/out event; **Record** is the processed per-day attendance row |
| **Scope** | Row-level visibility (`organization` / `unit` / `department` / self) derived from role |
| **Permission** | Coarse capability code checked by `require_permission` |
| **Ledger** | Double-entry leave transaction log (credit = allocation/reversal, debit = application) |
| **Early return** | Cancelling the remaining days of an already-started approved leave (`CANCELLATION_PENDING`) |
| **Ack loop** | ERP pulls `/leaves/changes` then `POST /leaves/changes/ack`; unacked events stay `PENDING` |
| **Cross-midnight shift** | Shift whose end time is before its start time (window rolls into the next day) |
