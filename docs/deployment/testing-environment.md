# People HRMS — Testing Deployment & Documentation Reference

**Live Environment**: [https://16-179-29-185.sslip.io](https://16-179-29-185.sslip.io)  
**Host Architecture**: AWS EC2 `t3.small` (2 vCPU, 2 GiB RAM, 4 GiB Swap, Ubuntu 24.04 LTS)  
**Security**: Let's Encrypt Wildcard-compatible SSL (`sslip.io`), `__Host-` prefixed secure cookies, HSTS

---

## 1. Quick Access Links

| Interface | URL | Description |
| :--- | :--- | :--- |
| **Workforce Portal** | [https://16-179-29-185.sslip.io/login](https://16-179-29-185.sslip.io/login) | Employee, Manager, HRBP, and Org Owner self-service portal. |
| **Technical Admin Portal** | [https://16-179-29-185.sslip.io/admin/login](https://16-179-29-185.sslip.io/admin/login) | Break-glass Super Admin management door for platform configuration. |
| **FastAPI Swagger UI** | [https://16-179-29-185.sslip.io/docs](https://16-179-29-185.sslip.io/docs) | Interactive OpenAPI documentation with executable endpoints and schemas. |
| **FastAPI ReDoc** | [https://16-179-29-185.sslip.io/redoc](https://16-179-29-185.sslip.io/redoc) | Clean, searchable reference documentation for the backend API. |
| **OpenAPI Specification** | [https://16-179-29-185.sslip.io/openapi.json](https://16-179-29-185.sslip.io/openapi.json) | Raw OpenAPI 3.1 JSON schema of all endpoints. |
| **Backend Healthcheck** | [https://16-179-29-185.sslip.io/health](https://16-179-29-185.sslip.io/health) | Live service status, uptime, latency, and database pool telemetry. |

---

## 2. Deployment Stack: Tools, Services & Technologies Used

The following tools, infrastructure services, and runtimes power this deployment:

### Cloud & Infrastructure
- **AWS EC2 (`t3.small`)**: Virtual compute instance providing 2 vCPUs and 2 GiB RAM with burstable CPU capability.
- **AWS EBS (`gp3`)**: 30 GiB general-purpose solid-state storage volume hosting OS, packages, database, and repository.
- **AWS Security Groups**: Virtual stateful firewall controlling inbound access (SSH 22, HTTP 80, HTTPS 443).
- **Linux Swap (4 GiB)**: Kernel paging space on EBS storage, configured via `fallocate` and `/etc/fstab` to absorb memory spikes during Nuxt/Vite builds on 2 GiB RAM.

### Networking, Routing & SSL
- **Ubuntu 24.04 LTS (Noble Numbat)**: Base Linux server operating system.
- **`sslip.io`**: Public DNS wildcard service providing instant domain resolution (`16-179-29-185.sslip.io` -> `16.179.29.185`) without manual DNS record management.
- **Nginx (v1.28+)**: Reverse proxy web server listening on ports 80 and 443, handling SSL termination, proxying `/docs` and `/redoc` directly to FastAPI (:8000), and routing application traffic to Nuxt (:3000).
- **Certbot & Let's Encrypt**: Automated ACME certificate manager issuing and renewing trusted TLS/SSL certificates.

### Database Layer
- **PostgreSQL 16**: Relational database engine storing all users, roles, outbox events, attendance punches, leaves, and sessions.
- **`psycopg` (v3.3+)**: Modern, high-performance async PostgreSQL driver for Python.

### Backend Stack (`app/api`)
- **`uv` (Astral)**: Next-generation fast Python package manager and toolchain resolver.
- **Python 3.14**: Standalone Python runtime installed and managed automatically by `uv`.
- **FastAPI (v0.141+)**: Async ASGI web framework serving domain logic, authentication, and REST APIs.
- **Uvicorn (v0.52+)**: High-performance ASGI web server running FastAPI on `127.0.0.1:8000`.
- **SQLAlchemy (v2.0+)**: Async Python Object-Relational Mapper (ORM).
- **Alembic (v1.19+)**: Database schema migration framework applying version-controlled revisions.
- **Cryptography (AES-256-GCM)**: Authenticated symmetric encryption for TOTP/MFA secrets at rest.
- **Argon2**: Memory-hard password hashing algorithm for workforce credentials.

### Frontend Stack (`app/web`)
- **Node.js (v22 LTS)**: Server-side JavaScript runtime engine.
- **`pnpm` (v12+)**: Fast, disk space-efficient Node package manager.
- **Nuxt 4 (v4.6+)**: Vue 3 meta-framework handling Server-Side Rendering (SSR) and Backend-For-Frontend (BFF) proxying.
- **Nitro Engine**: Nuxt's backend engine terminating `__Host-` HttpOnly session cookies, performing CSRF origin checks, and proxying `/api/hrms/*` requests to FastAPI.
- **Nuxt UI (v4.11+) & Tailwind CSS (v4+)**: Accessible component system and design token implementation.
- **Vite & Rollup**: Next-generation frontend bundler and asset compiler.

### Process Management & Monitoring
- **`systemd`**: Linux system and service manager running `hrms-backend.service` and `hrms-frontend.service` as persistent daemons with automatic restart on failure and auto-start on boot.
- **`journalctl`**: Unified systemd log streaming utility for monitoring backend and frontend logs.

---

## 3. In-Repository Documentation Catalog

The repository includes detailed architectural and operational documentation:

| Document | File Link | Summary & Scope |
| :--- | :--- | :--- |
| **System Architecture & Workflows** | [system-architecture-and-flows.md](file:///d:/Projects/people/docs/system-architecture-and-flows.md) | Canonical 10-chapter reference: ERP boundary, auth & MFA state machines, outbox pattern, database schemas, and decision register. |
| **User Roles, Permissions & Flows** | [user-roles-permissions-and-flows.md](file:///d:/Projects/people/docs/user-roles-permissions-and-flows.md) | Persona definitions, 4-tier access scopes (`SELF`, `DEPARTMENT`, `UNIT`, `ORGANIZATION`), and cross-role approval flows. |
| **Seed Data & Credentials Reference** | [seed-data-and-credentials.md](file:///d:/Projects/people/docs/seed-data-and-credentials.md) | Breakdown of test personas, seed lifecycle scripts, and default dev credentials. |
| **ERP Integration Contract** | [erp-integration.md](file:///d:/Projects/people/docs/erp-integration.md) | Operational contract for machine-to-machine integrations: HMAC SHA-256 signatures, nonce replay protection, and outbox reconciliation. |
| **ERP Interactive Test Simulator** | [README.md](file:///d:/Projects/people/tools/erp-simulator/README.md) | Zero-dependency browser-based test harness (`tools/erp-simulator`) for exercising 21 live ERP synchronization endpoints. |
| **Editorial Violet Design System** | [DESIGN.md](file:///d:/Projects/people/DESIGN.md) | Color palettes, typographic hierarchies, responsive layout grids, and Nuxt UI v4 token specifications. |
| **Product Specification** | [PRODUCT.md](file:///d:/Projects/people/PRODUCT.md) | Platform commitments, domain models, compliance requirements, and feature roadmap. |

---

## 4. Test Personas & Login Credentials

All workforce users share the standard test password: **`HrmsDev@2026!`**  
Super Admin uses: **`SuperAdmin@123`** (or the password configured in `SUPER_ADMIN_PASSWORD`).

### Workforce Personas (`/login`)

| Persona | Username | Scope | Primary Workflows to Test |
| :--- | :--- | :--- | :--- |
| **Org Owner / CEO**<br>Rajesh Sharma | `rajesh.sharma` | `ORGANIZATION` | Executive workforce dashboard, high-level attendance metrics, company-wide leave view. |
| **HR Director**<br>Priya Nair | `priya.nair` | `ORGANIZATION` | Organization-wide leave allocation, gazetted holiday schedules, shift management. |
| **Unit HRBP (Hyderabad)**<br>Suresh Patel | `suresh.patel` | `UNIT` (`HYD-01`) | Unit-scoped attendance rosters, shift assignments, and HR interventions. |
| **Department Manager**<br>Vikram Malhotra | `vikram.malhotra` | `DEPARTMENT` (`ENG-HYD`) | **Pending Approvals Queue**: Pre-seeded leave, attendance correction, and overtime requests from Rahul Sharma. |
| **Senior Engineer**<br>Rahul Sharma | `rahul.sharma` | `SELF` | Employee self-service: Leave applications, attendance punch history, overtime claims. |
| **Software Engineer**<br>Neha Gupta | `neha.gupta` | `SELF` | Team-member self-service in `ENG-HYD` department. |
| **HR Operations Executive**<br>Kavya Nair | `kavya.nair` | `SELF` | Employee self-service in `HR-HYD` department. |

### Technical Admin Persona (`/admin/login`)

| Persona | Username | Scope | Primary Workflows to Test |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `superadmin` | `SYSTEM` | Break-glass administration, organization creation, system audit logs, direct ERP sync health. |

---

## 5. Operational Runbook & Server Commands

### Service Architecture

```
Internet (Port 80/443)
       │
       ▼
 [ Nginx Reverse Proxy ]
       │
       ├──► /api/v1/integrations, /docs, /redoc ──► FastAPI (127.0.0.1:8000)
       │                                                 │
       └──► /, /login, /api/session, /api/hrms ──► Nuxt BFF (127.0.0.1:3000)
                                                         │
                                                         ▼
                                                  PostgreSQL (127.0.0.1:5432)
```

### Continuous Deployment (CI/CD) Pipeline

An automated GitHub Actions workflow is configured in [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) that triggers on every push to the `development` branch.

It invokes the version-controlled deployment script [`tools/deploy.sh`](../../tools/deploy.sh) on the server.

#### One-Time Setup on EC2:
1. Ensure `tools/deploy.sh` is executable:
   ```bash
   chmod +x /var/www/people/tools/deploy.sh
   ```
2. Allow passwordless daemon restart for `ubuntu` user:
   ```bash
   sudo bash -c 'echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart hrms-backend, /bin/systemctl restart hrms-frontend" > /etc/sudoers.d/hrms-deploy'
   ```

#### One-Time Setup on GitHub:
In your GitHub repository settings, navigate to **Settings** → **Secrets and variables** → **Actions** and add:
- `EC2_HOST`: Your EC2 public IP (`16.179.29.185`) or domain (`16-179-29-185.sslip.io`).
- `EC2_SSH_KEY`: The contents of your private `.pem` SSH key file.
- `EC2_USERNAME` *(optional, defaults to `ubuntu`)*: The SSH user.

#### Manual One-Command Deployment (Without GitHub Actions)
You can also run the deployment script directly on the server at any time:
```bash
/var/www/people/tools/deploy.sh
```

### Essential System Management

```bash
# Check service statuses
sudo systemctl status hrms-backend --no-pager
sudo systemctl status hrms-frontend --no-pager

# Restart services
sudo systemctl restart hrms-backend
sudo systemctl restart hrms-frontend

# Stream live backend API logs
journalctl -u hrms-backend -f

# Stream live frontend SSR logs
journalctl -u hrms-frontend -f

# Check Nginx access and error logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Pulling Updates & Rebuilding After Branch Changes

```bash
# 1. Stop services
sudo systemctl stop hrms-frontend hrms-backend

# 2. Update code
cd /var/www/people
git fetch origin
git checkout <branch-name>
git pull

# 3. Update backend
cd /var/www/people/app/api
uv sync
uv run alembic upgrade head

# 4. Rebuild frontend (with memory cap for t3.small)
cd /var/www/people/app/web
pnpm install
NODE_OPTIONS="--max-old-space-size=1536" pnpm build

# 5. Restart services
sudo systemctl start hrms-backend hrms-frontend
```

### Reset & Reseed Database

To wipe existing test transactions and re-populate the standard Indian organization dataset:

```bash
cd /var/www/people/app/api
uv run python db/seed_indian_data.py --clean
```
