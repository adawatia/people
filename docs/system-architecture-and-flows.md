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
| `core/auth.py` | fastapi-users wiring, `UserManager` (password policy, 3-way login lookup, dummy hash for unknown users), JWT strategy, `BASE_EMPLOYEE_PERMISSIONS` + `ROLE_PERMISSIONS` + `effective_permissions`, the compatibility `FIXED_ROLE_PERMISSIONS` view, `require_permission`, ERP API-key check, generic rate limiter |
| `core/tokens.py` | The only place credentials are minted/hashed: opaque refresh secrets (`token_urlsafe(48)`), SHA-256 storage hash, short-lived access JWT, **separate-audience** MFA challenge token |
| `core/session_policy.py` | `SessionPolicy` + `policy_for(privileged=…)`: access/refresh TTL, idle timeout, absolute lifetime, whether MFA is mandated. Two profiles: `business` and `privileged` |
| `core/auth_throttle.py` | `AuthThrottle` + pluggable `ThrottleStore` (`memory` / `redis`): per-IP, per-account and per-(IP+account) failure budgets with progressive delay and capped blocks |
| `core/password_policy.py` | Length/composition, separator-insensitive personal-information check, `zxcvbn` scoring, pluggable breached-password checker (`off` / `local` / `remote`, fail-open) |
| `core/totp.py` | RFC 6238 TOTP (stdlib only) + recovery codes; verification is constant-time with a ±1 step window |
| `core/request_context.py` | `client_ip` (proxy-aware only when `TRUST_PROXY_HEADERS=true`), `user_agent`, `request_id` — one shape of context for every auth event and throttle key |
| `schemas/auth.py` | Request/response contracts for login, sessions and MFA |
| `services/auth_service.py` | The session/MFA **state machine**: create, rotate, revoke, idle/absolute expiry, replay handling, password-change consequences, MFA orchestration, security audit events |
| `repositories/auth_session_repo.py` | `auth_sessions` primitives; `rotate()` is a single conditional `UPDATE … WHERE revoked_at IS NULL` so the database, not Python, decides a rotation race |
| `routers/auth_sessions.py` | Session endpoints + the login/refresh throttle guards |
| `routers/auth_mfa.py` | MFA challenge/enrol/activate/verify (unauthenticated, challenge-token only) and management endpoints (authenticated + password step-up) |
| `core/business_roles.py` | Elevated business-role + access-scope vocabulary and the *only* definition of scope defaults: `resolve_business_role`, `resolve_business_access`, `role_columns`, `merge_role_columns`, `ROLE_SCOPE_TYPES` |
| `core/rbac.py` | `DASHBOARD_WIDGETS` + `get_visible_widgets` (permission-filtered widget keys) |
| `core/employee_access.py` | `EmployeeAccessScope`, `scope_for_employee`, `get_employee_scope`, `get_permission_scope`, `require_employee_access` — **row-level** visibility. This is the only place a business role is translated into which rows are visible |
| `core/audit.py` | `add_audit_event` (stages a row in the caller's transaction) and `record_audit_event` (stages + commits) → append-only `audit_logs` |
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

* **Rate limiter is in-process memory.** Multiple API workers ⇒ per-worker limits. Move to Redis before horizontal scale. Login/refresh carry an *additional*, auth-specific throttle whose state lives in `AUTH_THROTTLE_BACKEND` (`memory` = per worker, `redis` = shared).
* **Access tokens are stateless JWTs** (15 min business, 5 min privileged) and carry no permissions. Revoking a session ends its **refresh** chain immediately, but an already-issued access token stays valid until it expires — that is the reason its lifetime is short (§2.5.3). Authorization (role, permission, scope) is re-resolved from the database on every request, so a role change applies at once.
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
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | business access token (60–3600) |
| `PRIVILEGED_ACCESS_TOKEN_TTL_SECONDS` | `300` | Super Admin access token |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000` (30 d) | outer bound of a refresh chain |
| `SESSION_IDLE_TIMEOUT_SECONDS` | `3600` | business idle timeout; checked on every refresh |
| `SESSION_ABSOLUTE_TIMEOUT_SECONDS` | `43200` (12 h) | hard end of a business session, never extended by refreshing |
| `PRIVILEGED_IDLE_TIMEOUT_SECONDS` | `900` | Super Admin idle timeout |
| `PRIVILEGED_ABSOLUTE_TIMEOUT_SECONDS` | `7200` (2 h) | Super Admin hard end |
| `AUTH_THROTTLE_MAX_FAILURES` | `5` | failures before the IP+account pair is blocked (login) |
| `AUTH_THROTTLE_WINDOW_SECONDS` | `900` | sliding window for the counters |
| `AUTH_THROTTLE_BLOCK_SECONDS` / `_MAX_BLOCK_SECONDS` | `60` / `3600` | first block length and the cap it doubles towards |
| `AUTH_REFRESH_MAX_FAILURES` | `20` | budget for the refresh scope (looser: the token is unguessable) |
| `AUTH_THROTTLE_BACKEND` / `REDIS_URL` | `memory` / `""` | `redis` is **required** for more than one worker; asking for it without `REDIS_URL` (or without the `redis` package) fails loudly |
| `TRUST_PROXY_HEADERS` | `false` | honour `X-Forwarded-For`; only enable behind a proxy you control |
| `MFA_ENABLED` / `MFA_REQUIRED_FOR_SUPER_ADMIN` | `true` / `false` | global MFA kill switch / privileged-account enforcement; startup logs a warning while MFA is off |
| `MFA_ISSUER` / `MFA_CHALLENGE_TTL_SECONDS` | `People HRMS` / `300` | authenticator label and challenge-token lifetime |
| `MFA_ENCRYPTION_KEY` | development key | AES-256 key (base64 or hex) encrypting TOTP seeds at rest. Empty means "unset" and resolves to the development key. **Production refuses the development default at startup** — a seed dump protected by a key sitting in the repository protects nothing. Rotating it invalidates enrolled factors (they must re-enrol), so treat it like a database credential |
| `MFA_PENDING_TTL_SECONDS` | `900` | lifetime of an unconfirmed replacement authenticator; expired pending secrets are cleared when accessed |
| `PASSWORD_RECOVERY_TTL_SECONDS` | `600` | lifetime of the authenticator-based password recovery and one-time reset capability |
| `PASSWORD_MIN_LENGTH` / `PASSWORD_MAX_LENGTH` | `12` / `256` | floors/ceilings are validated, so they cannot be lowered accidentally |
| `PASSWORD_BREACH_CHECK` / `_URL` | `local` / `""` | `off` \| `local` \| `remote` (k-anonymity, fail-open) |

**Lifespan (`main.py`)** — in order: log start → `create_db_and_tables()` **only in development** → `ensure_seed_data()` in dev or when `BOOTSTRAP_SEED_DATA=true` → start `notification_cleanup_loop()` as a task → on shutdown cancel the task cleanly.

`validate_runtime_secrets()` runs at import-time startup of `main.py` and raises `RuntimeError` outside development if `JWT_SECRET`, `DATABASE_URL` or `SUPER_ADMIN_PASSWORD` are still defaults, `ERP_API_KEY` is empty, or throttling is configured with `AUTH_THROTTLE_BACKEND` ≠ `redis` / with a missing `REDIS_URL` — i.e. an auth-throttle setup that would silently be per worker is a *startup error* in production. The development shortcut is keyed on an explicit allow-list of environment names, so a typo such as `ENVIRONMENT=Production` cannot disable the checks. `settings.security_warnings()` then logs the non-fatal reminders (per-worker throttling, MFA not yet enforced, remote breach check without a URL, proxy headers not trusted).

**Schema management:** Alembic (`app/api/alembic/versions/`, 8 migrations). `create_all` is a development convenience only. Production releases must run `alembic upgrade head` first.

### 2.4 Data model

28 tables. Grouped by concern, with the fields that drive behaviour:

**Identity & access**
| Table | Key points |
|---|---|
| `users` | `user_id` PK, unique `username`, unique nullable `mobile_number` (E.164), `must_change_password`, `created_by`, invitation metadata (hash, sent/expires/used), fastapi-users fields (`is_active`, `is_verified`, `is_superuser`), MFA columns (`mfa_enabled`, `mfa_secret` — AES-GCM ciphertext, `mfa_pending_secret` + expiry — a replacement awaiting proof, `mfa_last_used_step` — the last spent TOTP step, `mfa_enrolled_at`, `last_mfa_verified_at`, `mfa_recovery_code_hashes` — hashes only) |
| `auth_sessions` | Only the **SHA-256 hash** of the refresh token; `expires_at` (30 d outer bound), `absolute_expires_at` (hard end of the chain), `last_used_at` (idle timeout), `revoked_at` + `revoked_reason` (`rotated`, `logout`, `logout_all`, `password_changed`, `password_reset:*`, `reuse_detected`, `idle_timeout`, `account_inactive`), `replaced_by_id` (rotation chain), `ip_address`, `user_agent` (device list) |
| `audit_logs` | Append-only: actor, action, entity, `filters_json`, `request_id`, `ip_address` |

**Org structure (ERP-owned)**
`organizations` (single row enforced by unique `singleton_key`), `units`, `departments`, `designations`, `department_approvers` (`approver_type`: LEAVE / SHIFT / EXPENSE / WORK_ARRANGEMENT).

**Workforce**
`employees` — the operational core. Authorization identity lives here: `business_role` (`NULL` = plain employee | `DEPARTMENT_MANAGER` | `HR_ADMIN` | `ORGANIZATION_OWNER`), `access_scope` (`SELF` | `DEPARTMENT` | `UNIT` | `ORGANIZATION`, default `SELF`) and `access_scope_id` (unit or department id, `NULL` for `SELF`/`ORGANIZATION`). `role` is kept as the compatibility mirror the ERP writes (`"EMPLOYEE"` = no elevation). Plus `user_id` (login), `unit_id`, `department_id`, `designation_id` + cached `designation` string, `reporting_manager_id` (self-FK), `shift_id` (ERP default shift), `status` (`ACTIVE`/…), `overtime_eligible`, `monthly_salary`, exit fields.
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

Three authentication **domains**, one users table:

```
                    ┌─ business users  → /login        (all workforce roles)
PEOPLE HRMS auth ───┼─ Super Admin     → /admin/login   (password + MFA, stricter session policy)
                    └─ ERP machines   → /api/v1/integrations/erp/**  (X-API-Key)
```

Authentication answers *who you are*; a business role never selects a login endpoint, and permissions/scope are resolved only afterwards (§2.6).

#### 2.5.1 Two human login doors (same users table)

| Endpoint | Tag | Identity accepted | Extra rule |
|---|---|---|---|
| `POST /api/v1/auth/employee/login` | `auth-employee` | Indian mobile (any input is normalized to E.164) or username | **must** have a linked `Employee`, else `403 "This account is a technical account. Use the technical sign-in."` — reachable only with a *correct* password, so it cannot be used to probe for accounts |
| `POST /api/v1/auth/super-admin/login` | `auth-super-admin` | username **only** (rejects `@`, digits, `+` → `400`) | must have `is_superuser`; otherwise the same generic `401 "Invalid login credentials"` as a wrong password |

Both are OAuth2 password-form endpoints and **both issue a session directly** — there is no intermediate long-lived bearer token any more (§2.5.3). Response shape:

```json
// session issued
{"access_token": "…", "refresh_token": "…", "expires_in": 900, "session_id": 42,
 "refresh_expires_at": "…", "absolute_expires_at": "…", "must_change_password": false}
// second factor required instead
{"mfa_required": true, "mfa_enrollment_required": false, "mfa_token": "…", "mfa_expires_in": 300}
```

`UserManager.authenticate()` resolves `username → normalized mobile` and performs a **dummy hash** for unknown users so the timing of a failed lookup resembles a failed password check (§2.5.7).

#### 2.5.2 Login and refresh throttling

The generic per-IP limiter is not a login defence (a whole office shares one NAT address), so authentication has its own budget, evaluated against three keys — the *strictest* verdict wins:

| Key | Budget | Why it exists |
|---|---|---|
| `ip+account` | `AUTH_THROTTLE_MAX_FAILURES` (5) | an attack on a specific account; cannot deny service to anyone else |
| `account` | 2× the base, longer block | protects a known employee from a distributed attack; engages later because it is the one key an outsider could weaponise |
| `ip` | 20× the base | catches extreme spraying from one address without punishing shared NAT |

Below the budget a failure collects a small progressive delay; at the budget the key is blocked for `AUTH_THROTTLE_BLOCK_SECONDS`, doubling per further failure up to `AUTH_THROTTLE_MAX_BLOCK_SECONDS`. **No rule blocks permanently**, a successful sign-in clears all three counters, and `POST /auth/session/refresh` uses the same machinery with a looser budget (`AUTH_REFRESH_MAX_FAILURES`) keyed by the presented token's fingerprint — so spraying invalid tokens cannot deny a real user's refresh. State lives behind `ThrottleStore` (in-process by default; `AUTH_THROTTLE_BACKEND=redis` shares it across workers, which production requires — see §2.3).

#### 2.5.3 Token & session model

| Artifact | TTL | Stored where | Notes |
|---|---|---|---|
| Access token (JWT `HS256`, aud `fastapi-users:auth`, `sid`) | 15 min business / 5 min privileged | BFF cookie `people_session` (HttpOnly) | stateless; **no** permissions embedded |
| Refresh token (opaque, `token_urlsafe(48)`) | 30 d outer bound, bounded by `absolute_expires_at` | SHA-256 hash in `auth_sessions`; raw in BFF cookie `people_refresh` (HttpOnly) | rotated on every use |
| MFA challenge token (JWT, aud `hrms:mfa`, `typ=mfa`) | 5 min | never stored | cannot be replayed as an access token (wrong audience) |

Endpoints: `POST /auth/session` (issue for an already-authenticated caller) · `POST /auth/session/refresh` (rotate) · `DELETE /auth/session` (revoke, idempotent) · `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `DELETE /auth/sessions` (device management) · `GET /auth/session` (describe current).

**Lifetimes are checked on every refresh**, in order: revoked → rotation state → refresh expiry → idle deadline (`last_used_at + SESSION_IDLE_TIMEOUT_SECONDS`) → absolute deadline. A rotation inherits the chain's `absolute_expires_at`, so refreshing can never extend a session beyond its hard end. Every decision lives in `services/auth_service.py`; routers only translate it into HTTP.

**Rotation & replay defence:** presenting an already-rotated (revoked, `replaced_by_id IS NOT NULL`) refresh token is treated as theft — **all** of that user's live sessions are revoked (`revoked_reason="reuse_detected"`), an `AUTH_REFRESH_REUSE_DETECTED` audit row is written and `401 "Refresh token reuse detected"` is returned.

**Concurrency:** rotation is a single conditional `UPDATE … WHERE id = :id AND revoked_at IS NULL`; the loser of a race sees `rowcount == 0`, rolls its own replacement back and is handled as a replay. Two concurrent uses of one token therefore never both mint a descendant (covered by a dedicated test).

**Bulk revocation:** an HR/ERP temporary-password reset (`_reset_password`) and a self-service `POST /auth/change-password` both revoke every live session for the account (`password_reset:*` / `password_changed`). A password change deliberately **does not** mint a replacement session: the user signs in again, which is the required behaviour for privileged accounts. Because an access token cannot be revoked before it expires, the exposure window after a change is one access-token TTL — the reason that TTL is minutes, and the reason permissions are never cached in the token.

#### 2.5.4 Super Admin MFA (TOTP)

Split so a stolen password alone can never replace an existing factor:

* **Challenge endpoints** (unauthenticated, require the short-lived challenge token issued *after* a correct password): `POST /auth/mfa/enroll` (first-time only — returns the secret, `otpauth://` URI and 10 single-use recovery codes, shown once), `POST /auth/mfa/activate` (confirm the new secret and sign in), `POST /auth/mfa/verify` (TOTP or recovery code).
* **Management endpoints** (authenticated **and** password re-verified): `POST /auth/mfa/reset` (new secret), `POST /auth/mfa/confirm` (activate from an existing session), `POST /auth/mfa/disable`, `GET /auth/mfa/status`.

A second factor is requested when the account's *policy* mandates it **or** the account has already enrolled — an enrolled authenticator is always used, otherwise opting in from account settings would protect nothing. `MFA_REQUIRED_FOR_SUPER_ADMIN` defaults to `false` so enabling it is a deliberate, communicated rollout; `MFA_ENABLED=false` disables MFA enforcement, including for previously enrolled accounts. Verification is constant-time with a ±1 step (30 s) drift window, and recovery codes are stored as SHA-256 hashes like refresh tokens. Enrolled already? `disable` is refused while policy requires MFA.

**Forgot-password recovery** is separate from normal login: the user enters a username or mobile number, proves possession of the enrolled TOTP authenticator (or a recovery code), and receives a short-lived one-time password-reset capability. The flow never creates a session, revokes every existing session after the new password is saved, keeps MFA enrolled, and is throttled and audited. Reused TOTP steps are reported separately from mistyped codes, while an expired or replaced recovery capability returns the UI to the identity step.

**Every code is single-use.** A successful verification records the TOTP *step it matched* (`users.mfa_last_used_step`) and any later submission of that step or an earlier one is refused with a distinct message, so an observed code cannot be replayed for the remainder of its window — including the ±1 step of drift either side. The matched step is recorded rather than "now" on purpose: attributing a lagging client's code to the current step would either block a legitimate sign-in or leave the window open, which is exactly how replay was possible before. A spent code is reported as *spent* rather than invalid, so the user is told to wait for the next code instead of hunting for a typo that does not exist.

**Seeds are encrypted, not hashed** (`core/secret_box.py`): AES-256-GCM with a fresh nonce per write, stored as `v1:<base64url(nonce‖ciphertext‖tag)>` under `MFA_ENCRYPTION_KEY`, which never lives in the database. A seed must be recoverable to verify future codes, unlike a password or a refresh token, so the protection is encryption plus a key held elsewhere — a database dump alone yields no usable second factor. A value without the `v1:` prefix predates this and is read as-is, then re-encrypted on the next write, so the upgrade cannot lock anyone out; a value that cannot be decrypted (wrong or rotated key) fails **closed** — the account falls back to its recovery codes and re-enrolment rather than accepting codes derived from garbage.

**A replacement factor is proven before it replaces anything.** `start_enrollment` writes only `mfa_pending_secret`; the active seed, `mfa_enabled` and the recovery codes are untouched until a code from the new secret is accepted (`activate` / `confirm`), at which point the pending seed is promoted and the replay counter resets. This matters because the obvious implementation — clearing the live secret and `mfa_enabled` at the start — lets an abandoned "issue a new secret" disable the second factor entirely *and* kill the authenticator in the user's hand. Recovery codes are issued only with a first factor: replacing one keeps the existing set valid, and `POST /auth/mfa/recovery/regenerate` issues a fresh set (password re-verified) when the user actually wants one.

**QR setup is rendered in the browser.** Enrolment returns the `otpauth://` URI and the API never re-displays it; the Nuxt side draws the QR client-side from that URI, so the seed travels only in the JSON body it arrived in and never into a URL or query string where it would be written to access logs and browser history. Manual entry stays available as a fallback for the key.

The spec vocabulary maps onto the implemented routes as: `totp/setup` → `POST /auth/mfa/enroll` (first factor, challenge token) or `POST /auth/mfa/reset` (replacement, password re-verified); `totp/enable` → `POST /auth/mfa/activate` (login-time) or `POST /auth/mfa/confirm` (from a session); `challenge/totp` and `challenge/recovery` → `POST /auth/mfa/verify` (one endpoint accepts either, and a valid TOTP code never consumes a recovery code); `recovery/regenerate` → `POST /auth/mfa/recovery/regenerate`; status → `GET /auth/mfa/status`. Every one of them is throttled on the account, the source IP and the pair.

#### 2.5.5 Password policy (enforced on register, change, and HR/ERP temporary-password set)

1. ≥ 12 characters, ≤ 256 (passphrases and password-manager output are welcome)
2. must contain upper, lower, digit, special character (kept deliberately: removing an existing control would be a silent weakening)
3. must not contain the user's email local part / username / first / last name (≥ 3 chars) — matched **after stripping separators**, so `Warm.Comet` cannot pad past the check
4. `zxcvbn` score ≥ 3 with those personal inputs supplied
5. not in the embedded common-password list (also catches `Welcome@2026`-style padding and keyboard/sequential runs) and not in a breached corpus if `PASSWORD_BREACH_CHECK` is set to `remote` — the breach check is pluggable and **fails open**, so password changes never depend on a third party being reachable

Failure raises `PasswordPolicyError` → `InvalidPasswordException` → `400 {"detail": "…reason…"}`.

#### 2.5.6 Step-up re-verification

Password re-verification is required for the sensitive operations that can lock an owner out of their own account: Super Admin username change, MFA reset/confirm/disable, and MFA-dependent policy changes. Ordinary business operations never ask again — step-up is applied by the endpoint that owns the sensitive transition, not by a global gate.

#### 2.5.7 Enumeration resistance

Unknown accounts get a dummy hash instead of a fast `return None`, all credential failures share one generic message (`"Invalid login credentials"`), an unprivileged account hitting the Super Admin door gets the *same* body as an unknown username, and every failed attempt is counted by the throttle. The specific reason (`invalid_credentials`, `not_privileged`, `no_employee_profile`, `mfa_failed`, …) is recorded in `audit_logs` for operators, never returned to the caller.

#### 2.5.8 Security audit events

`services/auth_service.py` writes to the existing append-only `audit_logs` table (no second audit framework): `AUTH_LOGIN_SUCCESS` / `AUTH_LOGIN_FAILED`, `SUPER_ADMIN_LOGIN_SUCCESS` / `_FAILED`, `AUTH_LOGOUT`, `AUTH_SESSION_CREATED`, `AUTH_SESSION_REFRESHED`, `AUTH_REFRESH_FAILED`, `AUTH_REFRESH_REUSE_DETECTED`, `AUTH_SESSION_REVOKED`, `AUTH_ALL_SESSIONS_REVOKED`, `AUTH_PASSWORD_CHANGED`, `AUTH_PASSWORD_RESET`, `AUTH_USERNAME_CHANGED`, `AUTH_MFA_CHALLENGE` / `_ENROLLED` / `_SUCCESS` / `_FAILED` / `_RECOVERY_REGENERATED`. Records carry `user_id` (when known), session id, `request_id`, IP, user agent and a reason category (`invalid` versus `replayed` on an MFA failure, and `activate` versus `verify` for the stage). The correlation id is minted by the request-logging middleware (an inbound `X-Request-ID` / `X-Correlation-ID` is preserved), stored on `request.state` and echoed on the response as `X-Request-ID`, so one id ties a user-visible failure to the API log line *and* the audit rows it produced. **Never** logged: passwords, raw access/refresh tokens, TOTP secrets or recovery codes — identities in failure events are stored as truncated hashes.

#### 2.5.9 Session lifecycle (state machine)

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

EXPIRED and REVOKED are both represented by `revoked_at` + `revoked_reason`; reuse is the only transition that cascades to *other* sessions.

#### 2.5.10 ERP machine authentication

`X-API-Key` header validated with `secrets.compare_digest` against `settings.erp_api_key`; empty/mismatched ⇒ `403 Could not validate API KEY`. There is **no** fallback key outside development, and the key must never reach a browser. ERP credentials are a **static shared key** today: adequate for a single trusted integration on a private network, and the documented upgrade path is per-client credentials + rotation (optionally signed requests or mTLS) — not something to introduce without a product requirement. ERP is never routed through human sessions.

### 2.6 Authorization: identity, permissions, scope, and domain rules

Four orthogonal concepts — get this right or you will mis-scope a feature:

| Concept | Question it answers | Implemented in |
|---|---|---|
| **Employee** | *Who is this person?* | `Employee` row linked to the login; base self-service is implicit |
| **Business role** | *What extra responsibility do they carry?* | `Employee.business_role` (optional, at most one per employee), vocabulary in `core/business_roles.py` |
| **Permission** (`require_permission`, `hasPermission`) | *May this user perform this kind of action at all?* | `core/auth.py` → `BASE_EMPLOYEE_PERMISSIONS` + `ROLE_PERMISSIONS` via `effective_permissions` |
| **Scope** (`EmployeeAccessScope`, `get_permission_scope`, `get_employee_scope`, `require_employee_access`) | *Which employees/rows does it apply to?* | `core/employee_access.py` (resolved from the business role + access scope) |
| **Domain rule** | *Is this specific transition valid, for this resource, right now?* | Services (no self-approval, valid leave-state transitions, overlap checks, ERP-owned read-only) |

There are no role-assignment tables, per-user permissions, deny overrides or policy languages: an employee holds **at most one** elevated business role, and their permissions are the base set plus that role's bundle.

```
authenticate → resolve employee → resolve effective permissions → check required permission
            → resolve scope → check the resource is inside scope → apply domain rules → service
```

#### 2.6.1 The permission set

`BASE_EMPLOYEE_PERMISSIONS` is implicit for **every** employee, so it is never duplicated into a role bundle:

```
permissions = set(BASE_EMPLOYEE_PERMISSIONS)
if employee.business_role:
    permissions |= ROLE_PERMISSIONS[employee.business_role]
```

`ROLE_PERMISSIONS` therefore lists only what a role *adds*, and `core/auth.py` asserts its keys are exactly the three elevated roles. `FIXED_ROLE_PERMISSIONS` survives as a read-only compatibility view (`base + bundle` per role, including `"EMPLOYEE"`).

| Bundle | Meaning |
|---|---|
| `BASE_EMPLOYEE_PERMISSIONS` | self-service: `employee.view_self`, `attendance.view_self`, `leave.apply` / `view_self` / `cancel`, `work_arrangement.apply` / `view_self` / `cancel`, `overtime.view_self`, `shift.view_self` |
| `DEPARTMENT_MANAGER` | `employee.view`, `attendance.view_department`, `leave.approve` / `reject`, `work_arrangement.approve` / `reject`, `overtime.view_department` / `approve`, `reports.attendance` / `reports.leave` |
| `HR_ADMIN` | user + employee administration, designation CRUD, `attendance.view` / `view_unit` / `view_department` / `process` / `correct`, `leave.manage` / `approve` / `reject`, `work_arrangement.manage` / `approve` / `reject`, `shift.assign` / `update`, `overtime.approve` / `view_department`, all `reports.*`, `system.configure`, `audit.view`, `salary_cost.view_unit` / `view_department` |
| `ORGANIZATION_OWNER` | read/analytics additions: `employee.view`, `attendance.view` / `view_unit` / `view_department`, `overtime.view` / `view_department`, `reports.view` / `attendance` / `leave` / `overtime`, `dashboard.view_organization`; like all workforce roles, also receives base self-service permissions |

**Unit HR and organization HR receive the same `HR_ADMIN` bundle** — only the scope differs (§2.6.2). The Organization Owner is deliberately *not* a superset of HR: it has organization-wide analytics and no HR operations or manager approval capability. It still has the base self-service permissions, as every workforce role does. Roles are not hierarchical.

#### 2.6.2 Business role → scope resolution

Scope lives in three columns on `employees`: `business_role`, `access_scope` (`SELF` | `DEPARTMENT` | `UNIT` | `ORGANIZATION`) and `access_scope_id` (unit or department id; `NULL` for `SELF`/`ORGANIZATION`). `core/business_roles.resolve_business_access()` is the single resolver, and `scope_for_employee()` turns its result into an `EmployeeAccessScope`:

```
user.is_superuser            → organization scope (and the HR_ADMIN permission set)
business_role HR_ADMIN       → access_scope ORGANIZATION → organization scope
                               access_scope UNIT (+ id)  → unit scope {scope_id or unit_id}
business_role DEPARTMENT_MANAGER → department scope {scope_id or department_id}
business_role ORGANIZATION_OWNER → organization scope (the role *is* org-wide)
no business role             → SELF scope: {the caller's own employee_id}
                               …except allow_self=True still short-circuits when
                               employee.user_id == user.id
```

Defaults make legacy rows behave exactly as before: an HR admin with no explicit scope resolves to `UNIT` on their own `unit_id`, a manager to `DEPARTMENT` on their own `department_id`, and an owner to `ORGANIZATION`. A scope that is illegal for the role (e.g. `ORGANIZATION` on a department manager) falls back to the role default rather than widening access, and **organization HR must be explicit** — a blank `unit_id` never means "whole organization". Provisions are written through `role_columns` / `merge_role_columns`, which keep `Employee.role` as a compatibility mirror of the business role (`"EMPLOYEE"` = no elevation). A **transfer moves a `UNIT`/`DEPARTMENT` scope with the employee** — a unit HR admin moved to another unit is re-scoped to the new unit (and audited as `EMPLOYEE_ROLE_CHANGED`) instead of silently keeping reach over the unit they left; passing `access_scope_id` explicitly pins a scope that intentionally differs from the employee's own unit/department.

`require_employee_access(user, employee, code_or_tuple, session, allow_self=…)` merges the scope of several permission codes, so `("attendance.view_self", "attendance.view_unit")` grants access if *any* code covers the row. `get_employee_scope(user, session)` returns the caller's scope *without* a permission gate, for routes that already used `require_permission`. Routes commonly fall back to "if the caller has no unit/department scope, restrict the query to their own employee_id" (`leaves`, `attendance`, `work-arrangements`, `overtime`, `shifts`); `get_permission_scope` returns an **empty** scope when the caller lacks the code entirely.

Serving routes therefore read like ``require_permission("attendance.correct") + require_employee_access(...)`` instead of a role check. `core/attendance_access.py` (`require_hr_admin`, `require_hr_unit_access`) **no longer exists**; the only surviving role usage is deliberately narrow: `routers/shifts.py` limits a *plain* employee to their own schedule, and `routers/dashboard.py` chooses the owner analytics panel.

Auditability: granting or changing an elevated role writes `EMPLOYEE_ROLE_GRANTED` / `EMPLOYEE_ROLE_CHANGED` to `audit_logs` with the previous and new `business_role` / scope, so "HR moved from UNIT to ORGANIZATION" is traceable through the existing mechanism.

**Caveat:** several granted codes are never enforced by the API — `employee.view_self`, `attendance.view_self`, `leave.view_self`, `overtime.view_self`, `shift.view_self`, `reports.view`, `reports.overtime`, `reports.salary_cost`, `salary_cost.*`, `audit.view`, `user.*`, `employee.update`, `employee.deactivate`, `overtime.view`. They are forward-compatible vocabulary today; only the codes referenced in §2.9 gate real behaviour (full list in Appendix A).

Derived rules worth remembering:

* **Super Admin ⇒ exactly the HR_ADMIN permission set plus organization scope** (`get_user_permissions` / `get_employee_scope` short-circuit). There is no superuser-only permission.
* **A user with no `Employee` row ⇒ base employee set.** Safe default; also means a "technical" account that is not a superuser sees only self-service.
* Permissions are **read from the DB on every request** (`get_user_permissions` queries the employee row) — changing `Employee.business_role` or the access scope takes effect on the next call, but the *client's cached permission list* is only refreshed on `/users/me`.
* Elevated bundles must not repeat base codes, and every enforced code must be granted somewhere: both are asserted by `tests/test_permission_grants.py`.

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

`GET /dashboard/widgets` returns the visible keys; superusers get all. The UI now uses workspace context for presentation, while this endpoint remains the permission-aware source for future widget-level composition.

### 2.7 Domain services

#### 2.7.1 Attendance engine (`services/attendance_service.py`)

* **Ingest**: `POST /attendance/checkins` and `/checkins/bulk` now return **403** — punches are ERP-supplied. Raw punches still exist in the model and repository (`AttendancePunchRepository.find_duplicate`) for the ERP ingest path.
* **Processing** (`process_attendance_for_employee_date` / `process_attendance_batch`, exposed as `POST /attendance/process` with `attendance.process`):
  1. Resolve the shift window for the date (dated assignment beats the ERP default shift; handles cross-midnight and `begin_check_in_before_minutes`).
  2. Classify the day: `WEEKLY_OFF`, `HOLIDAY`, `ON_LEAVE` (from approved leave), `WORK_FROM_HOME` (from approved arrangement) before computing work time.
  3. Compute `worked_minutes` minus `break_minutes`; derive `late_minutes` (beyond `late_entry_grace_minutes`) and `early_exit_minutes`.
  4. Apply thresholds: `< absent_threshold_hours` → `ABSENT`; `< half_day_threshold_hours` → `HALF_DAY`; otherwise `PRESENT`. A single missing punch → `MISSED_PUNCH`. Unpunched day → `WEEKLY_OFF` / `ON_LEAVE` / `ABSENT` as applicable.
  5. Overtime minutes beyond shift end feed `overtime_records`.
* **Corrections**: `POST /attendance/corrections` requires the `attendance.correct` permission **plus** row scope (`require_employee_access`): unit HR may correct their own unit, organization HR any unit. It always writes `sync_status = PENDING_ERP_RECONCILIATION`. Approve/reject endpoints do not exist — ERP confirmation is the approval.
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
* Shift definitions and assignment lists apply `EmployeeAccessScope` before counting or paging: employees see only their own assigned/default shift, department managers see their department, unit HR sees their unit, and organization-scoped HR sees the organization. Assignment rows batch-load employee and shift labels.
* Assignment creation prevents overlapping assignments per employee (`find_overlapping_assignment`).
* Public router is **read-only** (see §8.1 A1).

#### 2.7.5 Holidays (`services/holiday_service.py`)

`create_holiday_list` can auto-generate a year of `is_weekly_off` rows from `weekly_off_day`; `resolve_holiday_list_for_employee` picks unit list → default list; `is_holiday_or_weekly_off` and `get_holidays_in_range` (with `skip_weekly_offs`) are the primitives used by the leave calculator and the attendance engine. Public API is read-only (`GET /holidays/lists`, `GET /holidays/lists/{id}`).

#### 2.7.6 Overtime (`services/overtime_service.py`)

`list_overtime`, `get_overtime`, `get_overtime_summary` (month filtering, approved minutes only), `approve_overtime` / `reject_overtime` with row locking, self-approval prevention, state validation, an approved-minutes ceiling, and an `overtime_approvals` audit row for approvals. The router exposes approval/rejection only to `overtime.approve` users within their assigned employee scope.

#### 2.7.7 Reports (`services/report_service.py`)

* `GET /reports/attendance-matrix?year&month` → day-by-day matrix + aggregates, scoped by `_scoped_report_filters`: organization scope = caller's own filters, UNIT scope = forced to that unit, DEPARTMENT scope = forced to that department; a caller with no usable scope gets 403.
* `GET /reports/leave-summary?year` → allocated/used/pending/available per employee, same scoping rule.

#### 2.7.8 Notifications & audit

* `routers/notifications.py` exposes `create_notification()` for services plus `GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}/read`, `POST /notifications/mark-all-read`.
* Visibility filter: superuser sees all; everyone else sees direct notifications, `ALL`/`STAFF`, only the linked employee's current business-role audience, and unscoped global `system` notifications. Accounts without a linked employee do not receive employee/HR/manager/owner broadcasts.
* `mark_notification_read` applies the same audience rules as listing, preventing guessed IDs from reading or mutating another user's or role's notification.
* Audit: `GET /dashboard/owner` and `/dashboard/owner/exceptions` write `ORGANIZATION_DASHBOARD_VIEWED` / `ORGANIZATION_EXCEPTION_DRILLDOWN_VIEWED` rows with filters, request id and IP.

#### 2.7.9 Background work

`utils/notifications_cleanup.py` starts after a 60-second delay and repeats every 6 hours:
1. delete everything older than 7 days,
2. delete read notifications older than 3 days,
3. keep at most the 50 newest notifications per `user_id`/`target_role` partition (window function).

### 2.8 ERP integration contract (all writes use `X-API-Key`)

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
| `POST /api/v1/leaves/periods`, `/types` | Create ERP-owned leave periods and types before balance sync | these two legacy paths sit outside `/integrations/erp`; both require `X-API-Key` |

**Ingestion discipline:** bulk endpoints are intentionally *partial-success* — a bad row lands in `failed[]` with its error string and the rest are committed. Callers must inspect the result, not just the HTTP status.

**Manual contract runner:** `app/api/demo.py` is an editable HTTP client for exercising the ERP contract in dependency order. It previews by default and sends requests only with `--execute`; returned unit, department, designation, shift, employee, and attendance IDs are carried into dependent calls. It does not write directly to PostgreSQL. `--leave-feed-only` can be run after a human approves or rejects leave, and acknowledgements require the separate `--ack-leave-changes` flag.

**Local database reset:** `app/api/cleanup_db.py` discovers application tables in PostgreSQL and previews them by default. Execution requires both `--execute` and the exact confirmation text `DELETE ALL HRMS DATA`; remote and non-development targets require additional explicit flags. It truncates application tables with identity reset while preserving `alembic_version`, so the schema and migration history remain intact. The optional `--reseed-bootstrap` flag recreates the minimum organization and Super Admin records from `ORGANIZATION_*` and `SUPER_ADMIN_*` settings. Stop the API during cleanup because development startup can otherwise recreate those bootstrap rows concurrently.

**Outbound discipline:** HRMS never calls the ERP. Leave approvals/rejections/cancellations queue an event that the ERP polls. Until the ERP acks, `erp_sync_status` stays `PENDING`; rows are visible in `GET /leaves/changes` indefinitely.

### 2.9 Public API index (grouped by tag)

Every tag below is also an OpenAPI tag declared in `main.py`. Auth column: **E** = employee login, **SA** = super admin, **Any** = any active user, **perm(x)** = `require_permission`, **ERP** = API key. There is no `role:X` auth column any more: capability comes from permissions, reach comes from the caller's access scope (§2.6).

| Group | Endpoint | Auth | Scope rule |
|---|---|---|---|
| **account** | `GET /users/me` | Any | returns permissions + employee_id/code + resolved `business_role` / `scope_type` (the scope id is not exposed) |
| | `GET /users/me/permissions` | Any | — |
| **auth** | `POST /auth/employee/login` | public, throttled | mobile/username → session (or MFA challenge) |
| | `POST /auth/super-admin/login` | public, throttled | username only → session (or MFA challenge) |
| | `POST /auth/change-password` | Any | clears `must_change_password` **and revokes every session** (`reauthentication_required: true`) |
| | `PATCH /auth/super-admin/username` | SA + password step-up | conflict-checked |
| | `POST /auth/hr/employees/{id}/password-reset` | perm(`user.update`) + row scope | revokes sessions, sets `must_change_password` |
| | `GET /auth/invitation/validate`, `POST /auth/invitation/set-password` | public | 48 h, single-use token |
| **auth-session** | `POST /auth/session` | Any | issues another chain for an authenticated caller |
| | `POST /auth/session/refresh` | public (token is the credential), throttled | rotation + replay kill; no access token required |
| | `DELETE /auth/session` | public (token is the credential) | logout; idempotent |
| | `GET /auth/sessions`, `GET /auth/session` | Any | signed-in devices / describe current |
| | `DELETE /auth/sessions/{id}`, `DELETE /auth/sessions` | Any | sign one device out / sign out everywhere |
| **auth-mfa** | `POST /auth/mfa/enroll`, `/activate`, `/verify` | challenge token only | first-time enrolment, confirm-and-sign-in, TOTP or recovery code |
| | `GET /auth/mfa/status` | Any | enrolment state, recovery codes left |
| | `POST /auth/mfa/reset`, `/confirm`, `/disable` | Any + password step-up | issue/activate/remove an authenticator |
| **dashboard** | `GET /dashboard/metrics` | Any | self metrics; unit/dept/org metrics when the caller has team-review permissions, filtered by their resolved scope |
| | `GET /dashboard/widgets` | Any | permission-filtered keys |
|  | `GET /dashboard/technical-metrics` | SA | counts only; no audit row is written |
| | `GET /dashboard/owner`, `/owner/exceptions` | perm(`dashboard.view_organization`) | organization-wide + audit row |
| **employees** | `GET /employees/` | Any | organization scope = all · UNIT scope = that unit · DEPARTMENT scope = that department · SELF = own record only |
| | `GET /employees/{id}`, `/work-history` | Any | `employee.view` + `allow_self` |
| | `POST /employees/onboard` | perm(`employee.create`) | **returns 410** (ERP-only) |
| **designations / org / units / departments** | `GET` list + detail | Any | read-only mirrors |
| **holidays** | `GET /holidays/lists`, `GET /holidays/lists/{id}` | Any | read-only |
| **shifts** | `GET /shifts/`, `/assignments`, `/assignments/{id}`, `/employee/{id}/schedule`, `/{id}` | Any | a plain employee (no business role) is forced to self; elevated roles see the management views |
| **attendance** | `GET /attendance/`, `/records/{id}`, `/employee/{id}/calendar`, `/employee/{id}/summary`, `/checkins`, `/corrections` | Any | read-permission scope + `allow_self` |
| | `POST /attendance/checkins`, `/checkins/bulk` | — | **403 — ERP supplied** |
| | `POST /attendance/process` | perm(`attendance.process`) | HR unit scope |
| | `POST /attendance/corrections` | perm(`attendance.correct`) + row scope | → `PENDING_ERP_RECONCILIATION` |
|  | `PATCH /attendance/corrections/{id}/approve\|reject` | — | **route removed — ERP confirms** |
| **leaves** | `GET /leaves/periods`, `/types`, `/types/{id}`, `/balance/employee/{id}`, `/`, `/{id}` | Any | self-service via `leave.apply`/`allow_self`; management scope otherwise |
| | `POST /leaves/`, `PATCH /leaves/{id}/cancel` | Any | self via `leave.apply`/`leave.cancel` |
| | `POST /leaves/periods`, `/types`, `PATCH /types/{id}` | perm(`leave.manage`) | HR |
|  | `PATCH /leaves/{id}/approve\|reject` | perm(`leave.approve`/`reject`) | scope + no self-approval |
|  | `PATCH /leaves/{id}/cancellation/approve\|reject` | perm(`leave.approve`/`reject`) | scope + no self-approval |
| **work-arrangements** | `GET /` , `GET /{id}` | Any | management scope else self |
| | `POST /`, `PATCH /{id}/cancel` | Any | self via apply/cancel |
|  | `PATCH /{id}/approve\|reject` | perm(`work_arrangement.approve`/`reject`) | scope + no self-approval |
| **overtime** | `GET /overtime/`, `/{id}`, `/employee/{id}/summary` | Any | business-role scope, self fallback |
| | `PATCH /{id}/approve`, `PATCH /{id}/reject` | perm(`overtime.approve`) | employee scope + no self-action; approval cannot exceed calculated minutes |
| **reports** | `GET /reports/attendance-matrix`, `/leave-summary` | perm(`reports.attendance`/`reports.leave`) | scope-forced filters inside the route (org scope may choose unit/department) |
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
│  ├─ middleware/auth.global.ts       # route guard (session required, public paths incl. /admin/login)
│  ├─ middleware/workspace.global.ts # route visibility guard for the active workspace
│  ├─ composables/useAuth.ts          # shared auth state, permissions, login/logout/MFA
│  ├─ composables/useWorkspace.ts     # permission-derived workspace availability and switching
│  ├─ composables/useHrmsApi.ts       # typed wrapper over /api/hrms/** (+ 401 → /login)
│  ├─ components/AuthMfaChallenge.vue # shared second-factor panel (login + admin login)
│  ├─ components/dashboard/OwnerDashboard.vue
│  ├─ components/attendance/AttendanceStatusBadge.vue
│  └─ pages/…                         # see §3.5
├─ server/
│  ├─ middleware/csrf.ts              # reject state-changing requests from an unexpected origin
│  ├─ api/session/login.post.ts       # login → cookies → /users/me (or an MFA challenge)
│  ├─ api/session/mfa.post.ts         # verify/activate a challenge → cookies → /users/me
│  ├─ api/session/mfa/enroll.post.ts  # reveal a new authenticator secret (challenge token only)
│  ├─ api/session/me.get.ts           # current user (refreshes once if the access token expired)
│  ├─ api/session/index.delete.ts     # revoke + clear cookies
│  ├─ api/hrms/[...path].ts           # single BFF proxy with single-flight transparent refresh
│  └─ utils/hrms.ts                   # cookie names/options, session cookie helpers, refreshSession, upstreamError
│  └─ utils/origin.ts                 # pure Origin/Referer validation used by the CSRF middleware
└─ shared/types/*.ts                  # type modules shared by app & server
```

### 3.2 The BFF session proxy (why the browser never sees a token)

Cookies (all `httpOnly`, `sameSite=lax`, `secure` and `__Host-`-prefixed outside dev; tokens are never in `localStorage`, sessionStorage, Pinia or JS-readable cookies):

| Cookie | TTL | Content |
|---|---|---|
| `people_session` (prod: `__Host-people_session`) | access-token TTL from the API (15 min business / 5 min privileged) | access JWT |
| `people_refresh` (prod: `__Host-people_refresh`) | until the session's `absolute_expires_at` — never longer | opaque refresh token |

Browser cookie expiry is a transport detail only: revocation is always server-side, and the cookie lifetime is derived from the session deadlines the API returns.

**Login** (`POST /api/session/login`):
```
browser ──▶ Nitro: POST /api/session/login {identity, password, accountType}
   Nitro ──▶ FastAPI POST /auth/(employee|super-admin)/login   (form-urlencoded)
             ↳ returns the session directly (access + rotating refresh) — no intermediate
               long-lived bearer token is minted or exchanged
   Nitro ──▶ FastAPI GET  /users/me      (Bearer access)
   Nitro ──▶ browser: Set-Cookie people_session + people_refresh, body = CurrentUser
```
If the API answers with an MFA challenge instead, the BFF passes `{mfa_required, mfa_token, enrollment_required, expires_in}` to the browser and stores **no** cookie; the page then posts the code to `/api/session/mfa` (or fetches the new secret from `/api/session/mfa/enroll` for first-time enrolment) and only then receives cookies.

**Any business call** (`/api/hrms/<path>`):
```
1. forward method/query/body with Authorization: Bearer <people_session>
2. on 401 and a refresh cookie exists (and path ≠ auth/session/refresh):
     single-flight POST /auth/session/refresh → rotate cookies → retry the original request once
3. still 401 → delete both cookies and surface the upstream error
```
`refreshSession()` de-duplicates concurrent rotations by keyed promise: a page that fires several calls at once performs **one** rotation (the API would otherwise treat the second use as replay and revoke the chain) and every caller applies the same new cookies.

This means **token refresh is transparent to every page**: a 15-minute access token never logs a user out during a working session, and a replayed refresh token (rotation violation) does — correctly — kill the session.

**Logout** (`DELETE /api/session`): revoke the server-side refresh session, clear both cookies, `204`. Cookies are cleared even if the API call fails, and logging out twice is not an error.

**CSRF / origin protection** (`server/middleware/csrf.ts`): every state-changing request (`POST`/`PUT`/`PATCH`/`DELETE`) must carry an `Origin` (or `Referer`) that matches the request's own host — or an entry in `NUXT_HRMS_ALLOWED_ORIGINS` — otherwise it is rejected with `403` before any handler runs. A request with neither header is treated as a non-browser client (mobile app, CLI, health probe) and allowed, because a browser always sends `Origin` on a cross-site state-changing request and a cookieless client holds no ambient authority to forge. `SameSite=Lax` is defence in depth here, not the whole strategy, and API CORS remains a separate concern on the FastAPI side.

**Error translation** (`server/utils/hrms.ts → upstreamError`): FastAPI `detail` (string or `{reason}`) becomes the Nitro `statusMessage`, so pages can display `error.data.statusMessage` verbatim. Default status when upstream status is unknown: `502`.

### 3.3 Auth state and route guard

`useAuth()` stores `auth-user`, `auth-initialized`, `auth-loading` in `useState` (SSR-safe, shared by all components) and exposes:

| Member | Behaviour |
|---|---|
| `displayName`, `initials` | display helpers |
| `hasPermission(code)` | true when `is_superuser` **or** `permissions` contains the code |
| `businessRole` | the resolved elevated business role (or `null`) — used for descriptive labels; workspace availability and actions are permission-derived |
| `scopeType` | `SELF` \| `DEPARTMENT` \| `UNIT` \| `ORGANIZATION`, used to adapt copy and layout; the scope *identifier* stays server-side |
| `fetchUser(force = false)` | one `GET /api/session/me` per request; errors ⇒ signed-out state (never throws) |
| `login(payload)` | posts to the BFF; returns the user, **or** an `MfaChallenge` the caller must complete before a session exists |
| `completeMfa({mfa_token, code, enrollment})` | verifies/activates the second factor, sets the user |
| `startMfaEnrollment(mfaToken)` | reveals the new authenticator secret + recovery codes (shown once) |
| `mustChangePassword` | true while the account is on an HR/ERP temporary password; drives the "set a new password" prompt |
| `logout()` | revokes session, clears state, `navigateTo('/login')` |
| `clear()` | forgets client state without calling the API (used after a password change, which has already killed every session) |

`middleware/auth.global.ts` runs on every navigation: `await fetchUser()` → unauthenticated and not a public path ⇒ `/login?redirect=<fullPath>`; authenticated visiting a sign-in page ⇒ `/`. Public paths: `/login`, `/admin/login`, `/forgot-password`, `/reset-password`, `/invitation`, `/verify-email`, `/auth/invitation`. `middleware/workspace.global.ts` then redirects a signed-in user from a route that is unavailable in the active workspace to that workspace's dashboard; API permission and row-scope checks remain authoritative.

`useHrmsApi().request()` additionally hard-handles `401` mid-session: clears `auth-user` and redirects to `/login?redirect=<current>`, then rethrows.

`useWorkspace()` keeps identity separate from presentation. It derives available workspaces from the permission codes returned by `/users/me`, defaults to `MY`, and changes only the `workspace` query context — it never logs the user out or creates another session. The selected workspace is kept in a preference cookie for refreshes and is revalidated against the currently signed-in user's permissions. The server remains authoritative for every resource and row scope; the workspace switcher is an information-architecture aid, not an authorization boundary.

### 3.4 Navigation & visibility — permission-gated workspaces

`layouts/default.vue` builds a navigation set for the current workspace. A workspace is available when the user has a permission that supports its tasks. Management navigation items declare any-of permission rules; self-service items rely on workspace membership and the route's permission guard. Keep `useWorkspace.ts` route rules and sidebar item gates aligned when adding a capability so a permitted route is not hidden from navigation. The former `roles` gate is gone — a role is not a visibility primitive, and every capability it used to imply now corresponds to a permission.

One account can move between contexts without another login:

| Workspace | Audience | Typical navigation |
|---|---|---|
| My Workspace | Every employee, including elevated users | Personal attendance, leave, work arrangements, overtime, shifts, holidays |
| Team Workspace | Department/team review permissions | Team dashboard, scoped employees/attendance/leave/work-arrangement/overtime/shift records, approvals, reports |
| HR Workspace | HR operations permissions | Scoped workforce/attendance/leave/work-arrangement/overtime records, approvals, reports, organization |
| Executive Workspace | `dashboard.view_organization` | Organization analytics, reports, organization overview |
| Technical Administration | Super Admin only | Technical metrics and system administration |

| Nav item | permissions (any-of) | Effective audience |
|---|---|---|
| Dashboard | workspace-specific | everyone, in the active workspace |
| Employees | `employee.view` | Team / HR / Executive where permitted |
| Attendance, Leave, Work arrangements, Overtime, Shifts, Holidays | workspace-specific + endpoint permissions | My self-service or elevated workspace scope |
| Approvals | `leave.approve`, `work_arrangement.approve` | Team / HR |
| Organization | `designation.view` or workspace permission | HR / Executive |
| Reports | `reports.attendance`, `reports.leave` | Team / HR / Executive |
| System administration (link) | superuser only | Super Admin |

Action and dialog visibility follows the same rule: `pages/attendance/index.vue` gates the correction dialog on `hasPermission('attendance.correct')` rather than on the `HR_ADMIN` role, and `pages/profile.vue` derives its display label from `business_role` + `scope_type` (so unit HR and organization HR are distinguishable). Dashboard presentation now follows the active workspace (`MY`, `TEAM`, `HR`, `EXECUTIVE`, or `TECHNICAL`) rather than branching directly on a role.

Navigation is grouped by purpose inside each workspace (for example Workforce, Requests & approvals, Time & compensation, Organization, and Insights in HR). Group headings are high-contrast and each group is visually bounded, so the active workspace's operational areas are distinguishable at a glance. Team/HR dashboards show scoped KPIs and approval work only; personal shift and attendance cards appear only in My Workspace. Approval shortcuts are rendered only when the user has a matching approval capability. Super Admin gets **only** Dashboard + System administration — the business nav is replaced, because master data lives in ERP.

The shared Approvals page is available when the user can approve leave, work arrangements, **or overtime**; overtime approval must not depend on also granting one of the other approval permissions.

Mobile has exactly four primary destinations: **Home**, **Workspace**, the permission-filtered contextual section (My: Leave; Team: Approvals; HR: Employees; Executive: Reports; Technical: Settings), and **More**. Workspace opens a Nuxt UI slideover that identifies the active workspace; More holds remaining pages and account actions. The desktop sidebar retains one workspace selector and grouped navigation.

The workspace route guard resolves the **destination** query and validated saved preference using pure helpers. It does not instantiate reactive workspace watchers inside middleware or read the previous page's route. Owners receive My + Executive, managers My + Team, HR My + HR, and technical administrators only Technical. Regression checks: `node --test tests/workspace.test.mjs` from `app/web` (Node 24).

The employee directory starts master-data and paginated directory requests independently using lazy loading, allowing client navigation to show its skeleton immediately. Changing unit resets the department filter, and leaving the page clears the search debounce timer.

The workspace middleware keeps hidden routes out of the current workspace and returns users to its dashboard. It is a user-experience guard only: every endpoint still re-checks permission and row scope (§2.6). Collection views in Attendance, Leave, Work arrangements and Overtime choose self-service employee filters in `MY`, and omit the employee filter in `TEAM`/`HR` so the backend applies the manager's department or HR's unit/organization scope. Self-service actions are hidden in management views.

### 3.5 Page inventory → API map

| Page | Primary endpoint(s) | Key UI capabilities | Broken/limited (see §8) |
|---|---|---|---|
| `pages/login.vue` | `POST /api/session/login`, `/api/session/mfa` | **workforce sign-in only** (mobile / username), password reveal, second-factor step, `redirect` honouring, inline error text; a temporary-password account is sent to `/settings?change-password=1` | links to `/admin/login` and `/forgot-password` |
| `pages/admin/login.vue` | `POST /api/session/login` (`accountType: 'super_admin'`), `/api/session/mfa` | separate technical entry point (username only), visually distinct, MFA step with first-time enrolment | business accounts are rejected by the API |
| `pages/index.vue` | `dashboard/metrics`, `dashboard/technical-metrics` (SA only), `dashboard/owner` via component | workspace-specific KPIs; personal shift/attendance cards only in MY; scoped approvals only when permitted | ignores `/dashboard/widgets` |
| `pages/employees/index.vue` | `employees/`, `org/units`, `org/departments`, `designations/` | paginated, filtered read-only directory; ERP ownership is stated in the page | Provisioning/lifecycle writes are ERP-owned and not offered in this UI |
| `pages/employees/[id].vue` | `employees/{id}`, `employees/{id}/work-history` | profile, org placement, work history | — |
| `pages/attendance/index.vue` | My: `attendance/employee/{id}/calendar`, `…/summary`, `attendance/corrections`; Team/HR: `attendance/` | My calendar and summary; correction request is shown only to `attendance.correct` users; Team/HR scoped records table | scoped collection currently identifies employees by ID; row-level API scope applies |
| `pages/leaves/index.vue` | My: `leaves/`, `leaves/types`, `leaves/balance/employee/{id}`; Team/HR: `leaves/` | My balance/apply/history; Team/HR scoped request list linking to approvals | — |
| `pages/work-arrangements/index.vue` | `work-arrangements/` | My request/list/cancel; Team/HR scoped request list | only WFH accepted server-side |
| `pages/approvals/index.vue` | Leave, work-arrangement, and overtime queues | queues and controls gated by matching permissions; rejection requires a reason; overtime approval defaults to calculated minutes | attendance corrections are ERP-confirmed, not approved here; overtime rows currently show employee IDs |
| `pages/shifts/index.vue` | `shifts/`, `shifts/assignments`, `org/units`, `employees/` | read-only shift definitions and assignments synchronized from ERP | writes intentionally not offered; ERP owns the source data |
| `pages/holidays/index.vue` | `holidays/lists`, `org/units` | calendar + holiday list viewer | `canManage` hard-coded `false` (correct, ERP-owned) |
| `pages/organization/index.vue` | `org/organization`, `org/units`, `org/departments`, `designations/` | read-only tabs for organization structure synchronized from ERP | writes intentionally not offered |
| `pages/overtime/index.vue` | My: `overtime/`, `overtime/employee/{id}/summary`; Team/HR: `overtime/` | My monthly summary and records; Team/HR scoped records | management collection has no employee name or date filters yet |
| `pages/reports/index.vue` | `reports/attendance-matrix`, `reports/leave-summary` | month picker, attendance matrix, leave summary; tabs gated by permission | — |
| `pages/notifications.vue` | `notifications`, `notifications/{id}/read`, `notifications/mark-all-read` | list, read, mark-all | — |
| `pages/profile.vue` | `users/me` (via composable) | identity, role label, employee code | — |
| `pages/settings.vue` | `auth/change-password`, `auth/super-admin/username`, `auth/mfa/*`, `auth/sessions` | password change (ends every session → back to `/login`), username change with password step-up, two-step verification setup/removal, signed-in device list with per-device and global sign-out | MFA and username sections are technical-account oriented; the device list is for everyone |

### 3.6 Design system & responsive rules

* Tokens in `app/assets/css/main.css` (`--people-canvas`, `--people-surface`, `--people-border`, `--people-blue/mint/lavender/peach/yellow` + `-ink` pairs) drive every card/icon tone; `people-card`, `people-icon`, `people-icon--*` are the shared class contracts.
* Every page header follows: eyebrow label → `h2` title → one-line subtitle → right-aligned primary action.
* Skeletons (`USkeleton`) for first paint, `UAlert` "taking a short break" pattern with a retry action for failed dashboards, `UToast` for action results, and Nuxt UI confirmation modals for destructive actions.
* Breakpoints: single column → `sm:grid-cols-2` → `xl:grid-cols-3/4`; sidebar is fixed ≥ `lg`; grouped bottom navigation and bottom sheets below `lg`; `min-h-11` tap targets; safe-area padding on mobile nav.
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
4. GET /users/me also: get_user_permissions(user)  [Employee.business_role (+ legacy role)
                                                    → BASE_EMPLOYEE_PERMISSIONS | ROLE_PERMISSIONS]
                       + employee lookup → employee_id, employee_code, role,
                         resolved business_role + scope_type (scope id stays server-side)
5. Nitro returns CurrentUser → useState('auth-user') → nav + page permission gates resolve
6. Page then fires its own /api/hrms/** calls (SSR `useAsyncData`), each subject to transparent refresh
```
Failure modes: no cookie → `401` → `/login?redirect=…` · access expired + refresh valid → silent rotate (one retry) · refresh replayed, revoked, idle-timed-out or past its absolute deadline → `401` → login · password changed/reset → every chain revoked → login.

### 4.1 F1 — EMPLOYEE (self-service day)

**Login.** `/login`, mobile `9876543210` + password.
`POST /api/session/login` → FastAPI normalizes to `+919876543210` → throttle check → `UserManager.authenticate` → dummy hash if unknown → `Employee` link check → **session issued directly** (access + rotating refresh) → `GET /users/me` → cookies set. An account with an enrolled authenticator is instead answered with an MFA challenge, completed in the same page.
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
The correction-request action is not available to a plain employee: it is hidden unless the user has `attendance.correct`, and the API independently enforces that permission and row scope. Authorized HR users can submit corrections from the personal attendance view; ERP reconciliation remains the final confirmation (§8.1 A3).

**Overtime (`/overtime`).** `GET /overtime/` self-scoped + monthly summary (approved minutes only). Approvers process the scoped pending queue in `/approvals`; self-action is rejected and approval minutes cannot exceed the ERP-calculated amount.

**Notifications (`/notifications`).** `GET /notifications` (user + role broadcasts), `PATCH …/{id}/read`, `POST …/mark-all-read`; server prunes with the retention rules in §2.7.9.

**Security (`/settings`).** `POST /auth/change-password` → policy validated → hash replaced, `must_change_password = false`, **every session revoked** (`password_changed`) → the page clears client state and returns to `/login?notice=password-changed`. An access token already issued stays valid for at most one access-token TTL (§2.5.3). The same page lists signed-in devices and can sign one out or all of them out.

### 4.2 F2 — DEPARTMENT_MANAGER (approve & report for one department)

**Login/Dashboard.** Same door; `hasPermission('leave.approve')` and `employee.view` make the Team workspace available. In `MY`, the user sees personal metrics and shift/attendance cards. In `TEAM`, `GET /dashboard/metrics` returns data scoped to **their department** (`get_employee_scope` ⇒ `dept_scope_ids`): headcount, attendance breakdown, overtime and pending-work indicators. Personal cards are not shown in this workspace; approval summaries/shortcuts appear only if the user holds leave or work-arrangement approval permission.

**Approvals (`/approvals`).** Tabs are permission-driven: `leave.approve` (+`leave.reject` for the reject button) and `work_arrangement.approve`; the attendance tab is a read-only queue (ERP confirms corrections).
* Leave queue loads `PENDING` **and** `CANCELLATION_PENDING` in parallel and picks the right endpoint per row (`/approve` vs `/cancellation/approve`).
* Approve ⇒ attendance rows become `ON_LEAVE`/`HALF_DAY`, ledger debit, `erp_event_id` queued for ERP, balance `pending → used`.
* Reject ⇒ modal with mandatory reason → `PATCH …/reject` → `pending` released.
* Self-approval is impossible: the service returns `400` even if the UI were bypassed.

**Reports (`/reports`).** Tabs by permission; the route **forces** `department_id` for a DM, so a DM cannot widen scope by passing `unit_id`.

**People.** `GET /employees/` is silently limited to their department (route logic), and `GET /employees/{id}` outside the department returns `403 "You do not have access to this employee"`.

### 4.3 F3 — HR_ADMIN (unit operations, or organization-wide when scoped so)

**Dashboard.** In `MY`, HR sees personal metrics and shift/attendance cards. In `HR`, dashboard metrics use the configured `UNIT` or `ORGANIZATION` scope and label the headcount accordingly; personal cards are not mixed into the HR view.

**Employees (`/employees`).** Unit-limited directory with search/filters, pagination (`page_size` ≤ 100), detail page with separately paginated work history. Provisioning is ERP-only: `POST /employees/onboard` returns `410`, and the page explains ERP ownership without exposing unsupported activate, deactivate, delete, or edit actions.

**Growing-list contract.** Nuxt-facing business lists use `page` (default 1), `page_size` (default 25, maximum 100), `search`, `sort_by`, `sort_order`, and their domain filters. Responses use `PaginatedResponse` navigation metadata. Authorization and filters are applied before counts; every endpoint publishes its accepted `sort_by` values as an OpenAPI enum matching the repository allowlist, and SQL ordering always appends the row identifier. Employee-month calendars, aggregate summaries, effective schedule windows, leave balances by configured type, one holiday list's entries, and policy-limited session lists are bounded collections rather than business-list exceptions. ERP ingestion and change-feed response shapes remain integration contracts and are unchanged.

**Attendance (`/attendance`).** Read scope covers `attendance.view`, `view_unit`, `view_department`; can run the engine with `POST /attendance/process` (`attendance.process`) for an authorized unit/employee, and can raise corrections for records inside their scope (`attendance.correct` + `require_employee_access` → 403 `"You do not have access to this employee"` otherwise).

**Unit HR vs organization HR.** Both hold the identical `HR_ADMIN` permission bundle; only the access scope differs (`UNIT` + `access_scope_id`, or `ORGANIZATION`). A unit HR admin sees their unit and is refused on another unit's records; organization HR (`access_scope = ORGANIZATION`, no `access_scope_id`) reaches every unit, and their dashboard KPI label reads "Organization members". Organization HR is still *not* an Organization Owner: it has no `dashboard.view_organization` and therefore no owner analytics panel.

**Shifts (`/shifts`).** Definitions + assignments are read from HRMS and scoped to the active user's employee reach: self in My, department in Team, unit/organization in HR. Creating them is ERP-only, so the page is a viewer and exposes no create/assign controls.

**Password operations.** `POST /auth/hr/employees/{id}/password-reset` sets a temporary password (policy-validated), sets `must_change_password`, and revokes all of the user's refresh sessions. This is the supported "reset a locked-out employee" path; the login page tells users to contact HR for exactly this reason.

**Organization (`/organization`) / Holidays (`/holidays`).** Viewer-only by design; writes live under `/integrations/erp/**`.

**Reports.** Attendance matrix and leave summary forced to the caller's unit (or, for organization HR, honouring the requested unit/department filter); HR is the only role with `salary_cost.*`, `reports.overtime`, `system.configure`, `audit.view`.

### 4.4 F4 — ORGANIZATION_OWNER (analytics only)

The owner can switch between `My Workspace` and `Executive Workspace`. `MY` shows employee self-service; the Executive dashboard renders `components/dashboard/OwnerDashboard.vue` and has no approval actions.

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
Owner permissions exclude approval and HR operations permissions. The Owner still receives base self-service permissions. Reports give them whole-organization attendance/leave/overtime.

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

OvertimeRecord  PENDING ──approve/reject──▶ APPROVED | REJECTED
  Actions require overtime.approve + row scope; a row lock prevents competing decisions;
  approved_minutes must be positive and no greater than calculated_minutes.
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

`uv run pytest` in `app/api` — 22 modules (~164 tests), mostly async end-to-end service/API tests against a real (test) database.

| Test module | Covers |
|---|---|
| `test_main.py` | root + health endpoints |
| `test_auth_setup.py` | limiter wiring, user schemas, OWNER permission boundary, invalid-login robustness, CORS preflight |
| `test_auth_primitives.py` | token/crypto primitives (refresh entropy + hash-only storage, audience separation, expiry, wrong key), TOTP accept/reject, drift attribution (`match_totp_step` reports the step that matched, and `is_totp_replay` treats only a spent step as reuse), secret-box round-trip/nonce-uniqueness/legacy-plaintext/tamper-and-wrong-key failure, password policy (weak, personal-info, passphrase, breach-checker selection + fail-open), and the throttle rules: per-pair blocking, geometric growth with a cap, short delay for a typo, one employee cannot lock out colleagues, success clears counters, separate refresh budget, key normalisation, store-backend misconfiguration, counter expiry |
| `test_auth_sessions.py` | session lifecycle over HTTP: direct session issuance at login, rotation + old-token rejection, replay of a logged-out token not destroying sibling sessions, logout-everywhere, device listing, idle timeout, absolute timeout that refreshing cannot extend, refresh-TTL expiry, the concurrent-refresh race (exactly one winner), audited reuse detection, malformed tokens |
| `test_auth_hardening_http.py` | every workforce role through one business endpoint, technical↔business door separation, no account enumeration, secret-free auth audit events, login throttling + recovery, refresh-abuse throttling, password change ending all sessions, access token surviving until expiry, HR temporary-password reset revocation + forced change, must-change-password clearing, Super Admin MFA challenge completion, challenge token not usable as an access token, employee MFA opt-in |
| `test_mfa_totp.py` | the second factor's own guarantees: a code authenticates exactly once (and a replay says so), a drifted code is accepted once and then spent, recovery codes are unaffected by TOTP single use, an abandoned replacement keeps the existing factor working (the regression where it used to turn MFA off), confirming a replacement promotes the new seed and retires the old one, a Super Admin is never forced to re-enrol after an abandoned reset, seeds are ciphertext at rest and absent from every response, and recovery codes regenerate/step-up correctly |
| `test_business_role_authorization.py` | the authorization matrix: base permissions for everyone, manager/unit-HR/org-HR/owner/super-admin reach, HR bundle identical across scopes, org scope not conferring owner analytics |
| `test_business_role_provisioning.py` | role assignment/transfer reconciliation (a moved unit HR cannot keep the old unit's scope), legacy-only rows repaired on write, explicit `null` beating a stale legacy `role`, audited role changes |
| `test_permission_grants.py` | static guard: every permission code in the catalog is granted, and every role bundle key is a real role |
| `test_employee_access.py` | permission scope from fixed role, org scope, self-access, out-of-scope rejection |
| `test_attendance_corrections_http.py` | corrections over HTTP, including unit-bounded HR reach and the ERP-confirmation contract |
| `test_invitation_flow.py` | invitation token creation/hashing/validation, password policy (`None` guard) |
| `test_email_service.py` | MIME construction, STARTTLS, reset/invitation/verification/email-changed templates |
| `test_milestone_1.py` | designation CRUD, employee profile + hierarchy |
| `test_milestone_2.py` | shifts (night shift), assignment overlap, cross-midnight window, holiday lists/weekly offs, punch ingest + dedupe |
| `test_milestone_3.py` | attendance processing: full day, late/early exit, half-day/absent thresholds, missed punch, unpunched weekly-off/leave/absent, correction workflow |
| `test_milestone_4.py` | leave period/type, allocation + ledger credit, holiday-aware day count, insufficient balance, approval ledger debit + attendance marking |
| `test_milestone_5.py` | WFH creation/overlap, approval + attendance marking, rejection & cancellation |
| `test_milestone_6.py` | attendance matrix report, leave balance summary report |
| `test_notifications.py` | notification lifecycle |
| `test_notification_audience.py` | role-scoped notification listing and mark-read authorization |
| `test_audit_and_workflows.py` | self-approval prevention (leave/correction/overtime/WFH), early-return day accounting, overtime self-approval + monthly summary filtering, WFH-aware processor, org CRUD validation, detail endpoints, notification + manager dashboard |
| `test_shift_schedule_batching.py` | batched schedule context equals per-date resolution, fallback outside context, upcoming search + schema, single-query employee shift listing |
| `test_migration_setup.py` | Postgres config + Alembic files present |

`tests/auth_helpers.py` holds the shared fixtures those auth suites build on (account/session factories, TOTP code generation, throttle reset).

Frontend: `pnpm typecheck` + `pnpm lint` only (no component/E2E framework yet — a stated gap in `AGENTS.md`). The CSRF/origin checker is pure and was additionally exercised case-by-case end-to-end (cross-origin `POST /api/session/login` → `403` from the BFF middleware; same-origin → upstream), and the whole login → `/users/me` → refresh-rotation → replay-revocation → logout path was driven through a real browser and `curl` against live dev servers.

---

## 8. Gaps, mismatches, and risks

These are verified against the current code and are the highest-value item in this document for leads: **each one is a decision waiting to be made.**

### 8.1 Frontend ↔ backend mismatches (dead UI actions)

| # | Symptom | Root cause | Severity | Decision owner |
|---|---|---|---|---|
| **A1** | ~~Employees page exposes lifecycle actions that fail~~ **Resolved** | Current directory is read-only and explicitly identifies ERP as the source of truth; the HRMS UI no longer offers activate/deactivate/delete actions. Backend lifecycle operations remain ERP-owned. | Resolved | Frontend lead |
| **A2** | ~~Overtime approval methods were unreachable~~ **Resolved** | Scoped `PATCH /overtime/{id}/approve` and `/reject` routes and an `overtime.approve` queue tab now expose the existing workflow. State is locked during action; zero/negative/over-calculated approvals are rejected; self-action is blocked. | Resolved | Backend + Frontend |
| **A3** | ~~Plain employees could see an attendance correction action they could not use~~ **Resolved** | The current UI hides correction submission unless `attendance.correct` is present, and the API enforces the same permission plus row scope. Correction approval is ERP-confirmed; no HRMS approve/reject routes are exposed. | Resolved | Frontend + Backend |
| **A4** | ~~Shifts page create/assign fail~~ **Resolved** | Current Shifts UI only reads ERP-synchronized definitions and assignments; it does not offer create/assign controls. | Resolved | Frontend lead |
| **A5** | ~~Organization page enable/disable/delete fail~~ **Resolved** | Current Organization UI is explicitly read-only; write controls are not rendered because organization master data is ERP-owned. | Resolved | Frontend lead |
| **A6** | Holidays create/add buttons | Hidden by `canManage = false` (correct today) — the code remains and will 405 if ever enabled | Low | Frontend lead |
| **A7** | ~~`attendance.approve_correction` is held by nobody~~ **Fixed** | The correction surfaces now gate on `attendance.correct` (which HR holds) and the approve/reject routes were removed, so `tests/test_permission_grants.py` passes with no dead-end code | Resolved | Architecture lead |
| **A8** | `POST /attendance/checkins` + `/checkins/bulk` are 403 stubs | Intentional (ERP supplies punches) but the punch ingestion path is therefore untested through HTTP; publishing them for ERP would be cleaner than a separate ERP route | Low/Medium | Architecture lead |
| **A9** | Dashboard widget API is not yet consumed | `GET /dashboard/widgets` exists and is permission-aware; workspace dashboards now provide the presentation context, while widget-level composition remains a future consolidation point | Medium | Frontend lead |
| **A10** | Invitation UI missing | `/auth/invitation/*` + email templates exist, `middleware` lists `/invitation` and `/auth/invitation` as public, but no page/route exists and no router calls `create_invitation_for_user` | Medium | Product + Frontend lead |
| **A11** | ~~Mobile Attendance showed “Correction pending” when no correction existed~~ **Resolved** | The mobile row now renders that state only when an actual pending correction matches the record; its correction action also uses the same status/permission conditions as desktop. | Resolved | Frontend |

### 8.2 Functional gaps (backend behaviour)

* **No notification is created for any workflow** — `create_notification` is only used by tests. Applying/approving/rejecting leave or WFH notifies nobody in-app; approvers rely on dashboard/queue polling.
* **`department_approvers` is decorative** — the table exists but no leave/WFH/shift/expense routing consults it; approvals are driven purely by role + unit/department scope.
* **Attendance processing is manual** — no scheduler calls `process_attendance_batch`; someone (or a cron outside this repo) must POST `/attendance/process`.
* Overtime approval records are now reviewable in HRMS; source calculation and record synchronization remain ERP-owned.
* **`leave.manage` grants allocation/type/period writes but allocation has no HTTP endpoint for org-wide bulk runs** — it is service-level only (`LeaveService.allocate_leaves`), exercised by tests.
* **`attendance_discrepancies`** is modelled and seeded but never written by the engine.

### 8.3 Security & correctness notes

* **Stateless access tokens bound the revocation window.** A password change or "sign out everywhere" ends every refresh chain immediately, but an access token already issued stays valid until it expires (15 min business, 5 min privileged) because JWT validation cannot consult the session row. This is deliberate (no per-request session lookup, no cached permissions) and the reason the TTL is minutes — see §2.5.3. A denylist/`jti` check is the upgrade path if that window is ever judged too wide (D7).
* **Super Admin has organization-wide read scope** via `get_permission_scope`; production posture depends on keeping that account break-glass only. Set `MFA_REQUIRED_FOR_SUPER_ADMIN=true` and enrol before going live — the API logs a startup warning while it is off.
* **Throttling is only as shared as its store.** `AUTH_THROTTLE_BACKEND=memory` (the default) means each worker counts separately; production validates against this at startup (D9), but a single-worker deployment still has a single point of failure for the counters.
* **Login throttling feedback**: the BFF forwards the upstream `Retry-After` header and includes the retry countdown in the sign-in error message. The displayed time is the server's retry interval; it is not a client-side lockout timer.
* **Notification audience isolation**: role broadcasts are limited to the linked employee's current business role; global `system` visibility applies only when no target role is set. Listing, unread counts, mark-all, and single mark-read share the same authorization predicate.
* **Anonymous `/health`** leaks DB reachability + uptime (rate-limited to 10/min).
* `ensure_permission(email, path, method)` in `core/auth.py` returns `bool(email)` for everything — dead/placeholder authorization helper; do not build on it.
* Seed defaults (`SuperAdmin@123`, dev JWT secret) are guarded by `validate_runtime_secrets()`; the development shortcut is an explicit allow-list of environment names, so a typo such as `ENVIRONMENT=Production` no longer disables the checks.

---

## 9. Decision register (for architecture / backend / frontend leads)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | **Is this "employees read-only + ERP writes" a temporary migration state or the target?** | (a) target — keep the HRMS views read-only; (b) temporary — implement HRMS write endpoints guarded by `employee.update` | Current implementation follows (a): dead lifecycle controls have been removed; revisit only if ownership moves from ERP. |
| D2 | **Attendance correction governance** | (a) ERP-only confirmation (current server behaviour) — remove approve/reject from UI and stop offering employee submission; (b) allow employee submission + manager approval inside HRMS, ERP reconciles async | (b) matches the product's own permissions and queue UI, but requires deciding who wins conflicts with ERP. Ship (a) as the interim truthful UI |
| D3 | **Overtime approval surface** | (a) add `PATCH /overtime/{id}/approve` and `/reject` + an Approvals tab + notifications; (b) leave overtime read-only | Core scoped actions and the Approvals tab are implemented; in-app notifications remain part of §8.2 |
| D4 | **Notifications on workflow events** | (a) emit on apply/approve/reject/cancel to the actor + approver + employee; (b) keep polling dashboards | (a) — `create_notification` already exists; wire it in the four services and reuse `link`/`reference_id` |
| D5 | **Approver routing** | (a) keep role+scope routing; (b) use `department_approvers` | Decide before exposing more approval types; today the table is misleading |
| ~~D6~~ | ~~**`attendance.approve_correction`**~~ **Settled** | — | Resolved by removing the code and the approve/reject routes, and gating corrections on `attendance.correct` + row scope (§2.6.2). No dead-end permission code remains |
| ~~D7~~ | ~~**Access-token TTL policy**~~ **Settled** | — | Resolved: login issues the session directly (no intermediate 8 h bearer token at all), access tokens are 15 min / 5 min privileged, and refresh chains are revoked on logout, password change, reset, idle and absolute deadlines. The residual window is one access-token TTL and is documented in §2.5.3/§8.3 |
| D8 | **Scheduler** | (a) external cron calling `/attendance/process`; (b) in-process loop like notifications cleanup; (c) Celery/APScheduler | (b) for now (one fewer moving part, matches existing precedent), (c) before horizontal scale |
| D9 | **Rate limiting & sessions at scale** | (a) in-memory limiter + DB sessions (today); (b) Redis for both | Authentication throttling already has a Redis backend (`AUTH_THROTTLE_BACKEND=redis`, validated at startup) — **enable it before running more than one worker**. The generic API limiter is still in-process memory and should move next |
| D10 | **Frontend test strategy** | (a) keep lint/typecheck only; (b) add component tests for the approval queue + login; (c) Playwright E2E over the BFF proxy | (b) now, (c) when D1/D2 stabilise the action surface |
| D11 | **Invitations** | (a) finish the invitation UX (page + send on ERP create, replacing temporary passwords); (b) drop the invitation code path | (a) — templates and token lifecycle are already built and tested |
| D12 | **Docs ownership** | Keep §2.9/§3.5/§8 tables updated in the PR template | Assign a reviewer per area (backend/frontend lead) |

---

## 10. Appendices

### A. Permission catalog (48 codes — base employee 10, DEPARTMENT_MANAGER 20 effective, HR_ADMIN 46 effective, ORGANIZATION_OWNER 21 effective)

`BASE_EMPLOYEE_PERMISSIONS` (10, implicit for every employee) plus each role's additive bundle. `FIXED_ROLE_PERMISSIONS` exposes the `base + bundle` view per role.

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

**Checked in the API but granted to no role:** none — `tests/test_permission_grants.py` asserts both directions (no enforced code is ungranted; no role bundle repeats a base code).

**Granted to some role but never enforced in the API** (safe to keep as forward-compatible vocabulary, hazardous to treat as a security control):
`user.view`, `user.create`, `user.deactivate`, `employee.update`, `employee.deactivate`, `employee.view_self`, `attendance.view_self`, `designation.view/create/update/delete`, `leave.view_self`, `overtime.view_self`, `shift.view_self`, `shift.assign`, `shift.update`, `reports.view`, `reports.overtime`, `reports.salary_cost`, `salary_cost.view_unit`, `salary_cost.view_department`, `audit.view`, `work_arrangement.apply`, `work_arrangement.view_self`.

*Derived by `tests/test_permission_grants.py` (`granted − enforced`), so this list cannot drift silently.*

*Frontend-only gates:* `shift.assign` / `shift.update` are not enforced because shift writes remain ERP-only; current Shifts UI is read-only. `attendance.correct` gates the correction dialog, and the API enforces it as well.

*Enforced today (24):* `employee.view`, `employee.create`, `attendance.view` / `view_unit` / `view_department` / `process` / `correct`, `leave.apply` / `approve` / `reject` / `cancel` / `manage`, `work_arrangement.approve` / `reject` / `cancel` / `manage`, `overtime.view` / `view_department` / `approve`, `reports.attendance` / `reports.leave`, `dashboard.view_organization`, `system.configure` (dashboard widget gating), `user.update` (HR password reset).

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
