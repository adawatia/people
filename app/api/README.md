# HRMS API Backend

The core application backend for the Human Resource Management System, built with **FastAPI**, **SQLAlchemy 2.0 (Async)**, **PostgreSQL (psycopg3)**, and **Pydantic v2**.

---

## Directory Organization

```
app/api/
├── core/               # Cross-cutting foundational modules
│   ├── audit.py        # Append-only security audit event helpers
│   ├── auth.py         # Dependencies, user manager, role resolution, JWT
│   ├── auth_throttle.py# Redis / in-memory brute force protection
│   ├── database.py     # Async engine, connection pooling, session maker
│   ├── mobile.py       # Indian E.164 mobile phone normalizer
│   ├── settings.py     # Pydantic BaseSettings environment configuration
│   └── totp.py         # RFC 6238 TOTP verification & recovery codes
├── db/                 # Database models and bootstrap lifecycle
│   ├── models.py       # SQLAlchemy declarative ORM models
│   └── seed.py         # Schema creation and initial bootstrap seeder
├── migrations/         # Alembic migration revisions
├── repositories/       # Persistence queries and atomic database primitives
├── routers/            # HTTP route controllers
│   ├── auth_login.py   # Workforce & technical sign-in, password recovery
│   ├── auth_mfa.py     # TOTP MFA challenges, enrollment, verification
│   ├── auth_sessions.py# Device sessions, refresh token rotation
│   ├── employees.py    # Workforce records and profile queries
│   ├── erp_*.py        # HMAC-authenticated machine integration routes
│   └── leaves.py       # Leave applications, approvals, balances
├── schemas/            # Pydantic v2 request/response contracts
├── services/           # Business domain logic and state machines
│   ├── auth_service.py # Session lifecycle, token minting, MFA machine
│   └── leave_service.py# Leave workflow transitions and outbox dispatch
└── tests/              # Pytest suite with 280+ test cases
```

---

## Environment Configuration

Copy `.env.example` to `.env` in `app/api/`:

```bash
cp .env.example .env
```

Key configuration variables:
- `ENVIRONMENT`: Set to `development` locally (accepts weak dev secrets); `production` enforces strict security validations.
- `DATABASE_URL`: Connection string (e.g. `postgresql+psycopg://user:password@localhost:5432/hrms_db`).
- `JWT_SECRET`: 32+ character random secret for signing access and MFA challenge tokens.
- `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD` / `SUPER_ADMIN_EMAIL`: Initial bootstrap credentials.
- `AUTH_THROTTLE_BACKEND`: `memory` for single-process local dev, `redis` for multi-worker production.
- `ERP_API_CLIENTS`: JSON map of HMAC keys and scopes for ERP machine clients.

---

## Database Management & Utilities

### 1. Automatic Development Setup
When running locally with `ENVIRONMENT=development`, the API automatically creates missing tables (`Base.metadata.create_all`) and seeds the initial Organization and Super Admin account upon server boot (`lifespan` handler in `main.py`).

### 2. Database Cleanup (`cleanup_db.py`)
Clears all application rows while preserving schema and migrations:

```bash
# Preview tables to be emptied (safe, read-only)
uv run python cleanup_db.py

# Execute cleanup and re-create initial bootstrap account
uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap

# Execute cleanup with custom Super Admin credentials
uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap \
  --admin-username "newadmin" \
  --admin-password "StrongPass123!" \
  --admin-email "admin@company.com"
```

### 3. Super Admin Password Recovery (`reset_super_admin_password.py`)
Host-side utility to reset the Super Admin password directly without touching application data:

```bash
uv run python reset_super_admin_password.py --identity superadmin
```

### 4. Alembic Migrations
```bash
# Generate a new migration revision
uv run alembic revision --autogenerate -m "describe_changes"

# Upgrade database to latest revision
uv run alembic upgrade head
```

---

## Authentication & Security Model

1. **Two Login Doors**:
   - `/auth/employee/login`: Accepts Indian mobile (`+919876543210`, `9876543210`, `09876543210`) or username. Rejects email addresses to prevent enumeration.
   - `/auth/super-admin/login`: Accepts username only. Requires MFA challenge completion when enrolled.
2. **Rotating Refresh Sessions**:
   - Access tokens expire in 15 minutes.
   - Refresh tokens rotate upon every exchange. Using a previously rotated token triggers immediate replay detection and revokes the entire session chain.
3. **Multi-Factor Authentication (TOTP)**:
   - Challenge tokens are short-lived (5 min) and restricted to MFA endpoints.
   - 10 single-use recovery codes are issued upon enrollment and hashed at rest.
4. **Adaptive Throttling (`AuthThrottle`)**:
   - Tracks failed attempts by account, IP, and (account, IP) pair.
   - Returns machine-readable HTTP 429 with `Retry-After` headers.

---

## ERP Machine Integration

The ERP system interacts via `/api/v1/integrations/erp/*` using HMAC-SHA256 request signatures:

- **Required Headers**: `X-ERP-Client-ID`, `X-ERP-Timestamp`, `X-ERP-Nonce`, `X-ERP-Signature`.
- **Durable Outbox**: Leave approvals, rejections, and cancellations stage events in `erp_outbox_events` in the same transaction as the state change.
- **Monotonic Cursor Feed**: `GET /integrations/erp/leaves/feed?cursor=...` enables reliable, gapless polling.
- **Idempotent Acknowledgement**: `POST /integrations/erp/leaves/ack` marks events processed.

---

## Testing

Backend tests require an isolated PostgreSQL database ending in `_test` to prevent test runs from touching development or staging databases:

```bash
# Run complete test suite
uv run pytest

# Run a specific test module
uv run pytest tests/test_auth_hardening_http.py

# Run with verbose output
uv run pytest -v -s
```
