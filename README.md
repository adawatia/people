# People HRMS (Emploi)

A modern, high-performance Human Resource Management System (HRMS) built for enterprises. Designed around a strict ERP ownership boundary, separation between workforce self-service and technical administration, cookie-backed BFF session security, and multi-tenant organizational scoping.

---

## Architecture Overview

```
                                      ┌──────────────────────────────────────────────┐
                                      │             External ERP System              │
                                      │  (Master Data: Org, Staff, Attendance, ...)  │
                                      └──────────────────────┬───────────────────────┘
                                                             │
                                                             │ HMAC Signed Machine APIs
                                                             │ (/api/v1/integrations/erp/*)
                                                             ▼
┌────────────────────────────┐    Cookie Sessions    ┌───────────────────────────────┐
│       Nuxt Frontend        │ ◄───────────────────► │        FastAPI Backend        │
│         (app/web)          │     (BFF Proxy)       │           (app/api)           │
│  - Nuxt 4, Vue 3, Nuxt UI  │                       │  - Python 3.12+, SQLAlchemy   │
│  - Tailwind CSS, PWA       │                       │  - Async PostgreSQL, Alembic  │
│  - Multi-role Workspaces   │                       │  - Argon2, TOTP MFA, Outbox   │
└────────────────────────────┘                       └───────────────┬───────────────┘
                                                                     │
                                                                     ▼
                                                     ┌───────────────────────────────┐
                                                     │      PostgreSQL Database      │
                                                     │ (App Data, Sessions, Outbox)  │
                                                     └───────────────────────────────┘
```

### Core Design Principles
1. **Authoritative ERP Boundary**: The external ERP is the sole source of truth for organization structure, job designations, employee master records, raw punch-in attendance, and shift assignments. Master records cannot be directly edited via workforce HRMS write endpoints.
2. **Door Separation**:
   - **Workforce Login** (`/login` → `/auth/employee/login`): Indian mobile number or username. Serves employees, department managers, unit HR, organization HR, and organization owners.
   - **Technical Admin Login** (`/admin/login` → `/auth/super-admin/login`): Dedicated break-glass system administration door with mandatory TOTP MFA support.
3. **Session & Token Security**:
   - Client holds only `HttpOnly`, `SameSite=Lax`, and `__Host-` prefixed cookies. Application JavaScript cannot inspect raw tokens.
   - Short-lived stateless access JWTs (15 min) paired with server-side database-tracked, rotating refresh tokens with automatic replay detection.
4. **Reliable Outbox & Audit**: Leave decisions, shift updates, and administrative changes emit immutable outbox events to guarantee zero data loss during ERP synchronization.

---

## Repository Structure

```
.
├── app/
│   ├── api/             # FastAPI backend workspace (Python, SQLAlchemy, Alembic)
│   │   ├── core/        # Auth, config, database engine, throttle, security
│   │   ├── db/          # Models, seed scripts, lifecycle bootstrap
│   │   ├── migrations/  # Alembic database migration revisions
│   │   ├── repositories/# Database persistence and query helpers
│   │   ├── routers/     # API route controllers
│   │   ├── schemas/     # Pydantic v2 data transfer schemas
│   │   ├── services/    # Business domain logic and workflow state machines
│   │   └── tests/       # Pytest test suite (280+ tests)
│   └── web/             # Nuxt frontend workspace (Vue 3, Nuxt UI v4, Nitro BFF)
│       ├── app/         # Pages, layouts, components, middleware, composables
│       ├── public/      # Static assets, branding logos, icons, PWA manifest
│       ├── server/      # Nitro BFF proxy endpoints and HttpOnly cookie management
│       ├── shared/      # Shared TypeScript types and contracts
│       └── tests/       # Frontend unit and integration tests
├── docs/                # Comprehensive architecture and integration references
│   ├── system-architecture-and-flows.md # Canonical 10-chapter reference specification
│   └── erp-integration.md               # Detailed ERP HMAC, outbox, and sync guide
├── tools/               # Developer tooling and test harnesses
│   └── erp-simulator/   # Interactive browser-based ERP test harness
├── AGENTS.md            # Repository guidelines and engineering rules
├── DESIGN.md            # Editorial violet design tokens and style specifications
└── PRODUCT.md           # Product specification and platform commitments
```

---

## Quickstart Guide

### Prerequisites
- **Python**: 3.12 or newer
- **uv**: Fast Python package installer (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js**: 20+ and **pnpm** (`npm install -g pnpm`)
- **PostgreSQL**: 15+ running locally (default dev port `5432`)

---

### 1. Backend Setup (`app/api`)

1. Change directory to the backend workspace:
   ```bash
   cd app/api
   ```

2. Configure environment settings:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Update `DATABASE_URL` with your local PostgreSQL credentials:
     ```env
     DATABASE_URL=postgresql+psycopg://postgres:yourpassword@localhost:5432/hrms_db
     ```
   - Set development bootstrap credentials:
     ```env
     ENVIRONMENT=development
     SUPER_ADMIN_USERNAME=superadmin
     SUPER_ADMIN_PASSWORD=YourStrongPassword123!
     SUPER_ADMIN_EMAIL=admin@example.com
     ```

3. Install dependencies and start the API server:
   ```bash
   uv sync
   uv run fastapi dev main.py
   ```
   *The server starts at `http://localhost:8000`. On first start in `development` mode, it automatically creates all PostgreSQL tables and seeds the initial Organization and Super Admin account.*

4. Verify API health & Interactive Docs:
   - OpenAPI Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Healthcheck: `GET http://localhost:8000/health`

---

### 2. Frontend Setup (`app/web`)

1. Change directory to the frontend workspace:
   ```bash
   cd app/web
   ```

2. Install dependencies:
   ```bash
   pnpm install
   ```

3. Start the Nuxt development server:
   ```bash
   pnpm dev
   ```
   *The web application will open at `http://localhost:3000`.*

---

## Common Development Commands

### Backend Commands (`app/api`)
```bash
# Start development server with hot-reload
uv run fastapi dev main.py

# Run the complete test suite (requires PostgreSQL test database)
uv run pytest

# Check code formatting and linting
uv run ruff check .

# Database cleanup utility (wipe data & reset auto-increment IDs)
uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap

# Host-side Super Admin password recovery
uv run python reset_super_admin_password.py --identity superadmin

# Apply database migrations
uv run alembic upgrade head
```

### Frontend Commands (`app/web`)
```bash
# Start Nuxt dev server
pnpm dev

# Typecheck TypeScript files
pnpm typecheck

# Lint with ESLint
pnpm lint

# Run unit tests
node --test tests/*.test.mjs

# Build for production
pnpm build
```

---

## Documentation & Tools Index

- **[System Architecture & Workflows](file:///docs/system-architecture-and-flows.md)**: The end-to-end reference covering layering rules, permissions, access scopes, state machines, and ERP boundaries.
- **[ERP Integration Specification](file:///docs/erp-integration.md)**: In-depth guide on HMAC SHA-256 signatures, replay prevention, outbox change feeds, and bulk upsert envelopes.
- **[ERP Test Simulator Harness](file:///tools/erp-simulator/README.md)**: Interactive testing tool to generate mock ERP events, sync attendance, and test outbox flows.
- **[Design & Tokens Reference](file:///DESIGN.md)**: Editorial violet design system tokens, color palettes, and responsive layouts.
- **[Repository Rules & Guidelines](file:///AGENTS.md)**: Module organization, coding style, and pull request rules.
