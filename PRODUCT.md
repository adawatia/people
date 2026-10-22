# Emploi

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two distinct user groups with dedicated authentication entrances:

- **Workforce Users (`/login`)**:
  - **Employees**: Log daily work, check in/out, monitor personal leave balances, submit leave and attendance regularization requests, and review assigned shift schedules.
  - **Department Managers**: Review and approve leave requests and attendance regularizations for direct reports, monitor team shift schedules, and manage exceptions.
  - **HR Administrators & Organization Owners**: Oversee company-wide attendance and leave policies, manage shift rotations and schedules, inspect employee operational records, handle exceptions, and review audit trails.

- **Technical Administrators (`/admin/login`)**:
  - **Super Admin**: Break-glass operational control, tenant/system settings, platform diagnostics, infrastructure audit logs. Strictly isolated from daily workforce HR workflows.

## Product Purpose

Emploi provides a calm, clutter-free workspace for daily workforce operations: attendance, leave management, scheduling, and shifts. It optimizes for quick, friction-free daily rituals for employees and clear, accountable approval loops for managers and HR, while treating ERP as the authoritative system of record for workforce master data.

## Positioning

"HR made calm." Unlike heavyweight legacy HR suites or sprawling enterprise ERP modules, Emploi acts as a high-clarity operational layer: employees and managers complete routine actions in seconds without navigating labyrinthine enterprise menus, backed by a resilient BFF architecture that synchronizes with ERP master records without compromising speed or data integrity.

## Operating Context

- **Daily Rituals**: Rapid check-in/out at shift boundaries, quick mobile/desktop leave balance checks, one-click leave and regularization approvals.
- **Deployment & Architecture**: Responsive web application designed for desktop, tablet, and mobile browsers. Nuxt 4 + Nuxt UI front-end connected via an HTTP-only cookie-based Backend-for-Frontend (BFF) proxy to a FastAPI backend.
- **Integrations**: Downstream ERP system owns organizational master data, employee profiles, and raw attendance event streams. Emploi reconciles operational approvals back to the ERP.

## Capabilities and Constraints

- Strict door separation: Workforce users cannot log in at `/admin/login`; Super Admin cannot log in at `/login`.
- Multi-factor authentication (MFA) via TOTP authenticator apps, authenticator-based self-service password recovery, and forced password changes.
- Server-side throttling and reactive rate-limit feedback to prevent brute-force attacks.
- Ephemeral, fully isolated test database lifecycle for automated tests (`people_test_<uuid>`).
- Read-only ERP master data boundaries: HRMS does not unilaterally create employee master profiles or alter ERP-owned organizational hierarchies.

## Brand Commitments

- Name: **Emploi** ("HR made calm").
- Identity & Palette: Calm forest green palette (`--color-brand-700: #1d613a`, `--ui-primary: #287448`).
- Tone & Voice: Calm, unambiguous, respectful of user focus. Clear field-level error messages and actionable alert banners rather than cryptic status codes.

## Evidence on Hand

- Verified codebase implementation in `app/web/` (Nuxt 4, Nuxt UI v4) and `app/api/` (FastAPI, SQLAlchemy, Alembic).
- Architecture and operational flows fully documented in `docs/system-architecture-and-flows.md`.
- Brand assets in `app/web/public/` (`favicon.ico`, `favicon.svg`, `apple-touch-icon.png`, `og-image.png`).
- No synthetic customer testimonials, fake benchmark statistics, or unconfirmed compliance certifications.

## Product Principles

1. **Calm and Fast**: Daily rituals (check-in, balance check, leave submission, approval) must complete in seconds with minimum cognitive load.
2. **Strict Separation of Doors**: Daily workforce operations and break-glass platform administration never share an entrance or surface.
3. **Truth at the Boundaries**: ERP is the system of record for workforce master data; HRMS never fabricates or quietly overrides master state.
4. **Transparent Feedback**: Never leave a user guessing on errors, rate limits, or session expiry—provide immediate, recoverable context.
5. **Data Integrity Over Speed**: Operations that impact employee records, leave balances, or audit trails must be transactional, idempotent, and auditable.
