# ERP ↔ People HRMS integration — implementation status

Date: 2026-10-21 · Branch: `development` · API: `app/api` (FastAPI, SQLAlchemy
async, PostgreSQL, Alembic)

Status labels: `[x]` implemented and verified · `[ ]` not completed ·
`[!]` blocked / needs approval · `[N/A]` verified not applicable.

---

## 1. Summary

The integration was hardened end to end on the HRMS side:

1. **Leave events can no longer be lost.** Every leave decision now writes an
   immutable `erp_outbox_events` row in the same transaction as the state
   change. Previously a single `erp_event_id` column was overwritten by the next
   transition, so an unacknowledged `APPROVED` event disappeared when the leave
   was cancelled.
2. **The feed has a correct cursor.** Polling uses a monotonic outbox
   `sequence`, not `actioned_at`. Equal timestamps, NULL timestamps, page
   boundaries and restarts can no longer hide events. Fetching never
   acknowledges.
3. **Acknowledgement is idempotent and honest.** It reports newly acknowledged,
   already acknowledged and unknown ids separately, survives duplicates, and
   never masks a newer event for the same leave.
4. **Attendance identity is explicit.** `erp_record_id` is the business key; a
   replay is a `duplicate`, changed values are an audited correction, a second
   id for an occupied employee/date is a permanent conflict, and a row HRMS
   created is adopted (audited). Records commit per chunk of 500 with one
   advisory-lock statement per chunk.
5. **Every bulk endpoint answers the same envelope** (`batch_id`, counts,
   per-item `status`/`code`/`message`/`retryable`), with sanitised errors and a
   durable `erp_sync_batches` audit row. Raw exception text no longer reaches
   ERP.
6. **Operations can see the integration**: pending-event count and age, last
   delivery, per-entity 24-hour batch counts, replay-protection backend, plus
   dry-run reconciliation for attendance and leave balances.
7. **HMAC/replay protection was already hardened** in the prior increment
   (shared Redis nonce store, fail-closed in production, 409 on replay); this
   increment adds end-to-end tests for it.

---

## 2. Files by feature

### Durable outbox and change feed
- `app/api/db/models.py` — `ErpOutboxEvent`, `ErpSyncBatch`
- `app/api/services/erp_outbox.py` — **new**: `enqueue_leave_event`, `pending_event_count`
- `app/api/services/leave_service.py` — approve / reject / cancel / cancellation-approve stage one event in-transaction
- `app/api/routers/erp_leaves.py` — sequence-cursor feed, idempotent ack, envelope for balances

### Attendance and idempotency
- `app/api/routers/erp_attendance.py` — rewritten: identity/conflict/correction/adoption rules, chunk commits, batched advisory locks
- `app/api/core/erp_sync.py` — added `acquire_erp_upsert_locks` (one lock statement per chunk)
- `app/api/routers/erp_overtime.py` — envelope, ownership validation, IntegrityError-as-duplicate
- `app/api/routers/erp_holidays.py` — envelope, date-conflict detection, audited removal
- `app/api/services/shift_service.py` — `resolve_bulk_assignment_targets`, `stage_bulk_assignment`, `assignment_read_for`
- `app/api/routers/erp_shifts.py` — per-employee bulk result envelope
- `app/api/routers/erp_employees.py` — envelope, batched locks, sanitised errors
- `app/api/routers/erp_master_data.py` — envelope for units/departments/designations
- `app/api/schemas/erp_bulk.py`, `app/api/schemas/employees.py` — removed the competing result models

### Shared contract, observability, reconciliation
- `app/api/core/erp_batch.py` — **new**: `ErpBatchResult`, `ErpItemResult`, `ErpItemError`, `classify_erp_error`, `apply_batch_status`, `record_batch`, `resolve_batch_id`
- `app/api/routers/erp_operations.py` — **new**: `/sync/status`, `/sync/pending-events`, `/reconciliation/attendance`, `/reconciliation/leave-balances`
- `app/api/core/erp_nonce_store.py` — `backend` / `is_shared` diagnostics
- `app/api/core/settings.py` — `ERP_SYNC_STALE_AFTER_SECONDS`, `ERP_OUTBOX_RETENTION_DAYS`
- `app/api/main.py` — registers the operations router

### Tests
- `app/api/tests/test_erp_leave_outbox.py` — **new**, 14 tests
- `app/api/tests/test_erp_leave_workflow_events.py` — **new**, 7 tests
- `app/api/tests/test_erp_attendance_sync.py` — **new**, 9 tests
- `app/api/tests/test_erp_bulk_contract.py` — **new**, 8 tests
- `app/api/tests/test_erp_operations.py` — **new**, 5 tests
- `app/api/tests/test_erp_hmac.py` — **new**, 11 tests
- `app/api/tests/test_erp_bulk_upserts.py`, `tests/test_bulk_lookup_efficiency.py`, `tests/test_api_contract_cleanup.py` — updated to the envelope / conflict policy / new route count
- `app/api/tests/test_leave_balance_concurrency.py` — fixed test-harness defects (real approver FK, non-overlapping ranges, stale identity-map read, awaited sync helper)

