# HRMS Nuxt Web Application Plan

**Status:** Proposed implementation plan  
**Frontend:** Nuxt 4, Vue 3, TypeScript, Nuxt UI 4  
**Backend:** Existing FastAPI application in `apps/api`  
**Target:** Production-quality HRMS for desktop and mobile browsers  
**Visual direction:** Professional, calm, pastel-soft business interface using Lucide icons

---

## 1. Executive Summary

The existing Expo application in `apps/app` will be replaced with a purpose-built Nuxt web application. This is a clean web rebuild rather than a component-by-component Expo migration because the current frontend is primarily Expo starter code, while the FastAPI backend already contains the core HRMS workflows.

The new application will:

- support employee, manager, HR administrator, and system administrator workflows;
- derive navigation and actions from backend permissions and role scopes;
- provide equally intentional desktop and mobile experiences;
- use Nuxt UI for accessible, consistent components;
- use Lucide icons throughout the product;
- use a professional pastel-soft visual system with restrained color, clear hierarchy, and high readability;
- keep authentication tokens out of browser JavaScript by using Nuxt server routes as a backend-for-frontend;
- generate TypeScript API contracts from the FastAPI OpenAPI schema;
- include responsive, accessibility, security, and workflow testing before release.

The recommended final frontend location is `apps/web`, matching the repository's root README. The current `apps/app` directory should be renamed or replaced during the migration.

---

## 2. Product Principles

### 2.1 Business-first

The interface should help people complete HR tasks quickly. Decorative elements must not compete with attendance status, leave balances, approvals, employee records, or reports.

### 2.2 Permission-driven

The backend uses dynamic permissions with organization, unit, and department scopes. The frontend must not reduce this to a fixed `admin` versus `employee` model.

Navigation visibility, page access, record actions, dashboard widgets, and selectable organization scopes must be derived from the authenticated user's effective permissions and assignments.

### 2.3 Mobile and desktop designed together

Every feature must define both layouts before implementation begins. Mobile must not be a compressed desktop screen, and desktop must not look like an enlarged mobile application.

### 2.4 Calm and professional

Pastel color is used to organize information and communicate status. Large saturated surfaces, excessive gradients, glass effects, neon accents, and playful illustrations should be avoided.

### 2.5 Predictable workflows

All mutations should provide:

- a clear primary action;
- confirmation when consequences are significant;
- visible pending state;
- field-level validation;
- a success acknowledgement;
- a recoverable error message;
- a reliable return path.

---

## 3. Current Repository Assessment

### 3.1 Backend modules already available

The FastAPI backend currently covers:

- authentication by email, username, or mobile number;
- JWT sessions;
- invitation onboarding;
- password reset and email verification;
- users, roles, permissions, and scoped role assignments;
- organizations, units, and departments;
- employee profiles, reporting hierarchy, lifecycle, and work history;
- designations;
- shifts and shift assignments;
- holiday lists and weekly offs;
- attendance punches, processing, calendar, and summaries;
- attendance correction requests;
- leave periods, policies, allocation, balance, and applications;
- work-from-home, on-duty, and field-work requests;
- overtime review and summaries;
- notifications;
- permission-sensitive dashboard metrics;
- attendance and leave reports.

### 3.2 Existing frontend state

The existing `apps/app` frontend uses Expo, React Native, Expo Router, NativeWind, Metro, and device-specific storage. Most screens and assets are starter content, so little business UI should be ported.

Reusable items are limited to:

- approved brand SVG files;
- API error-formatting concepts;
- basic authentication-flow requirements;
- any final copy approved by the product owner.

### 3.3 Readiness issues

Before frontend integration begins:

- apply the Alembic migration to an isolated development/test database;
- make the backend test suite reproducible;
- regenerate the OpenAPI document from the running application;
- verify record-level authorization, not only page-level permissions;
- update stale backend documentation;
- document status values and validation rules used by every workflow.

