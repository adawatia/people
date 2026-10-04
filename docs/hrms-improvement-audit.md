# HRMS improvement audit and delivery report — 2026-09-24

This report records the completed audit, implemented changes, measured evidence, and remaining delivery limits. Severity reflects observed behavior, not hypothetical vulnerabilities. Existing overtime changes were retained and integrated.

## Findings

| Severity | Finding / evidence | Fix and verification |
|---|---|---|
| High | Shared pagination permits `all=true`; business leave/WFH/history/checkins lists are unbounded; notifications and attendance truncate without metadata. | Bounded shared contracts, SQL paging, UI controls, scope/count tests. |
| High | Report attendance query omits employee predicate when scope yields no employees; leave report performs per-employee balance queries. | Always constrain records; paginate employees and batch balances; PostgreSQL query-count tests. |
| High | BFF catches errors from a retried business request as refresh failures. | Separate refresh and retry error handling; regression test. |
| High | Password recovery converts `InvalidPasswordException` with `str(exc)`; FastAPI Users stores its policy explanation in `exc.reason`, yielding an empty 400 detail and the BFF’s generic service error. | Return the safe policy reason from recovery and password-change routes; BFF preserves 400 details and 422 validation messages; focused regression tests. |
| High | Authenticator replacement compares a code from the new secret with the replay counter belonging to the old secret. Both secrets use the same time counter, so confirmation in the current 30-second interval is rejected. | Treat the pending secret as a new factor, record its first accepted step only after promotion, preserve replay protection for subsequent verification, and cover same-step replacement in PostgreSQL tests. |
| Medium | Employee eager loading includes complete history even in authentication and list requests. | Remove history from general loading; dedicated paginated history. |
| Medium | Dashboard SQL in routers; repeated scope resolution and page-derived metrics. | Move read orchestration/query logic; request-context reuse and independent aggregates. |
| Medium | Five mobile nav items; workspace selector buried in More; links carry unrelated queries. | Four primary items and dedicated workspace sheet; navigation tests. |
| Medium | Volatile list state, inconsistent controls, native confirmations, purple-heavy tokens. | Shared URL state, pagination, clear filters, modals, theme tokens. |
| Low | Repeated status styles, chart hard-coded colors, inconsistent labels. | Shared presentation and accessible text/dark variants. |

## Router inventory

Every decorated endpoint below was inventoried for method, auth dependencies, response shape and consumer coverage. ERP routes retain their ownership boundary and now support scoped signed clients and idempotent master-data upserts. A technical, read-only paginated audit API was added; no workforce audit page was introduced.