### Documentation
- `docs/erp-integration.md` — **new**: full contract (ownership, auth, envelope, codes, cursor/ack, retention, ERP retry requirements, reconciliation runbook, migration)
- `docs/system-architecture-and-flows.md` — §2.8 table, F6 flows, env vars, glossary
- `docs/frontend-backend-gaps.md` — ERP sync operations row
- `docs/erp-test/endpoints.js`, `docs/erp-test/README.md` — cursor/ack/envelope guidance
- `app/api/.env.example` — new settings
- `ERP_HRMS_IMPLEMENTATION_STATUS.md` — this file

---

## 3. Schema changes

New migration: `app/api/alembic/versions/3d4e5f607182_erp_outbox_and_batch_audit.py`
(`down_revision = 2c3d4e5f6071`).

| Object | Purpose |
|---|---|
| `erp_outbox_events` (`sequence` BIGSERIAL PK, `event_id` unique, `entity_type`, `entity_id`, `event_type`, `payload` JSONB, `created_at`, `last_delivered_at`, `delivery_attempts`, `acknowledged_at`, `acknowledged_by`) | Durable per-transition event log |
| `ix_erp_outbox_events_pending` partial index on `(entity_type, sequence) WHERE acknowledged_at IS NULL` | Makes the poll proportional to the backlog |
| `ix_erp_outbox_events_entity`, `ix_erp_outbox_events_event_id` | Reconciliation and identity lookups |
| `erp_sync_batches` (`batch_id` PK, `endpoint`, `client_id`, counts, `status`, `http_status`, `last_error_code`, timestamps) | Durable audit of every bulk request |
| Backfill | Copies currently-pending (`erp_sync_status <> 'ACKNOWLEDGED'`) leave outcomes into the outbox so the migration cannot drop an event |

No existing migration was modified. No table or column was dropped.

---

## 4. Contract changes and compatibility

Full detail in `docs/erp-integration.md` §10. In short:

- **Breaking**: bulk responses are now the batch envelope; `accepted[]`/`failed[]`/`duplicates[]` are replaced by `items[]` with `status`.
- **Breaking**: `POST /shifts/assignments/bulk` returns the envelope instead of a list.
- **Changed**: `GET /leaves/changes` is cursor-based (`cursor` / `next_cursor`). `since` still works for one transition window and is mapped tie-safely (`created_at < since`), so it redelivers rather than skips.
- **Additive**: ack accepts `{"event_ids": [...], "batch_id": "..."}` and still accepts a bare array; response adds `already_acknowledged`, `pending_remaining`, `batch_id`.
- The ERP client must be updated in the same maintenance window for bulk writes; the feed keeps working for legacy clients in the meantime.

---

## 5. Verification performed

Commands (from `app/api`):

```bash
uv run pytest -q                     # 289 passed, 3 warnings, 253s
uv run ruff check .                   # All checks passed
uv run alembic current                # 3d4e5f607182 (head)
uv run alembic downgrade -1 && uv run alembic upgrade head   # reversible + backfill re-runs
```

Empty-database migration: created a disposable local PostgreSQL database
(`hrms_migration_check`) on the configured server, ran `alembic upgrade head`
with `DATABASE_URL` pointed at it (exit 0, `current` = `3d4e5f607182 (head)`),
then dropped it. The full chain applies from scratch.

HTTP smoke test through `TestClient` with real HMAC signatures (settings and
nonce store patched for a synthetic client):

- `GET /api/v1/integrations/erp/sync/status` → 200, feed + per-entity + nonce diagnostics;
- `GET /leaves/changes?limit=5` → 200 with `items`, `has_more`, `next_cursor`, `pending_count`;
- `POST /leaves/changes/ack` with an unknown id → 200, `unknown` populated, nothing acknowledged;
- replaying an identical signed request → second call `409`.

Concurrency and constraint behaviour is tested against real PostgreSQL (two
sessions), not SQLite or mocks: concurrent identical attendance chunk → one
`accepted` + one `duplicate`; concurrent leave applications → one success.

---

## 6. Remaining blockers / ERP-side requirements

`[!]` **ERP client update is required and is not in this repository.** The ERP
must: persist `next_cursor`, ack only after durable processing, send a fresh
nonce per retry, retry only `retryable` items with exponential backoff + jitter,
and resend partially failed pages with the same `X-ERP-Batch-Id`. No ERP code was
modified or claimed to be.

`[!]` **No source revision metadata.** ERP does not send a version/revision for
attendance or master data, so an out-of-order older payload can overwrite a newer
one in arrival order. Documented as a limitation; the safe fix requires an ERP
contract addition (e.g. `revision`), which needs product approval.

`[!]` **Acknowledgement retention needs an operator job.** The API does not
schedule pruning. The `DELETE` statement in `docs/erp-integration.md` §6 must be
run by ops (cron/`pg_cron`) using the configured `ERP_OUTBOX_RETENTION_DAYS`.

