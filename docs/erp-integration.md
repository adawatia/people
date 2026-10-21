# ERP ↔ People HRMS integration contract

This document is the operational contract between the external ERP and this
HRMS. It covers ownership, authentication, every direction of data flow, the
bulk response envelope, the leave change feed and acknowledgement protocol,
retry/recovery expectations for the ERP client, reconciliation, and the
maintenance a deployment needs.

The HRMS side is implemented here. **No ERP client code lives in this
repository**, so anything marked *ERP client requirement* is a contract the ERP
must satisfy; it has not been implemented or verified in this codebase.

---

## 1. Ownership

| Data | Owner | HRMS behaviour |
|---|---|---|
| Organization, units, departments, designations | ERP | Mirrored through `/integrations/erp/...` only. HRMS read APIs cannot overwrite ERP-owned fields. |
| Employee master data, employment status | ERP | Mirrored; password/username provisioning happens once, later upserts preserve the login. |
| Shifts and shift assignments | ERP | Mirrored; overlap rules and unit consistency are validated. |
| Holidays and weekly-offs | ERP | Mirrored into one organization-wide calendar. |
| Processed attendance records | ERP | Mirrored. HRMS-created rows (e.g. leave) may be adopted by ERP. |
| Leave types, periods, allocations, balances | ERP | Mirrored. HRMS does not invent balances. |
| Overtime **source** records | ERP | Mirrored as `PENDING` with zero approved minutes. |
| Leave applications and decisions | HRMS | Published to ERP through the outbox change feed. |
| Overtime approval decisions | HRMS | HRMS sets `approved_minutes`, `status`, `actioned_*`; ERP must never send those. |
| Attendance corrections | HRMS request, ERP confirms | HRMS raises a correction; reconciliation/confirmation remains the ERP's decision. |
| HRMS login sessions, MFA, passwords | HRMS | Never exposed to ERP except the explicit password-reset endpoint. |
| Work-from-home / on-duty requests | HRMS | Not part of the ERP contract today. |

A record is only ever repaired through a validated synchronisation operation —
never by an ad-hoc write.

---

## 2. Authentication

Every `/api/v1/integrations/erp/*` request is authenticated with HMAC-SHA256.

Headers:

| Header | Meaning |
|---|---|
| `X-ERP-Client-ID` | Client key in `ERP_API_CLIENTS` |
| `X-ERP-Timestamp` | Unix seconds |
| `X-ERP-Nonce` | Unique per request, 16–128 characters |
| `X-ERP-Signature` | Lowercase hex HMAC-SHA256 |
| `X-ERP-Batch-Id` | Optional bulk correlation id, `[A-Za-z0-9._:-]{8,128}` |

Canonical string (newline-joined, no trailing newline):

```
{METHOD}\n{path}?{raw_query}\n{timestamp}\n{nonce}\n{sha256_hex(raw_body)}
```

* `path` is the request path exactly as sent (`/api/v1/...`), the query string is
  appended verbatim when present, and the body hash is over the exact bytes sent.
* Signature comparison is constant-time; timestamp age must be within
  `ERP_SIGNATURE_MAX_AGE_SECONDS` (default 300, allowed 30–900).
* Nonces are consumed atomically with `SET NX EX` in Redis. In production a
  missing/unavailable Redis **fails closed** (503); the in-memory fallback is
  only for development and single-process use.
* A replayed nonce returns **409**; every other authentication failure returns
  **403** with a generic message.
* Client secrets must be at least 32 characters. They are never logged.

Configuration:

```json
ERP_API_CLIENTS={"erp-prod":{"secret":"<48+ random chars>","scopes":["employees:write","master-data:write","shifts:write","attendance:write","holidays:write","overtime:write","leaves:read","leaves:write","leave-master:write","sync:read"]}}
```

`ERP_API_KEY` (legacy `X-API-Key`) is honoured **only** when
`ENVIRONMENT=development`.

Scopes in use: `employees:write`, `master-data:write`, `shifts:write`,
`attendance:write`, `holidays:write`, `overtime:write`, `leaves:read`,
`leaves:write`, `leave-master:write`, `sync:read`. `*` grants all.