- `app/api/routers/attendance.py`: GET /checkins, GET /, GET /records/{record_id}, GET /employee/{emp_id}/calendar, GET /employee/{emp_id}/summary, POST /process, POST /corrections, GET /corrections
- `app/api/routers/auth_invitation.py`: GET /validate, POST /set-password
- `app/api/routers/auth_login.py`: POST /employee/login, POST /super-admin/login, POST /password-recovery/start, POST /password-recovery/verify, POST /password-recovery/reset, POST /change-password, PATCH /super-admin/username, POST /hr/employees/{employee_id}/password-reset, POST /integrations/erp/employees/{employee_id}/password-reset
- `app/api/routers/auth_mfa.py`: POST /enroll, POST /activate, POST /verify, GET /status, POST /confirm, POST /recovery/regenerate, POST /reset, POST /disable
- `app/api/routers/auth_sessions.py`: POST /session, POST /session/refresh, DELETE /session, GET /sessions, DELETE /sessions, DELETE /sessions/{session_id}, GET /session
- `app/api/routers/dashboard.py`: GET /owner, GET /owner/exceptions, GET /technical-metrics, GET /widgets, GET /metrics
- `app/api/routers/departments.py`: GET , GET /{dept_id}
- `app/api/routers/designations.py`: GET /, GET /{designation_id}
- `app/api/routers/employees.py`: GET /, POST /onboard, GET /{emp_id}, GET /{emp_id}/work-history
- `app/api/routers/erp_attendance.py`: POST /records, POST /records/bulk
- `app/api/routers/erp_employees.py`: PATCH /{employee_id}, PATCH /{employee_id}/deactivate, PATCH /{employee_id}/activate, POST
- `app/api/routers/erp_holidays.py`: POST /bulk
- `app/api/routers/erp_leaves.py`: GET /changes, POST /changes/ack, POST /balances, POST /balances/bulk
- `app/api/routers/erp_master_data.py`: PATCH /organization, POST /units, PATCH /units/{unit_id}, DELETE /units/{unit_id}, POST /departments, PATCH /departments/{department_id}, DELETE /departments/{department_id}, POST /designations, PATCH /designations/{designation_id}, DELETE /designations/{designation_id}
- `app/api/routers/erp_overtime.py`: POST /records/bulk
- `app/api/routers/erp_shifts.py`: POST , PATCH /{shift_id}, POST /assignments, POST /assignments/bulk, PATCH /assignments/{assignment_id}/cancel
- `app/api/routers/holidays.py`: GET /lists, GET /lists/{list_id}
- `app/api/routers/leaves.py`: GET /periods, POST /periods, GET /types, POST /types, GET /types/{type_id}, PATCH /types/{type_id}, GET /balance/employee/{emp_id}, GET /, GET /{app_id}, POST /, PATCH /{app_id}/approve, PATCH /{app_id}/reject, PATCH /{app_id}/cancel, PATCH /{app_id}/cancellation/approve, PATCH /{app_id}/cancellation/reject
- `app/api/routers/notifications.py`: GET , GET /unread-count, PATCH /{id}/read, POST /mark-all-read
- `app/api/routers/audit.py`: GET (technical-only paginated security-event listing)
- `app/api/routers/organizations.py`: GET
- `app/api/routers/overtime.py`: GET /, GET /{ot_id}, GET /employee/{emp_id}/summary, PATCH /{ot_id}/approve, PATCH /{ot_id}/reject
- `app/api/routers/reports.py`: GET /attendance-matrix, GET /leave-summary
- `app/api/routers/shifts.py`: GET /, GET /assignments, GET /assignments/{assignment_id}, GET /employee/{emp_id}/schedule, GET /{shift_id}
- `app/api/routers/units.py`: GET , GET /{unit_id}
- `app/api/routers/users.py`: GET /me, GET /me/permissions
- `app/api/routers/work_arrangements.py`: GET /, GET /{req_id}, POST /, PATCH /{req_id}/approve, PATCH /{req_id}/reject, PATCH /{req_id}/cancel

## Frontend / query inventory

Pages, BFF handlers and repositories reviewed for list shape, actions, filters and loading states:

- `app/web/app/pages/admin/login.vue` (149 lines)
- `app/web/app/pages/approvals/index.vue` (559 lines)
- `app/web/app/pages/attendance/index.vue` (609 lines)
- `app/web/app/pages/employees/[id].vue` (169 lines)
- `app/web/app/pages/employees/index.vue` (196 lines)
- `app/web/app/pages/forgot-password.vue` (89 lines)
- `app/web/app/pages/holidays/index.vue` (117 lines)
- `app/web/app/pages/index.vue` (348 lines)
- `app/web/app/pages/leaves/index.vue` (641 lines)
- `app/web/app/pages/login.vue` (184 lines)
- `app/web/app/pages/notifications.vue` (124 lines)
- `app/web/app/pages/organization/index.vue` (164 lines)
- `app/web/app/pages/overtime/index.vue` (281 lines)
- `app/web/app/pages/profile.vue` (128 lines)
- `app/web/app/pages/reports/index.vue` (231 lines)
- `app/web/app/pages/settings.vue` (526 lines)
- `app/web/app/pages/shifts/index.vue` (139 lines)
- `app/web/app/pages/work-arrangements/index.vue` (408 lines)
- `app/web/server/api/hrms/[...path].ts` (55 lines)
- `app/web/server/api/session/index.delete.ts` (24 lines)
- `app/web/server/api/session/login.post.ts` (69 lines)
- `app/web/server/api/session/me.get.ts` (47 lines)
- `app/web/server/api/session/mfa/enroll.post.ts` (25 lines)
- `app/web/server/api/session/mfa.post.ts` (48 lines)
- `app/web/server/api/session/password-recovery/reset.post.ts` (12 lines)
- `app/web/server/api/session/password-recovery/start.post.ts` (12 lines)
- `app/web/server/api/session/password-recovery/verify.post.ts` (12 lines)
- `app/web/server/middleware/csrf.ts` (28 lines)
- `app/web/server/utils/hrms.ts` (136 lines)
- `app/web/server/utils/origin.ts` (85 lines)
- `app/api/repositories/attendance_punch_repo.py` (72 lines)
- `app/api/repositories/attendance_record_repo.py` (146 lines)
- `app/api/repositories/auth_session_repo.py` (108 lines)
- `app/api/repositories/designation_repo.py` (35 lines)
- `app/api/repositories/employee_repo.py` (152 lines)
- `app/api/repositories/holiday_repo.py` (69 lines)
- `app/api/repositories/leave_repo.py` (251 lines)
- `app/api/repositories/org_repo.py` (77 lines)
- `app/api/repositories/overtime_repo.py` (93 lines)
- `app/api/repositories/shift_repo.py` (193 lines)
- `app/api/repositories/work_arrangement_repo.py` (76 lines)

## Validation boundary

Staging is the configured `app/api/.env` database: read-only transactions only. All tests and migrations must explicitly use isolated PostgreSQL on port 55439. No staging credentials or employee records are included in this report.

## Pagination and API contract coverage

Every growing business list now defaults to 25 rows, rejects sizes above 100, applies authorization and domain filters before counting, validates sort fields through an allowlist, and adds the row identifier as a deterministic ordering tie-breaker. Each `sort_by` query parameter publishes that endpoint's exact allowlist as an OpenAPI enum, so Nuxt and other generated clients can discover the supported keys. `search` is the public search parameter. Responses use the shared `PaginatedResponse` metadata (`total`, `page`, `page_size`, `total_pages`, `has_next`, `has_prev`).

| Dataset / consumer | Endpoint | Search and sort contract | Scope and count behavior | Result |
|---|---|---|---|---|
| Employees / Employees page and remote selectors | `GET /employees/` | `search`, `sort_by`, `sort_order`; code/name/created/status allowlist | Employee, department, unit, or organization scope is applied before count | Complete |
| Employee history / Employee detail | `GET /employees/{id}/work-history` | Search remarks; from/to/created/id sort allowlist | Parent employee access is checked before the history query | Complete |
| Attendance / Attendance page | `GET /attendance/` | Employee search; date/status/id sort allowlist | Self, department, unit, and organization filters precede count | Complete |
| Raw punches / attendance operations | `GET /attendance/checkins` | Employee search; time/type/source/processed/id sort allowlist | Same attendance scope; raw data remains read-only from HRMS | Complete |
| Corrections / Attendance page | `GET /attendance/corrections` | Employee search; request time/status/id sort allowlist | Self or authorized management scope before count | Complete |
| Leave applications / Leave and Approvals pages | `GET /leaves/` | Employee search; applied/status/id sort allowlist | Self or authorized management scope before count | Complete |
| Leave periods and types / forms and filters | `GET /leaves/periods`, `GET /leaves/types` | Name search; name/id sort allowlist | Active/type filters precede count | Complete |
| Work arrangements / Work Arrangements and Approvals pages | `GET /work-arrangements/` | Employee search; created/status/id sort allowlist | Self or authorized management scope before count | Complete |
| Overtime / Overtime and Approvals pages | `GET /overtime/` | `search`; attendance date/status/id allowlist | Self, department, unit, or organization scope before count | Complete |
| Shift definitions / Shifts page and selectors | `GET /shifts/` | Name search; name/code/start/id sort allowlist | Unit or employee-visible definitions before count | Complete |
| Shift assignments / Shifts page | `GET /shifts/assignments` | Employee search; effective date/status/id allowlist | Central employee access scope is part of the SQL query | Complete |
| Notifications / Notifications page | `GET /notifications` | Title search; created/id sort allowlist | Personal and role audience predicate precedes count | Complete |
| Attendance report rows / Reports page | `GET /reports/attendance-matrix` | Employee search; employee code/name allowlist | Employees are paged first; records are batch-loaded only for that page; full-filter totals are independent | Complete |
| Leave report rows / Reports page | `GET /reports/leave-summary` | Employee search; employee code/name allowlist | Employees are paged first; balances are batch-loaded; breakdown totals use the complete filtered population | Complete |
| Owner exception drill-down / Executive dashboard | `GET /dashboard/owner/exceptions` | Employee search; code/name/unit/department/id allowlist | Organization permission and optional unit predicate precede count; employee hydration is one bounded batch | Complete |
| Workforce login accounts / Technical Administration | `GET /users/admin/accounts` | Name, username, email, mobile and employee-code search; username/email/created/status/id allowlist | Explicit Super Admin gate precedes the query; Super Admin accounts are excluded from support actions | Complete |
| Units, departments, designations, holiday lists / lookup selectors | respective list endpoints | Name search; name/id sort allowlist | Domain filters precede count; remote selectors search server-side | Complete |

