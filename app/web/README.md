# People HRMS Web Client (Emploi)

The frontend client for People HRMS, built with **Nuxt 4**, **Vue 3**, **@nuxt/ui v4**, and **Tailwind CSS**. It incorporates a secure Backend-For-Frontend (BFF) proxy layer in Nitro and Progressive Web App (PWA) support.

---

## Directory Organization

```
app/web/
├── app/
│   ├── assets/css/     # Design system CSS tokens and base styles
│   ├── components/     # Reusable Vue components (MFA, passwords, tables, modals)
│   ├── composables/    # Reactive state composables (useAuth, useWorkspace, useHrmsApi)
│   ├── layouts/        # App layouts (default dashboard shell, auth layout)
│   ├── middleware/     # Global route guards (auth.global.ts, workspace.global.ts)
│   ├── pages/          # Application views & routing
│   │   ├── admin/      # Technical Super Admin sign-in (/admin/login)
│   │   ├── approvals/  # Leave and overtime approval queues
│   │   ├── attendance/ # Personal and team attendance logs
│   │   ├── employees/  # Directory and detailed employee profile views
│   │   ├── leaves/     # Leave requests and balance cards
│   │   ├── login.vue   # Workforce sign-in
│   │   ├── settings.vue# Security, password change, and MFA management
│   │   └── index.vue   # Role-adaptive operational dashboard
│   └── utils/          # Client utilities (safeInternalPath redirect protection)
├── public/             # Static logos, icons, PWA icons, manifest
├── server/             # Nitro BFF proxy layer
│   ├── api/
│   │   ├── hrms/       # Authenticated proxy to FastAPI (/api/hrms/*)
│   │   └── session/    # Cookie session management (login, me, mfa, logout)
│   └── utils/          # hrms.ts cookie utilities, single-flight refresh maps
├── shared/types/       # Shared TypeScript interfaces (auth, dashboard, employees)
└── tests/              # Node test runner suite for BFF, auth, and state guards
```

---

## Security Architecture (Nitro BFF)

The frontend uses a **Backend-For-Frontend (BFF)** pattern in Nitro server routes:

1. **HttpOnly Cookie Containment**:
   - The browser JavaScript never stores or accesses raw JWT access tokens or refresh tokens.
   - Sessions are maintained entirely through secure, `HttpOnly`, `SameSite=Lax`, and `__Host-` prefixed cookies (`people_session` and `people_refresh`).
2. **Single-Flight Session Refresh**:
   - When the 15-minute access token expires, Nitro's `/server/api/hrms/[...path].ts` catches the 401 and coordinates a single-flight refresh.
   - Concurrent requests share the same refresh call, preventing race conditions against the API's refresh token replay protection.
3. **Open-Redirect Protection**:
   - All `redirect` query parameters are sanitized through `safeInternalPath()` to reject protocol-relative URLs (`//evil.com`) and external destinations.

---

## Workspace & Role Model

The frontend automatically resolves the user's business role and access scope after login:

- **Personal Workspace**: Base self-service available to every employee (attendance history, leave applications, profile).
- **Team Workspace**: Activated for `DEPARTMENT_MANAGER` (team attendance, leave approvals).
- **HR Workspace**: Activated for `HR_ADMIN` (unit/organization employee directory, reports).
- **Executive Workspace**: Activated for `ORGANIZATION_OWNER` (organization-wide KPIs).
- **Technical Administration**: Isolated workspace for `SUPER_ADMIN` (system configuration, technical accounts, ERP synchronization health).

---

## Development Setup

### 1. Install Dependencies
```bash
pnpm install
```

### 2. Environment Configuration
Create or update `.env` in `app/web/` if needed:
```env
NUXT_HRMS_API_BASE=http://127.0.0.1:8000
```

### 3. Start Development Server
```bash
pnpm dev
```
Runs at `http://localhost:3000`.

---

## Quality & Testing Commands

```bash
# Typecheck TypeScript across pages, components, and server routes
pnpm typecheck

# Lint with ESLint
pnpm lint

# Run frontend unit tests (BFF proxy, cookie handling, and route guards)
node --test tests/*.test.mjs

# Build production bundle
pnpm build

# Preview production build locally
pnpm preview
```

---

## Progressive Web App (PWA)

The application includes an integrated service worker via `@vite-pwa/nuxt`:
- **Offline Shell**: Serves a responsive offline UI when connection drops.
- **Installable**: Supports desktop and mobile "Add to Home Screen" with standard manifest icons.
- **Cache Strategy**: Caches fonts and static icons with stale-while-revalidate policies.