---

## 3. Bulk response envelope

Every bulk endpoint returns the same shape. It is a **breaking change** from the
previous `accepted[]`/`failed[]`/`duplicates[]` arrays; the ERP client must read
`items[]`.

```json
{
  "batch_id": "8f3c1d2e4a5b6c7d",
  "endpoint": "attendance.records.bulk",
  "received_count": 3,
  "accepted_count": 1,
  "duplicate_count": 1,
  "failed_count": 1,
  "retryable_failed_count": 0,
  "items": [
    {"key": "ERP-ATT-1001", "status": "accepted",  "id": 42, "code": null, "message": null, "retryable": false},
    {"key": "ERP-ATT-1002", "status": "duplicate", "id": 41, "code": null, "message": null, "retryable": false},
    {"key": "ERP-ATT-1003", "status": "failed",    "id": null, "code": "SHIFT_NOT_FOUND", "message": "Shift not found", "retryable": false}
  ]
}
```

* `key` is the ERP identity: `erp_id` for master data/employees,
  `erp_record_id` for attendance, `erp_event_id` for overtime, `erp_holiday_id`
  for holidays, `employee:<id>` for shift assignments, `employee:code:year` for
  balances.
* `batch_id` is the caller's `X-ERP-Batch-Id` when supplied, otherwise generated;
  it is echoed in the `X-ERP-Batch-Id` response header and stored in
  `erp_sync_batches` with the outcome counts.
* Items are reported `accepted` only after their persistence step succeeded.
* `retryable=true` means: resend this item later (transient persistence or
  server failure). `retryable=false` means the payload must change.
* Request-level errors are still normal FastAPI errors: `422` for a malformed
  envelope (empty page, wrong types, oversized batch), `403` for auth/scope.
  Item-level failures are `200`, unless **every** item failed transiently —
  then the page is `503` with `Retry-After: 30`.

### Stable item codes

| Code | Meaning | Retryable |
|---|---|---|
| `VALIDATION_ERROR` / `INVALID_REQUEST` | Payload rejected by business rules | no |
| `NOT_FOUND` / `EMPLOYEE_NOT_FOUND` / `SHIFT_NOT_FOUND` | Referenced row missing | no |
| `CONFLICT` | Unique constraint / duplicate identity | no |
| `ATTENDANCE_RECORD_CONFLICT` | Another ERP record already owns that employee/date | no |
| `ERP_RECORD_ID_CONFLICT` | An `erp_record_id` was reused for a different employee/date | no |
| `HOLIDAY_DATE_CONFLICT` | Another ERP holiday already owns that date | no |
| `OVERTIME_TARGET_NOT_FOUND` | Employee/attendance mismatch | no |
| `OVERTIME_STATUS_NOT_ERP_OWNED`, `OVERTIME_APPROVAL_NOT_ERP_OWNED` | ERP tried to set HRMS-owned approval fields | no |
| `TRANSIENT_PERSISTENCE_ERROR`, `TRANSIENT_TIMEOUT` | Database/lock/timeout fault | yes |
| `INTERNAL_ERROR` | Unexpected server fault (details are logged, not returned) | yes |

Messages never contain SQL, driver text, stack traces, connection details, or
unrelated personal data.

---

## 4. Endpoints by direction

### ERP → HRMS (ERP is authoritative)