The initial backend test run returned 16 passes and 39 failures because the configured PostgreSQL database did not contain required tables such as `organizations` and `notifications`. Database setup is therefore a release gate, not an optional cleanup task.

---

## 4. Recommended Technical Architecture

### 4.1 Core stack

| Area | Choice |
|---|---|
| Framework | Nuxt 4 |
| UI runtime | Vue 3 with TypeScript |
| Component system | Nuxt UI 4 |
| Styling | Tailwind CSS 4 through Nuxt UI |
| Icons | Lucide through Nuxt Icon/Iconify |
| Forms | Nuxt UI `UForm` with Zod schemas |
| API access | Typed `$fetch` wrapper and SSR-safe composables |
| API types | Generated from FastAPI `/openapi.json` |
| State | Nuxt state for session and lightweight domain stores only where needed |
| Unit tests | Vitest |
| Component tests | Vue Test Utils and Nuxt Test Utils |
| End-to-end tests | Playwright |
| Package manager | pnpm |

### 4.2 Application structure

```text
apps/web/
├── app/
│   ├── assets/css/
│   │   └── main.css
│   ├── components/
│   │   ├── app/
│   │   ├── attendance/
│   │   ├── employees/
│   │   ├── forms/
│   │   ├── leave/
│   │   ├── navigation/
│   │   └── shared/
│   ├── composables/
│   │   ├── useHrmsApi.ts
│   │   ├── usePermissions.ts
│   │   ├── useResponsiveDataView.ts
│   │   └── useSession.ts
│   ├── layouts/
│   │   ├── auth.vue
│   │   └── default.vue
│   ├── middleware/
│   │   ├── auth.ts
│   │   ├── guest.ts
│   │   └── permission.ts
│   ├── pages/
│   ├── stores/
│   ├── types/
│   │   ├── api.generated.ts
│   │   └── navigation.ts
│   ├── utils/
│   ├── app.config.ts
│   └── app.vue
├── server/
│   ├── api/
│   │   ├── hrms/[...path].ts
│   │   └── session/
│   └── utils/
├── tests/
├── nuxt.config.ts
├── package.json
└── pnpm-lock.yaml
```

### 4.3 Authentication model

The JWT should not be stored in `localStorage` or exposed to application JavaScript.

```text
Browser
   │ Secure HttpOnly cookie
   ▼
Nuxt/Nitro session and proxy routes
   │ Authorization: Bearer <token>
   ▼
FastAPI /api/v1
```

Login flow:

1. The browser posts credentials to the Nuxt session endpoint.
2. Nitro sends the required form-encoded request to FastAPI.
3. Nitro stores the returned access token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie.
4. HRMS browser requests use same-origin Nuxt endpoints.
5. Nitro attaches the bearer token when calling FastAPI.
6. Nuxt route middleware obtains the current user from `/users/me`.
7. A 401 clears the session and redirects to the login page.

### 4.4 API contract strategy

```text
FastAPI openapi.json
        │
        ▼
openapi-typescript
        │
        ▼
api.generated.ts
        │
        ▼
typed useHrmsApi composable
```

Generated files should not be manually edited. CI should regenerate the contract and fail when committed types are stale.

---

## 5. Visual Design Direction

### 5.1 Brand character

The product should feel:

- trustworthy;
- organized;
- calm;
- efficient;
- modern without appearing experimental;
- friendly without appearing informal.

### 5.2 Pastel-soft color system

Pastels should appear mainly in status backgrounds, selected navigation, charts, filters, and summary cards. Text and important controls must retain strong contrast.

#### Core neutral palette

| Token | Suggested value | Use |
|---|---:|---|
| `canvas` | `#F7F8FA` | Main application background |
| `surface` | `#FFFFFF` | Cards, panels, dialogs |
| `surface-soft` | `#F1F4F7` | Secondary panels and grouped controls |
| `border` | `#E3E7EC` | Standard borders |
| `border-strong` | `#CDD4DC` | Focused divisions and table headers |
| `text` | `#1D2733` | Primary text |
| `text-muted` | `#667281` | Secondary text |
| `text-dimmed` | `#8C97A5` | Metadata and placeholders |