`[!]` **Production replay protection depends on Redis.** If `REDIS_URL`/the
shared client is missing in production, ERP requests fail closed with 503
(by design). `GET /sync/status` reports `memory` + `replay_protection_shared=false`
so this is visible before it causes an outage.

`[ ]` **Password-reset and shift-assignment routes keep their existing shapes.**
Single-record endpoints are unchanged by design; only bulk endpoints were
standardised.

`[ ]` **No HRMS UI for ERP backlog/reconciliation.** Deliberately API-only
(operator tooling, not an end-user page); recorded in
`docs/frontend-backend-gaps.md`.

`[N/A]` **Message broker.** A PostgreSQL outbox is sufficient for a
single-consumer pull feed; no Kafka/RabbitMQ was added.

`[N/A]` **Full ERP snapshot reconciliation.** The HRMS can only diff what the
ERP posts; a complete "everything the ERP has" comparison needs an ERP export
endpoint, which does not exist.

---

## 7. Deployment and configuration

1. Review `docs/erp-integration.md` §9.
2. `uv run alembic upgrade head` (creates both tables and backfills pending
   leave events; safe to re-run, no destructive statements).
3. Configure `ERP_API_CLIENTS`, `REDIS_URL`, `ERP_SYNC_STALE_AFTER_SECONDS`
   (default 86400), `ERP_OUTBOX_RETENTION_DAYS` (default 90).
4. Deploy the API, then update the ERP client to the envelope/cursor contract.
5. Verify `GET /integrations/erp/sync/status` shows `nonce.backend = "redis"`,
   `replay_protection_shared = true`, and a `pending_events` figure that drains
   after the ERP acks.
6. Schedule the retention `DELETE` and an alert on `feed.behind_schedule`.

---

## 8. Checklist

### Change feed and acknowledgement
- [x] Unacknowledged events cannot become permanently invisible
- [x] Sequence cursor (no timestamp-only cursor; equal timestamps are ordered)
- [x] Stable, deterministic event id (`LEAVE-{id}-{EVENT}`)
- [x] Redelivery until acknowledged
- [x] Idempotent acknowledgement (duplicates, already-acknowledged)
- [x] Unknown/foreign ids reported, not written
- [x] Fetch never acknowledges
- [x] Durable across HRMS restarts (database-backed)
- [x] Partial acknowledgement supported
- [x] Old cursor replays safely
- [x] New events during processing are delivered next page

### Outbox
- [x] Immutable event rows with entity/type/payload/timestamps
- [x] Written in the same transaction as the business change
- [x] No duplicate event on retried transitions
- [x] Deterministic pagination and ordering
- [x] Attempt/last-delivery tracking
- [x] Retention documented with a maintenance query

### Idempotency and concurrency
- [x] Unique ERP identity constraints relied on and enforced (employees, master
      data, attendance, overtime, holidays)
- [x] Transaction-safe upserts with advisory locks (single + batched)
- [x] Exact duplicate vs correction vs conflict for attendance
- [x] Concurrent identical attendance requests resolve to one row
- [x] Concurrent identical employee upserts serialised by lock
- [x] Failed item rolls back only its savepoint
- [x] Mixed-success bulk pages commit accepted items

### Bulk contract
- [x] `batch_id`, received/accepted/duplicate/failed/retryable counts
- [x] Per-item key, status, id, code, message, retryable
- [x] No raw exception text, SQL, or stack traces in responses
- [x] Server-side logging with batch id
- [x] Transient vs permanent classification; 503 + `Retry-After` for all-transient pages
- [x] `X-ERP-Batch-Id` echo and `erp_sync_batches` audit row
- [x] Empty/malformed batch rejected before any write

### Authentication
- [x] Method, path+query, timestamp, nonce, body hash in the signature
- [x] Constant-time comparison; body hashed once
- [x] Timestamp window and replay rejection
- [x] Scope validation, generic auth failures, 32+ char secrets
- [x] Shared atomic nonce store; fail closed when unavailable
- [x] Concurrent replay allows exactly one request

### Business workflows
- [x] Leave approve/reject/cancel enqueue exactly one event in-transaction
- [x] Failed approval rolls back both state and event
- [x] Repeated/invalid transitions produce no extra events
- [x] Ack never masks a newer event
- [x] Overtime approval fields remain HRMS-owned
- [x] Attendance correction preserves the ERP confirmation boundary (HRMS never
      overwrites `ERP_CONFIRMED` values; ERP reconciliation remains authoritative)

### Observability and reconciliation
- [x] Pending count, oldest age, last delivery
- [x] Per-entity last batch / last accepted / 24h counts / last error code
- [x] Replay-protection backend visibility
- [x] Attendance and leave-balance dry-run reconciliation with `apply` switch
- [x] Missing-in-ERP is window-scoped; absence is never a deletion

### Database
- [x] New Alembic migration; no existing migration modified
- [x] Migration chain from an empty PostgreSQL database validated
- [x] Downgrade/upgrade validated
- [x] Partial index for polling; entity and identity indexes
- [x] Deterministic ordering for pending queries