| Method & path | Notes |
|---|---|
| `PUT /integrations/erp/organization/{erp_id}` | Single organization |
| `PUT /integrations/erp/units/by-erp-id/{erp_id}`, `/units/bulk` | Teams; bulk = envelope |
| `PUT /integrations/erp/departments/by-erp-id/{erp_id}`, `/departments/bulk` | `unit_id` is the local id returned by the unit upsert |
| `PUT /integrations/erp/designations/by-erp-id/{erp_id}`, `/designations/bulk` | |
| `PUT /integrations/erp/employees/by-erp-id/{erp_id}`, `/employees/bulk` | First call creates the login; later calls preserve the password |
| `PATCH /integrations/erp/employees/{id}/activate`, `/deactivate` | Lifecycle |
| `PUT /integrations/erp/shifts/by-erp-id/{erp_id}` | Shift definition |
| `POST /integrations/erp/shifts/assignments`, `/assignments/bulk`, `PATCH /assignments/{id}/cancel` | Bulk assignment returns the envelope keyed by employee id |
| `POST /integrations/erp/attendance/records/bulk` | Processed attendance (see §5) |
| `POST /integrations/erp/holidays/bulk` | Organization-wide calendar |
| `POST /integrations/erp/overtime/records/bulk` | Source records only |
| `POST /integrations/erp/leaves/periods`, `/types`, `PATCH /types/{id}` | Leave master data |
| `POST /integrations/erp/leaves/balances/bulk` | Balances per employee + leave code + year |

### HRMS → ERP (pull only; HRMS never calls the ERP)

| Method & path | Notes |
|---|---|
| `GET /integrations/erp/leaves/changes?cursor=&limit=` | Unacknowledged leave events, `sequence` order |
| `POST /integrations/erp/leaves/changes/ack` | Acknowledge processed event ids |

### Operations

| Method & path | Notes |
|---|---|
| `GET /integrations/erp/sync/status` | `scope: sync:read`. Backlog count/age, last delivery, per-entity 24h counts, nonce backend |
| `GET /integrations/erp/sync/pending-events?limit=` | Pending events with attempts and last-delivery |
| `POST /integrations/erp/reconciliation/attendance` | Dry-run diff of an ERP attendance snapshot |
| `POST /integrations/erp/reconciliation/leave-balances` | Dry-run diff of ERP balances |

---

## 5. Attendance identity rules

* Business key: **`erp_record_id`** (globally unique in `attendance_records`).
* Local uniqueness: `(employee_id, attendance_date)` (`uq_attendance_employee_date`).
* Same id, same values → `duplicate`, no write.
* Same id, different values → accepted **correction**; the previous values are
  recorded in `audit_logs` (`ERP_ATTENDANCE_CORRECTED`).
* Row exists for the employee/date with **no** ERP id (created by HRMS, e.g. an
  approved leave) → adopted, audited as `ERP_ATTENDANCE_ADOPTED`.
* Row exists for the employee/date under a **different** `erp_record_id` →
  `ATTENDANCE_RECORD_CONFLICT`; nothing is overwritten. Resolve in the ERP and
  resend with the correct identity.
* An `erp_record_id` may never move to another employee or date →
  `ERP_RECORD_ID_CONFLICT`.
* `shift_id` is only changed when the field is present in the payload.
* Batch atomicity: item-level savepoints, **one commit per 500 records**. A
  crash mid-chunk means that chunk was not committed and can be resent safely.
* Concurrency: one advisory-lock statement per chunk keyed by employee/date,
  with the unique constraints as the final backstop. Two identical concurrent
  chunks produce one `accepted` and one `duplicate`.

**Known limitation:** the ERP sends no revision/version metadata, so corrections
are last-write-wins by arrival order. If the ERP gains a monotonic revision, add
it to the payload and reject older revisions before applying.

---

## 6. Leave change feed and acknowledgement

### Event model

Every leave decision stages one immutable row in `erp_outbox_events` **in the
same transaction** as the state change:

| Column | Meaning |
|---|---|
| `sequence` | Monotonic BIGINT; the only cursor |
| `event_id` | Deterministic `LEAVE-{leave_id}-{EVENT}`; unique |
| `entity_type` / `entity_id` | `LEAVE_APPLICATION` / leave id |
| `event_type` | `APPROVED`, `REJECTED`, `CANCELLED`, `CANCELLATION_APPROVED` |
| `payload` | JSON snapshot taken at decision time |
| `created_at`, `last_delivered_at`, `delivery_attempts` | Delivery accounting |
| `acknowledged_at`, `acknowledged_by` | Acknowledgement |

A later transition on the same leave (approve → cancel) is a **separate**
event; the earlier one is never overwritten. A retried transition produces no
second row (`ON CONFLICT (event_id) DO NOTHING`).