#### Semantic pastel palette

| Meaning | Background | Foreground | Typical use |
|---|---:|---:|---|
| Primary | `#E5EEFF` | `#2856A3` | Active navigation, selected controls |
| Success | `#E5F5EB` | `#23663B` | Present, approved, active |
| Warning | `#FFF3D6` | `#875E12` | Pending, late, attention needed |
| Error | `#FCE7E7` | `#A03838` | Rejected, absent, destructive action |
| Info | `#E3F2F6` | `#256579` | Informational notices, remote work |
| Lavender | `#EEE9FA` | `#624B91` | Leave, policies, secondary categories |
| Peach | `#FBEBDD` | `#8B5430` | Overtime and special schedules |

Colors must never be the only indicator of meaning. Pair status color with text and, where useful, an icon.

### 5.3 Typography

Use one professional sans-serif family, preferably Inter or Public Sans.

- Page title: 24–30 px, semibold
- Section title: 18–20 px, semibold
- Card title: 14–16 px, semibold
- Body: 14–16 px, regular
- Supporting text: 12–14 px
- Tabular numbers: enable tabular numeral styling

Avoid all-uppercase labels except for short employee or status codes.

### 5.4 Shape and depth

- Card radius: 12–16 px
- Input and button radius: 8–10 px
- Pills and status badges: full radius
- Borders: subtle neutral gray
- Shadows: soft and shallow; borders should carry most structural separation
- Avoid nested cards unless the grouping adds real meaning
- Avoid excessive blur and glassmorphism

### 5.5 Density

Desktop data pages should support comfortable and compact table density. Mobile stays comfortable, with at least 44 px interactive targets.

---

## 6. Lucide Icon System

Lucide is the only general interface icon family. Do not mix Lucide with emoji, platform symbols, or unrelated icon packs.

### 6.1 Icon rules

- Default icon size: 18–20 px
- Compact controls: 16 px
- Empty states: 32–40 px
- Stroke width: visually consistent across the application
- Every icon-only control requires an accessible label and tooltip on desktop
- Use icons to aid recognition, not replace important text
- Do not use more than one icon in a standard button
- Destructive actions use both a clear label and the appropriate error color

### 6.2 Navigation icon map

| Area | Lucide icon |
|---|---|
| Dashboard | `LayoutDashboard` |
| My profile | `CircleUserRound` |
| Employees | `UsersRound` |
| Users and access | `UserCog` |
| Attendance | `CalendarCheck2` |
| Punch in/out | `ScanLine` |
| Leave | `CalendarDays` |
| Approvals | `ClipboardCheck` |
| Shifts | `Clock3` |
| Holiday calendar | `CalendarHeart` |
| Work arrangements | `BriefcaseBusiness` |
| Overtime | `TimerReset` |
| Reports | `ChartNoAxesCombined` |
| Organization | `Building2` |
| Departments | `Network` |
| Designations | `BadgeCheck` |
| Roles and permissions | `ShieldCheck` |
| Notifications | `Bell` |
| Settings | `Settings2` |
| Help | `CircleHelp` |

### 6.3 Action icon map

| Action | Lucide icon |
|---|---|
| Add | `Plus` |
| Edit | `Pencil` |
| Save | `Save` |
| Search | `Search` |
| Filter | `ListFilter` |
| Sort | `ArrowUpDown` |
| Export | `Download` |
| Upload/import | `Upload` |
| Approve | `Check` |
| Reject | `X` |
| Cancel request | `Ban` |
| More actions | `Ellipsis` |
| Open detail | `ChevronRight` |
| Previous | `ChevronLeft` |
| Date | `Calendar` |
| Time | `Clock` |
| Location | `MapPin` |
| Warning | `TriangleAlert` |
| Information | `Info` |
| Success | `CircleCheck` |
| Error | `CircleX` |
| Sign out | `LogOut` |

---

## 7. Responsive Application Shell

### 7.1 Desktop shell