The following collections are deliberately bounded rather than paginated: one employee-month attendance calendar, one employee-month attendance or overtime summary, one employee's leave balances by leave type, one employee's effective shift schedule window, one holiday list's entries, the current user's policy-limited authentication sessions, widget definitions, and aggregate dashboard series. ERP ingestion and change-feed contracts retain their integration shapes.

Approval types remain three independent paginated datasets. Their totals come from their own filtered responses; records are not downloaded, merged, and paginated in the browser.

## PostgreSQL scope and ordering verification

`tests/test_list_scope_matrix.py` creates two isolated organizational scopes and deliberately gives rows equal primary sort values. It then repeats page 1 and reads page 2 to prove stable ordering, no page overlap, and no records from the other scope. Coverage includes employees, attendance records, attendance punches, leave applications, work arrangements, overtime, shift assignments, employee history, notifications, and shift definitions. `tests/test_list_contracts.py` separately verifies filter/count agreement, escaped search input, invalid pagination and sort rejection, report aggregation over the full filter, employee-first report paging, and bounded query counts. `tests/test_sort_openapi_contract.py` verifies that every public `sort_by` parameter documents the same finite allowlist enforced by its repository.

All database tests require an explicit PostgreSQL URL whose database name ends in `_test`. SQLite is no longer a permitted test fallback, and the overtime pagination regression test uses the isolated PostgreSQL database.

Focused result on 2026-09-24: `4 passed` for `test_list_scope_matrix.py` plus `test_list_contracts.py`. The complete gate result is recorded in the final verification section below.

## Performance acceptance evidence

### Method

Staging inspection used the connection already configured in `app/api/.env`, read-only transactions, bounded `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` statements, and aggregate counts only. No staging writes, migrations, or write-capable tests were run. The before/after report comparison used the same isolated PostgreSQL dataset of 200 synthetic employees and identical report parameters so old per-employee retrieval and the new employee-page/batch implementation could be compared directly.

### Dataset and plans observed on staging

| Table | Rows observed |
|---|---:|
| Employees | 2,981 |
| Attendance records | 1,300 |
| Leave applications | 230 |
| Work arrangement requests | 263 |
| Leave balances | 336 |
| Notifications | 43 |
| Overtime records | 77 |

| Representative page | Rows requested | Execution | Buffers / plan summary |
|---|---:|---:|---|
| Employees ordered by code + id | 25 | 0.233 ms | 29 shared hits; employee-code index scan plus incremental in-memory sort |
| Attendance ordered by date + id | 25 | 0.166 ms | 23 shared hits; 1,300-row sequential scan plus 30 kB top-N sort |
| Leave ordered by applied time + id | 25 | 0.136 ms | 7 shared hits; 230-row sequential scan plus 35 kB top-N sort |
| Work arrangements ordered by created time + id | 25 | 0.059 ms | 5 shared hits; 263-row sequential scan plus 32 kB top-N sort |