### Pull

```
GET /api/v1/integrations/erp/leaves/changes?cursor=<next_cursor>&limit=100
```

```json
{
  "items": [{
    "event_id": "LEAVE-42-APPROVED",
    "sequence": 918,
    "event_type": "APPROVED",
    "leave_id": 42,
    "employee_code": "EMP001",
    "leave_code": "CL",
    "from_date": "2026-11-10",
    "to_date": "2026-11-11",
    "days": 2.0,
    "status": "APPROVED",
    "reason": "Family",
    "rejection_reason": null,
    "approved_at": "2026-11-01T10:15:00+05:30"
  }],
  "has_more": true,
  "next_cursor": "918",
  "pending_count": 37
}
```

Rules:

* Always pass the previous `next_cursor`; do not compute cursors yourself.
* Fetching **never** acknowledges and increments only `delivery_attempts`
  and `last_delivered_at`. Duplicate delivery is expected until ack.
* Ordering is `sequence ASC`; events created in the same millisecond are still
  totally ordered, so no pagination gap exists.
* `since=<ISO timestamp>` is accepted for one transition window only. It maps to
  a sequence boundary using `created_at < since`, so events created exactly at
  `since` are redelivered rather than skipped. Migrate to `cursor`.
* An empty page keeps `next_cursor` unchanged.

### Acknowledge

```
POST /api/v1/integrations/erp/leaves/changes/ack
{"event_ids": ["LEAVE-42-APPROVED"], "batch_id": "ack-2026-11-01-01"}
```

A bare JSON array (`["LEAVE-42-APPROVED"]`) is still accepted. Maximum 500 ids;
duplicates are collapsed.

```json
{
  "batch_id": "ack-2026-11-01-01",
  "acknowledged": ["LEAVE-42-APPROVED"],
  "already_acknowledged": [],
  "unknown": [],
  "pending_remaining": 36
}
```

* Acknowledge **only after** the ERP has durably applied the event.
* Re-acknowledging is safe (`already_acknowledged`).
* Ids that are not leave events on this feed are reported in `unknown` and are
  not touched.
* The legacy `leave_applications.erp_sync_status` mirror becomes `ACKNOWLEDGED`
  only when no unacknowledged event remains for that application, so an older
  ack can never hide a newer decision.

### Retention

* Unacknowledged events are retained indefinitely.
* Acknowledged events are retained for `ERP_OUTBOX_RETENTION_DAYS` (default 90)
  for audit, then pruned by an operator/maintenance job:

```sql
DELETE FROM erp_outbox_events
WHERE acknowledged_at IS NOT NULL
  AND acknowledged_at < now() - interval '90 days';
```

No scheduler is built into the API; run this from your maintenance window (or
`pg_cron`) with the value matching `ERP_OUTBOX_RETENTION_DAYS`.

---

## 7. ERP client requirements (retry and recovery)

Not implemented here — the ERP client must:

1. Poll `/leaves/changes` on a schedule, persist `next_cursor`, and ack only
   after processing. A restart resumes from the persisted cursor; losing the
   cursor only causes redelivery, never loss.
2. Retry `5xx`/network failures with exponential backoff and jitter
   (e.g. 1s, 2s, 4s … capped at 60s, ±20% jitter), a bounded attempt count or
   window, and the **same** `X-ERP-Batch-Id` so retries are correlatable.
3. Never retry a `4xx`/`retryable=false` item unchanged; fix the payload.
4. Treat `duplicate` as success.
5. Quarantine pages that exhaust retries, with the `batch_id`, endpoint and the
   failing item keys, for manual handling.
6. Resend a partially failed page; accepted items come back as `duplicate`.
7. Sign every retry with a **fresh** nonce and timestamp (replay protection is
   per-request, not per-payload).

Contract test suggestion: a fake ERP loop that (a) polls, (b) kills itself
before acking, (c) restarts from the old cursor and re-processes, (d) acks, and
(e) verifies the feed is empty.

---

## 8. Monitoring and reconciliation

`GET /sync/status` (`sync:read`) reports:

* `feed.pending_events`, `feed.oldest_pending_event_age_seconds`,
  `feed.last_delivery_at`, `feed.behind_schedule` (age > `ERP_SYNC_STALE_AFTER_SECONDS`);
* per entity: last batch time, last accepted time, last error code, and 24-hour
  received/accepted/duplicate/failed totals (from `erp_sync_batches`);
* `nonce.backend` (`redis`/`memory`) and `replay_protection_shared` — if this is
  ever `memory` in production, replay protection is per-worker and misconfigured.

Alert on: `behind_schedule=true`, any `failed_count` with
`retryable_failed_count > 0`, and `replay_protection_shared=false`.

`POST /reconciliation/attendance` body:

```json
{"from_date": "2026-11-01", "to_date": "2026-11-30", "apply": false, "records": [ ... ]}
```

Reports `missing_in_hrms`, `missing_in_erp` (ERP-sourced rows in the window not
present in the payload), `unlinked_hrms_record` (row held by a different/absent
ERP id) and `mismatched` (field-level `hrms` vs `erp`). Absence from the payload
is **never** treated as a deletion, and the window is capped at 366 days.
`apply=true` runs the normal audited sync path for the supplied records only.

`POST /reconciliation/leave-balances` compares `allocated`/`used`/`pending` and
supports the same `apply` switch; a balance the ERP omits is left untouched.

Typical recovery runbook:

1. `GET /sync/status` — is the backlog growing? Which entity last failed?
2. `GET /sync/pending-events` — confirm the backlog is delivery, not a stuck ack.
3. Re-poll from the persisted cursor; ack what the ERP has applied.
4. For a data mismatch, run the reconciliation dry-run, decide the correct
   source value, then re-send the ERP record (or `apply=true` after review).

---

## 9. Deployment and configuration

Backend environment (see `app/api/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `ERP_API_CLIENTS` | empty | JSON client registry (id → secret, scopes) |
| `ERP_SIGNATURE_MAX_AGE_SECONDS` | 300 | Timestamp window |
| `ERP_SYNC_STALE_AFTER_SECONDS` | 86400 | Backlog alarm threshold |
| `ERP_OUTBOX_RETENTION_DAYS` | 90 | Acknowledged-event retention |
| `REDIS_URL` | empty | Shared nonce store; **required** in production for replay protection |

Deployment steps:

1. `uv run alembic upgrade head` — creates `erp_outbox_events` and
   `erp_sync_batches` and backfills currently-pending leave events. Existing
   applied migrations are untouched.
2. Configure `ERP_API_CLIENTS`, `REDIS_URL`, and the new thresholds.
3. Deploy the API; verify `GET /integrations/erp/sync/status` reports
   `nonce.backend=redis` and `replay_protection_shared=true`.
4. Update the ERP client to the envelope/cursor contract (see §10) before it
   polls again.
5. Schedule the retention `DELETE` from §6.

---

## 10. Compatibility and migration for the ERP client

This release intentionally breaks the v1 bulk response and the leave feed cursor
in place (no `/v2` paths):

| Before | After | Action |
|---|---|---|
| `accepted[]` / `duplicates[]` / `failed[]` | `items[]` with `status` | Read `items[]`; filter by `status`; use `id` for local mapping |
| `failed[].error` (free text) | `items[].code` + `message` | Branch on `code`, show `message` to operators |
| `GET /leaves/changes?since=` | `?cursor=` + `next_cursor` | Persist and send `next_cursor`; `since` still works temporarily |
| Ack response `{acknowledged, unknown}` | `+ already_acknowledged, pending_remaining, batch_id` | Additive; existing parsing keeps working |
| `POST /leaves/changes/ack` bare array | `{event_ids, batch_id}` | Both accepted |
| `POST /shifts/assignments/bulk` returned a list | Envelope keyed by employee id | Read `items[]` |

Suggested rollout: deploy the API first (old clients keep working on the feed via
`since`, but bulk responses change immediately), then upgrade the ERP client in
the same maintenance window. If a zero-downtime cutover is required, keep the
ERP write paths paused during the deploy.
