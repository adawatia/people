# Nuxt.js Frontend Architecture & Integration Guide

This document outlines the architectural blueprint of our custom Nuxt 4 + Nuxt UI (v3/v4) frontend for the HRMS, operating on top of the FastAPI backend.

---

## 1. High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│ Nuxt 4 Presentation Layer (apps/web)                            │
│ ┌───────────────┐ ┌───────────────┐ ┌─────────────────────────┐ │
│ │ Pages & Views │ │ UI Components │ │ Layouts (Default/PWA)   │ │
│ └───────┬───────┘ └───────┬───────┘ └────────────┬────────────┘ │
│         └─────────────────┼──────────────────────┘              │
│                           ▼                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Composable Domain Services (useEmployees, useAttendance...)  │ │
│ └─────────────────────────┬───────────────────────────────────┘ │
│                           ▼                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Centralized API Client (useApi / fetchWithAuth in useAuth)  │ │
│ │ • Base URL & Auth Cookie Handling • Error Interception      │ │
│ └─────────────────────────┬───────────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────────┘
                            │ HTTP / REST (/api/v1/* via proxy)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI REST API Backend (apps/api on port 8000)                │
│ • OAuth2 Password Bearer / Cookie JWT • RBAC Permission Check   │
│ • Domain Routers (Org, Employees, Shifts, Attendance, Leaves...)│
│ • Service Layer & Validations                                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ SQLAlchemy Async Engine
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PostgreSQL Database (Local / Production)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure Conventions

In accordance with Nuxt 4 conventions configured in `apps/web/app/`:

```text
apps/web/app/
├── assets/                  # CSS stylesheets (Tailwind v4 base, fonts, custom variables)
├── components/              # Modular UI components
│   ├── attendance/          # Punch widgets, attendance tables, regularisation modals
│   ├── common/              # Empty states, status badges, confirmation modals, export buttons
│   ├── employees/           # Employee tables, form modals, profile tabs
│   ├── holidays/            # Holiday lists and calendar widgets
│   ├── layout/              # Navbars, sidebars, mobile navigation sheets
│   ├── leave/               # Leave balance cards, application forms, approval dialogs
│   ├── reports/             # Matrix grids, report filter toolbars
│   ├── shifts/              # Shift definition cards, assignment dialogues, roster grids
│   └── work-arrangements/   # WFH/OD forms and approval cards
├── composables/             # Reactive domain composables & API clients
│   ├── useApi.ts            # Central typed fetch client with error/toast interception
│   ├── useAttendance.ts     # Attendance punches, history, calendar, regularisations
│   ├── useAuth.ts           # Authentication session, tokens, user profile, RBAC checks
│   ├── useEmployees.ts      # Employee CRUD, search, hierarchy, activation
│   ├── useHolidays.ts       # Holiday list management and generation
│   ├── useLeave.ts          # Leave types, allocations, balances, applications, approvals
│   ├── useOrg.ts            # Organizations, units, departments, designations
│   ├── useReports.ts        # Attendance matrix, leave summary, overtime
│   ├── useShifts.ts         # Shift types, assignments, team schedules
│   └── useWorkArrangements.ts # Remote/OD/Field work applications & approvals
├── layouts/                 # Shell templates
│   ├── default.vue          # Full HRMS shell (sidebar, navbar, mobile bottom nav)
│   └── auth.vue             # Minimal card-centered shell for Login/Forgot Password
├── middleware/              # Nuxt route middleware
│   ├── auth.ts              # Protects internal pages; redirects unauthenticated users to /login
│   ├── guest.ts             # Redirects authenticated users from /login to /
│   └── permission.ts        # Dynamic route-level permission checks
├── pages/                   # File-based routing
│   ├── attendance/          # Attendance dashboard, checkins, corrections
│   ├── employees/           # Employee directory, creation, detail tabs
│   ├── holidays/            # Holiday lists
│   ├── index.vue            # Executive & self-service HRMS dashboard
│   ├── leaves/              # Leave balances, applications, allocations, approvals
│   ├── login.vue            # Login view
│   ├── org/                 # Units, departments, designations
│   ├── reports/             # Attendance matrix and leave summary reports
│   ├── roles.vue            # RBAC roles and permissions
│   ├── shifts/              # Shift definitions and assignments
│   ├── users.vue            # System user accounts
│   └── work-arrangements/   # WFH, Out-Duty, Field work requests
└── types/                   # TypeScript interfaces strictly aligned with FastAPI Pydantic schemas
    ├── api.ts               # PaginatedResponse<T>, ApiError
    ├── attendance.ts        # AttendancePunch, AttendanceRecord, AttendanceCorrection
    ├── auth.ts              # User, Token, Role, Permission
    ├── employee.ts          # Employee, EmployeeCreate, EmployeeUpdate, EmploymentType
    ├── holiday.ts           # HolidayList, Holiday
    ├── leave.ts             # LeaveType, LeavePeriod, LeaveAllocation, LeaveApplication, LeaveBalance
    ├── org.ts               # Organization, Unit, Department, Designation
    ├── report.ts            # AttendanceMatrixResponse, LeaveSummaryResponse
    ├── shift.ts             # ShiftType, ShiftAssignment, ScheduleItem
    └── work-arrangement.ts  # WorkArrangement, WorkArrangementType, Status
```

---

## 3. Centralized API Architecture (`useApi`)

All composables wrap a unified HTTP client that enforces:
1. **Base URL**: Defaults to runtime config `apiBase` (`/api/v1` in browser via proxy, direct FastAPI in SSR).
2. **Credentials**: `credentials: 'include'` to pass HTTP-only session cookies and authorization headers.
3. **Reactive State**: Returns typed `data`, `pending`, `error`, and `refresh` triggers.
4. **Toast Integration**: Automatically formats backend validation errors (e.g. FastAPI 422 Unprocessable Entity detail arrays) into digestible user toasts.
5. **Unauthorized Interception**: On HTTP 401, clears invalid tokens and invokes auth redirection to `/login`.

---

## 4. Nuxt UI (v3/v4) Theme & Component Standards

- **Color Tokens**: Adheres to the established *Soft UI Evolution* design language in `apps/web/design.md`.
  - Base surface: `bg-[#f8fafc]` (Light) / `bg-[#070b13]` (Dark).
  - Primary accent: High-contrast Sky/Indigo palette.
  - Border radius: Standardized `rounded-xl` for cards/panels, `rounded-lg` for inputs.
- **Micro-Interactions**: Hover lift transitions, loading spinners on active buttons (`:loading="isSubmitting"`), and tactile feedback on table rows.
- **Empty States**: Every list component includes dedicated illustrations and descriptive copy for zero-record states.