Sequential scans are appropriate at the observed staging sizes: each plan remained memory-only and below 0.2 ms. The employee list already uses `ix_employees_employee_code`; row-scope joins are supported by existing employee unit/department indexes; relationship loading is supported by employee foreign-key indexes on attendance, punches, leave, work arrangements, overtime, history, and shift assignments; notification time and audience-user access has existing created/user indexes. No new index migration was added because measured plans did not demonstrate an index deficit. Adding speculative compound indexes would increase write and maintenance cost without measured benefit. Re-evaluate only when production-like cardinality or latency shows a specific scan as material.

### Identical isolated report benchmark

| Implementation | SQL statements | Elapsed | Serialized payload |
|---|---:|---:|---:|
| Previous per-employee retrieval | 402 | 290.58 ms | 55,131 bytes |
| Employee-page plus bounded batches | 6 | 14.11 ms | 6,595 bytes |
| Change | 98.5% fewer | 95.1% faster | 88.0% smaller |

The payload reduction is expected because only the requested employee page is returned while the SQL aggregate still covers the complete filtered set. The measured query count stays bounded as page size changes.

### Measurement limitations

The old application build was not deployed to staging, so a staging endpoint before/after comparison was neither possible nor fabricated. The comparable before/after figures above are isolated PostgreSQL results; the staging figures are post-change read-only plan observations. Staging volumes are small for attendance and request tables and do not represent a future production peak. The index decision is therefore valid for the measured access patterns and must be revisited with production-like data if those tables grow materially.

## Final route and action verification register

| Route group | Reads and visible actions checked | Authorization, ownership, and workflow result |
|---|---|---|
| Attendance | Punch list, attendance list/detail/calendar/summary, correction submission/list, processing and ERP punch rejection | Read scope is self/department/unit/organization; correction requires `attendance.correct`; raw punch and ERP ownership boundaries remain enforced; list contracts complete |
| Invitations and login | Invitation validation/password setup; employee/admin login; recovery start/verify/reset; password change and administrative reset | Generic identity responses, password policy reasons, recovery capability expiry, TOTP replay distinction, session revocation, and admin/ERP gates verified |
| MFA | Enroll, activate, verify, status, replace/confirm, regenerate recovery codes, reset, disable | Pending-secret confirmation no longer inherits the old factor's replay counter; accepted steps remain single-use after activation; policy restrictions retained |
| Sessions | Create, refresh, current session, list/revoke one/revoke others/logout | Cookie, CSRF, absolute/idle expiry, rotation, and ownership checks retained; bounded by session policy |
| Dashboard | Owner aggregate, owner exceptions, technical metrics, widgets, personal metrics | Owner permission gates and audit events retained; query orchestration resides in services/repositories; exception drill-down is paginated and batched |
| Organization lookups | Organization, units, departments, designations, holiday lists/detail | Authenticated reads; growing lookups use remote paginated search; ERP remains owner of mutations |
| Employees | Directory, detail, history, onboarding endpoint | Directory/history scoped and paginated; UI shows ERP ownership and does not expose unsupported create/edit actions; onboarding permission remains server-enforced |
| Leave | Period/type configuration, balance, application create/read, approval/rejection/cancellation and cancellation decision | Permission plus row-scope checks occur before actions; state transitions remain the existing workflow; application and lookup lists complete |
| Work arrangements | Create/read/list, approve/reject/cancel | Self and management scopes retained; action permissions and state checks remain server-side; list contract complete |
| Overtime | List/detail/summary, approve/reject | Existing overtime changes preserved; approval permission no longer depends on unrelated approval types; ERP record ownership retained; list contract complete |
| Shifts | Definitions, assignments, assignment detail, employee schedule | List and detail scope checks use central employee scope; definitions/assignments paginated; ERP owns shift mutations |
| Notifications | List, unread count, read one, mark visible as read | Personal and normalized role audiences are applied to reads and updates; queue count is independent; list contract complete |
| Reports | Attendance matrix and leave summary | Explicit report permission and forced row scope; employees paged before related data; full-filter SQL aggregates are independent of the page |
| ERP attendance/employees/holidays/leaves/master data/overtime/shifts | Existing ingest, acknowledgement, activation, synchronization, and idempotent master-data upserts | Scoped HMAC client authentication, timestamp validation and nonce replay protection replace the shared production key; the legacy key is development-only; ERP ownership remains unchanged |