- Persistent left sidebar
- Collapsible navigation labels
- Brand mark and organization context at the top
- Permission-filtered navigation groups
- Top header containing breadcrumb, scope selector, notifications, and account menu
- Main content width appropriate to the page type
- Optional right-side detail panel for high-volume approval workflows

Suggested navigation groups:

1. Overview
2. My workspace
3. Team management
4. Workforce
5. Reports
6. Administration

### 7.2 Mobile shell

- Compact top app bar
- Bottom navigation with a maximum of four primary destinations plus `More`
- `More` opens a full-height navigation drawer
- Contextual primary actions use a sticky footer or clearly placed floating action
- Filters open in a bottom sheet
- Detail content is a dedicated page rather than a narrow split panel
- Safe-area padding is required around bottom navigation and sticky actions

Recommended employee bottom navigation:

1. Home — `House`
2. Attendance — `CalendarCheck2`
3. Leave — `CalendarDays`
4. Notifications — `Bell`
5. More — `Menu`

Manager and HR destinations remain available from `More`; permission-sensitive quick actions may also appear on the dashboard.

### 7.3 Responsive behavior matrix

| Pattern | Desktop | Mobile |
|---|---|---|
| Record listing | Data table | Summary cards |
| Filtering | Inline toolbar/side panel | Bottom sheet |
| Detail | Page or split view | Dedicated stacked page |
| Form | One or two columns | Single column |
| Approvals | Queue plus detail | Card list plus detail page |
| Calendar | Month/roster grid | Week/day list |
| Page actions | Header buttons | Sticky action bar |
| Tabs | Standard horizontal tabs | Scrollable tabs or segmented control |
| Metrics | Four-to-six card grid | Two-column or horizontal scroll group |

---

## 8. Information Architecture and Pages

### 8.1 Public authentication

| Route | Purpose |
|---|---|
| `/login` | Email, username, or mobile login |
| `/forgot-password` | Request password reset |
| `/reset-password` | Set a new password from token |
| `/invitation` | Validate invitation and create password |
| `/verify-email` | Complete email verification |

The authentication layout should use a quiet branded background with one focused card. It must avoid marketing-heavy content that distracts from sign-in.

### 8.2 Employee self-service

| Route | Purpose |
|---|---|
| `/dashboard` | Personal status, metrics, balances, and quick actions |
| `/me/profile` | Personal and employment information |
| `/me/attendance` | Attendance calendar and monthly summary |
| `/me/attendance/punch` | Punch in/out with optional location confirmation |
| `/me/attendance/corrections` | Correction history and new correction request |
| `/me/leave` | Leave balances and application history |
| `/me/leave/new` | New leave application |
| `/me/work-arrangements` | WFH, on-duty, and field-work requests |
| `/me/overtime` | Personal overtime summary |
| `/notifications` | Notification center |

### 8.3 Manager workspace

| Route | Purpose |
|---|---|
| `/approvals` | Unified pending approval overview |
| `/approvals/leaves` | Leave approval queue |
| `/approvals/attendance` | Attendance correction queue |
| `/approvals/overtime` | Overtime approval queue |
| `/approvals/work-arrangements` | Work-arrangement queue |
| `/team/attendance` | Team attendance view |
| `/team/schedule` | Team shift schedule |

### 8.4 HR and administration

| Route | Purpose |
|---|---|
| `/employees` | Employee directory |
| `/employees/new` | Employee onboarding |
| `/employees/[id]` | Employee profile and work history |
| `/users` | User accounts and invitation status |
| `/users/[id]` | Account and scoped role assignments |
| `/workforce/shifts` | Shift definitions |
| `/workforce/assignments` | Shift assignment and roster |
| `/workforce/holidays` | Holiday lists |
| `/leave/policies` | Leave periods and types |
| `/leave/allocations` | Employee leave allocations |
| `/reports/attendance` | Monthly attendance matrix |
| `/reports/leave` | Leave summary report |
| `/settings/organization` | Organization profile |
| `/settings/units` | Unit management |
| `/settings/departments` | Department management |
| `/settings/designations` | Designation management |
| `/settings/roles` | Role and permission configuration |

