# People HRMS Documentation Hub

Welcome to the central technical documentation directory for **People HRMS (Emploi)**.

All documentation is structured into specialized categories below.

```
docs/
├── architecture/       # Canonical system reference, layering, state machines
├── deployment/         # AWS EC2 setup guide, runbooks, live testing environment
├── security/           # Personas, additive permissions, multi-tenant scopes
├── data/               # Seed lifecycle scripts, mock scenarios, credentials
└── integrations/       # External ERP HMAC-SHA256 protocols, outbox patterns
```

---

## 1. Directory Index

### 🚀 Deployment & Operations (`docs/deployment/`)
Comprehensive deployment guides, environment setups, and production runbooks:
- **[`deployment/ec2-setup-guide.md`](./deployment/ec2-setup-guide.md)**: Full AWS EC2 `t3.small` setup guide, inventory of tools, step-by-step commands, systemd units, Nginx configs, and troubleshooting FAQ.
- **[`deployment/testing-environment.md`](./deployment/testing-environment.md)**: Live test environment directory (`16-179-29-185.sslip.io`), interactive Swagger/ReDoc links, pre-seeded accounts, and maintenance runbook.

### 🏛️ System Architecture (`docs/architecture/`)
The canonical technical specification for the platform:
- **[`architecture/system-architecture-and-flows.md`](./architecture/system-architecture-and-flows.md)**: **The 10-Chapter Canonical Specification** covering ERP authoritative boundaries, authentication & MFA state machines, outbox event patterns, PostgreSQL database schemas, and the engineering decision register.

### 🔐 Security & Access Control (`docs/security/`)
Role-based access control, scope enforcement, and door separation:
- **[`security/user-roles-permissions-and-flows.md`](./security/user-roles-permissions-and-flows.md)**: The complete reference for the 5 user personas, additive permission codes, 4-tier access scopes (`SELF`, `DEPARTMENT`, `UNIT`, `ORGANIZATION`), and cross-role approval workflows.

### 📊 Data & Seed Personas (`docs/data/`)
Database lifecycle, test scenarios, and initial states:
- **[`data/seed-data-and-credentials.md`](./data/seed-data-and-credentials.md)**: Seed persona matrix, test credentials (`HrmsDev@2026!`), organization structures, shift rules, and database reset commands.

### 🔌 External Integrations (`docs/integrations/`)
Machine-to-machine contracts and synchronization feeds:
- **[`integrations/erp-integration.md`](./integrations/erp-integration.md)**: HMAC-SHA256 machine authentication contract, canonical signing algorithms, clock skew tolerance, replay defense, and bulk data sync envelopes.

---

## 2. Related Tools & Root Specifications

- **[ERP Test Simulator Harness](../tools/erp-simulator/README.md)**: Interactive browser-based testing console (`tools/erp-simulator`) to test live ERP sync routes.
- **[Editorial Violet Design System](../DESIGN.md)**: Color tokens, typographic hierarchy, responsive layout grids, and component conventions.
- **[Product Specification](../PRODUCT.md)**: Platform commitments, domain models, and feature roadmap.
- **[Repository Rules & Guidelines](../AGENTS.md)**: Module organization, coding style, and pull request conventions.

---

## 3. Contributing & Maintenance Rule

Per [`AGENTS.md`](../AGENTS.md):
> **Before changing architecture, auth, roles, or any workflow, read `docs/architecture/system-architecture-and-flows.md`.** It is the end-to-end reference. If your change adds or removes a router, permission code, page, or ERP endpoint, update the matching table in that document in the same pull request.