## Page and BFF verification register

| Page / handler | Visible behavior and actions checked | Result |
|---|---|---|
| Home and owner dashboard | Real aggregate cards/charts, exception drill-down, loading/error/empty states | Permission-aware and responsive; no fabricated metrics or unsupported detail tabs |
| Employees and employee detail | Search/filter/page, remote unit/department lookup, profile/history | URL state and paging retained through refresh/navigation; ERP-only actions are explained rather than offered |
| Attendance | Attendance and correction datasets, date/status filters, correction submission | Separate list states, mobile cards/desktop table, retry/empty/loading states, server-scoped actions |
| Leave | Search/filter/page, create, approve/reject/cancel and cancellation decisions | Confirmations use Nuxt UI modal; actions refresh the relevant paginated data |
| Work arrangements | Search/filter/page, create, approve/reject/cancel | Confirmations and permission visibility aligned with API actions |
| Overtime | Month/status/search/page, approve/reject | Existing pagination integrated; independent approval queue and count retained |
| Approvals | Leave, work arrangement, and overtime queues | Three independent paginated requests and URL prefixes; counts do not depend on downloading all rows |
| Shifts, holidays, organization | Remote search, filters and pagination | Standard list controls and meaningful empty/error states |
| Notifications | Search/read filter/page, read one/read all | Visible audience only; unread count fetched separately |
| Reports | Search/sort/page, month/year, contained attendance matrix, leave chart/table | Page rows and full-filter totals agree; comparison-heavy report remains horizontally scrollable |
| Profile and settings | Profile, password, MFA enrollment/replacement/recovery and technical settings | Recovery-session reset handling and new-factor confirmation fixed; policy/permission gating retained |
| Mobile/desktop layout | Home, Workspace, contextual section, More; desktop sidebar selector | Exactly four mobile destinations; permission-filtered defaults and Profile fallback; Technical-only Super Admin; workspace switching does not carry list queries |
| `server/api/hrms/[...path].ts` and `server/utils/hrms.ts` | Cookie forwarding, CSRF, one refresh flight, one business retry | A failed post-refresh retry preserves its real upstream status and detail instead of ending the session |
| Session and recovery BFF handlers | Login/logout/me/MFA/recovery proxying | Secure cookie attributes and same-origin checks retained; safe 400/422 details reach the UI |

## Final verification and remaining limits

The change set includes focused regression coverage for BFF retry status preservation, URL list state, stale request handling, workspace navigation, MFA replacement/recovery, PostgreSQL pagination, counts, scope isolation, deterministic ordering, and report query bounds. Final results on 2026-09-24:

- Backend: `206 passed` against isolated PostgreSQL; one non-failing Starlette/httpx test-client deprecation warning remains.
- Python quality: `uv run ruff check .` passed.
- Frontend: `pnpm lint`, `pnpm typecheck`, and `pnpm build` passed.
- Frontend regressions: 4 Node test files passed (`bff`, `list-state`, `upstream-error`, `workspace`).
- Build notices: Nuxt reports a large client chunk and plugin timing advice; these are performance warnings, not build failures.

Production deployment is outside this work. The final delivery may include a review branch and pull request; it does not apply migrations or deploy the application. Browser checks are automated at the composable/navigation/BFF level and supplemented by responsive Nuxt build review; a live authenticated Playwright pass against every role and real ERP integration remains an environment-dependent acceptance activity.