Routes should be hidden when the user lacks relevant permissions and independently guarded by route middleware.

---

## 9. Shared Component Plan

Build reusable product components on top of Nuxt UI rather than duplicating page-specific markup.

### 9.1 Layout components

- `AppSidebar`
- `AppMobileNav`
- `AppHeader`
- `AppBreadcrumbs`
- `PageHeader`
- `PageSection`
- `ScopeSelector`
- `PermissionGate`

### 9.2 Data-display components

- `ResponsiveDataView`
- `StatusBadge`
- `EmployeeIdentity`
- `MetricCard`
- `SummaryCard`
- `DefinitionList`
- `ActivityTimeline`
- `AttendanceCalendar`
- `ApprovalCard`
- `EmptyState`
- `ErrorState`
- `LoadingSkeleton`

### 9.3 Form components

- `FormSection`
- `DateRangeField`
- `EmployeeSelect`
- `OrganizationScopeFields`
- `ReasonField`
- `PasswordStrengthMeter`
- `FormActionBar`
- `ConfirmActionModal`

### 9.4 Responsive data-view contract

Every list page should define:

- desktop table columns;
- mobile summary fields;
- row/card primary action;
- filter schema;
- empty-state copy;
- loading skeleton;
- permission-dependent actions.

This keeps mobile behavior intentional and consistent across employees, leave, attendance, users, shifts, and approvals.

---

## 10. Workflow UX Specifications

### 10.1 Dashboard

Employee dashboard:

- today's attendance status;
- current shift;
- punch in/out information;
- leave balance summary;
- monthly attendance summary;
- quick actions;
- recent notifications.

Manager/HR dashboard additions:

- scoped headcount;
- present, absent, on-leave, and weekly-off counts;
- attendance rate;
- missed punches;
- pending approval counts;
- overtime summary;
- recent approval requests.

Widgets must respect the backend dashboard widget response and effective permissions.

### 10.2 Attendance punch

1. Show current employee and resolved shift.
2. Determine expected punch type where possible.
3. Ask for browser location only when required.
4. Explain why location is requested.
5. Show captured location state before confirmation.
6. Submit once and prevent accidental duplicate taps.
7. Display the recorded server timestamp and source.

Location denial must produce a useful recovery path rather than a generic failure.

### 10.3 Leave application

1. Select leave type.
2. Show available balance and policy notes.
3. Choose date range and optional half day.
4. Calculate an estimated day count.
5. Enter the reason.
6. Review before submission.
7. Display pending status and timeline.

Backend calculation remains authoritative; frontend day counts are previews only.

### 10.4 Approval flow

Each approval detail must show:

- employee identity;
- department and employee code;
- request type and date range;
- relevant balance or attendance context;
- request reason;
- prior action history where available;
- clear approve and reject actions.

Rejecting requires a reason. Approving high-impact changes should show a concise confirmation.

### 10.5 Employee profile

Group profile fields into:

1. Basic information
2. Employment information
3. Organization and reporting line
4. Contact and emergency contact
5. Address
6. Identity and statutory information
7. Bank information
8. Separation details
9. Work-history timeline

Sensitive sections require explicit permissions and should not be sent to unauthorized clients.

---

## 11. Permission and Scope Model

The frontend should load `/users/me` once per authenticated session and retain:

- user identity;
- linked employee ID and code;
- effective permission codes;
- scoped role assignments;
- active/inactive state;
- superuser state.

Helpers should expose operations such as:

```ts
can('employee.create')
canAny(['leave.approve', 'leave.reject'])
hasOrganizationScope()
unitScopeIds()
departmentScopeIds()
```

Permission gates improve the experience but do not replace backend authorization.

Required backend hardening includes:

- employee ownership checks for self-service requests;
- record filtering by organization/unit/department scope;
- field-level protection for salary, Aadhaar, PAN, and bank details;
- prevention of punches or applications submitted for unauthorized employees;
- audit trails for administrative changes.

---

## 12. Expo Removal Plan

Remove Expo and React Native implementation files only after the replacement branch is protected by source control.

### Remove

- Expo package dependencies
- React Native dependencies
- Expo Router entry points and pages
- Metro configuration
- Expo Babel configuration
- `app.json`
- Expo environment declarations
- NativeWind configuration and declarations
- SecureStore and AsyncStorage integration
- React Native query provider and Zustand store
- Expo splash and tutorial assets
- Android and iOS icon assets
- Expo-specific scripts
- Expo-specific repository instructions

### Preserve or relocate

- approved company logo SVGs;
- approved favicon source;
- business-relevant copy;
- API error normalization behavior;
- documentation that remains accurate.

### Validate removal

Run repository searches for:

```text
expo
react-native
nativewind
metro
EXPO_PUBLIC_
SecureStore
AsyncStorage
```

No runtime or build references should remain in the Nuxt project.

---

## 13. Implementation Phases

### Phase 0 — Backend readiness

Deliverables:

- isolated development and test database setup;
- successful migration and seed process;
- reproducible backend test run;
- generated OpenAPI contract;
- endpoint/permission/scope matrix;
- list of backend authorization changes.

Exit criteria:

- tests run against a known schema;
- normal employees cannot access another employee's sensitive records;
- API contract generation is deterministic.

### Phase 1 — Nuxt foundation

Deliverables:

- Expo removal;
- Nuxt scaffold;
- Nuxt UI theme;
- Lucide configuration;
- lint, type-check, test, and build scripts;
- runtime environment configuration.

Exit criteria:

- no Expo references remain;
- Nuxt development server runs;
- production build succeeds;
- desktop and mobile shell smoke tests pass.

### Phase 2 — Authentication and application shell

Deliverables:

- Nitro session proxy;
- login/logout;
- forgot/reset password;
- invitation onboarding;
- current-user session;
- permission middleware;
- desktop sidebar;
- mobile navigation;
- notification indicator.

Exit criteria:

- authenticated refresh works;
- 401 and 403 behaviors are correct;
- JWT is not accessible to browser JavaScript;
- navigation matches effective permissions.

### Phase 3 — Dashboard and attendance vertical slice

Deliverables:

- responsive dashboard;
- metrics and visible widgets;
- attendance calendar and summary;
- punch workflow;
- correction requests;
- notification center.

Exit criteria:

- complete employee attendance workflow works on desktop and mobile;
- loading, empty, error, and success states are covered;
- geolocation failure is recoverable.

### Phase 4 — Employee self-service

Deliverables:

- personal profile;
- leave balances and applications;
- work arrangements;
- employee schedule;
- overtime summary.

Exit criteria:

- every workflow has tested status transitions;
- ownership constraints are enforced by the backend;
- mobile sticky actions do not obscure content.

### Phase 5 — Manager approval workspace

Deliverables:

- unified approval overview;
- leave approvals;
- attendance correction approvals;
- overtime approvals;
- work-arrangement approvals;
- manager team context.

Exit criteria:

- queues are scope-filtered;
- self-approval protection is verified;
- rejection reasons are required and displayed.

### Phase 6 — HR administration

Deliverables:

- employee directory and lifecycle;
- user invitations;
- roles and assignments;
- shifts and rosters;
- holidays;
- leave policies and allocation;
- organization master data.

Exit criteria:

- large lists use server pagination;
- sensitive fields require explicit permission;
- scoped role assignment is validated.

### Phase 7 — Reports and release hardening

Deliverables:

- attendance report;
- leave report;
- CSV export;
- print layouts;
- accessibility audit;
- performance audit;
- security review;
- end-to-end role matrix;
- deployment and rollback documentation.

Exit criteria:

- production build and tests pass;
- keyboard and screen-reader flows are validated;
- no critical security or accessibility findings remain;
- staging approval is complete.

---

## 14. Testing Strategy

### 14.1 Unit tests

- permission helpers;
- scope helpers;
- date and time formatting;
- status mapping;
- API error normalization;
- form schema validation;
- attendance and leave display calculations.

### 14.2 Component tests

- responsive data view;
- mobile filter sheet;
- status badge semantics;
- permission gate;
- form sections;
- confirmation dialogs;
- approval actions;
- password strength feedback.

### 14.3 End-to-end workflows

- login and logout;
- invitation onboarding;
- employee attendance punch;
- attendance correction request and approval;
- leave application, approval, rejection, and cancellation;
- work-arrangement lifecycle;
- overtime approval;
- employee creation and deactivation;
- user invitation and scoped role assignment;
- shift assignment;
- reports and filters.

### 14.4 Responsive coverage

Minimum automated viewports:

- 360 × 800 mobile
- 390 × 844 mobile
- 768 × 1024 tablet
- 1280 × 800 desktop
- 1440 × 900 desktop

### 14.5 Accessibility coverage

- full keyboard navigation;
- visible focus states;
- meaningful labels for icon-only controls;
- correct dialog and sheet focus management;
- status information not dependent on color;
- contrast verification;
- reduced-motion support;
- screen-reader announcements for form and mutation errors.

---

## 15. Performance and Data Rules

- Use route-level code splitting.
- Do not ship administration pages to employee-only routes unnecessarily.
- Use server pagination for large data sets.
- Debounce search input.
- Cancel obsolete requests when filters change.
- Cache stable master data with controlled refresh behavior.
- Avoid duplicate client requests after SSR hydration.
- Use skeletons that match final layout dimensions.
- Prefer CSS and Nuxt UI components over large animation libraries.
- Load charts only on pages that require them.
- Use virtualization for large schedules or matrices when necessary.

---

## 16. Backend Improvements Required for Release

1. Enforce employee ownership on self-service endpoints.
2. Enforce assignment scope on team and administrative endpoints.
3. Add pagination to attendance, leave, shifts, overtime, notifications, and work arrangements.
4. Add consistent sorting and search parameters.
5. Protect salary, identity, and bank fields using explicit permissions.
6. Standardize status values and document their transitions.
7. Return consistent conflict responses for overlapping records.
8. Add audit-log support for high-impact administrative changes.
9. Decide whether notifications use polling, server-sent events, or WebSockets.
10. Add missing update/deactivate actions for configuration records where business workflows require them.
11. Create a reliable test database fixture and migration routine.
12. Add rate limiting around login, password reset, and invitation validation.
13. Remove stale vendor-portal content from backend documentation.

---

## 17. Delivery Estimate

Suggested six-milestone delivery:

| Milestone | Outcome |
|---|---|
| 1 | Backend readiness, Nuxt foundation, authentication, responsive shell |
| 2 | Dashboard, notifications, and attendance |
| 3 | Leave, work arrangements, profile, and overtime |
| 4 | Manager approval workspace |
| 5 | Employee, user, shift, leave-policy, and organization administration |
| 6 | Reports, accessibility, security, performance, and release |

Approximate implementation range:

- one experienced full-stack developer: 10–14 weeks;
- two frontend developers with backend support: 6–8 weeks;
- additional time should be reserved if backend authorization rules or reporting requirements expand.

These estimates assume designs are approved progressively and backend decisions are made during the first milestone.

---

## 18. Definition of Done

A feature is complete only when:

- backend authorization is verified;
- desktop and mobile designs are implemented;
- loading, empty, error, forbidden, and success states exist;
- keyboard operation works;
- icon-only actions have accessible names;
- visual status is not communicated by color alone;
- form validation maps backend errors to useful messages;
- unit or component coverage exists where appropriate;
- critical path end-to-end coverage exists;
- responsive screenshots have been reviewed;
- documentation and generated API types are current.

The application is release-ready only when the Expo runtime has been fully removed, the backend schema and tests are reproducible, record-level authorization is enforced, and the supported employee and administrator workflows pass on both mobile and desktop.

