# Frappe HR to Nuxt UI Component & UX Mapping

This document provides a comprehensive mapping between Frappe HR (Desk & Mobile App) UI primitives/patterns and our Nuxt.js + Nuxt UI (v3/v4) architecture consuming FastAPI REST APIs.

---

## 1. UI Framework Component Mapping

| Frappe Concept / UI Component | Nuxt UI Component / Idiomatic Nuxt Pattern | Description & Application in HRMS |
| :--- | :--- | :--- |
| **Desk Application Shell** | `UDashboardGroup`, `UDashboardSidebar`, `UDashboardPanel`, `UDashboardNavbar` | Global responsive layout with collapsible sidebar, teleport headers, and mobile drawer/bottom navigation. |
| **Sidebar Navigation** | `UNavigationMenu` (vertical orientation) | Role-aware hierarchical navigation tree with badge indicators and active route highlighting. |
| **List View (DocType List)** | `UTable` + `UInput` + `USelect` + `UPagination` | Server-driven paginated tables with sorting, multi-column search, and filter bars (e.g. Employee, Attendance, Leaves). |
| **Form View (DocType Form)** | `UForm` / `UFormField` + `UCard` + `UTabs` | Sectioned forms with validation schema, state management, dirty tracking, and clear action toolbars. |
| **Dialog / Modal Window** | `UModal` (`v-model:open`) | Modal dialogs for creation wizards, approval confirmation, punch regularisation, and quick edits. |
| **Slide-over / Drawer** | `USlideover` | Off-canvas drawers for detailed logs, filter drawers, check-in punch maps, and audit trails. |
| **Dropdown Menu / Action Menu** | `UDropdownMenu` | Row action menus (Edit, Deactivate, View Audit Log, Download Slip). |
| **Select / Combobox** | `USelect` / `USelectMenu` | Searchable dropdowns for foreign keys (Units, Departments, Designations, Shifts, Leave Types). |
| **Date & Calendar Pickers** | `UInput` (type `date`), Nuxt UI Calendar / DatePicker, or VueUse date primitives | Range pickers for attendance filter, leave date spans, and payroll cycle windows. |
| **Tabs & Segmented Controls** | `UTabs` | Tabbed navigation for Employee Detail views (Personal, Employment, Attendance, Leaves, Shifts, Activity). |
| **Badge / Tag / Status Pill** | `UBadge` (`variant="soft"`) | Colored indicators for statuses: `ACTIVE` (emerald), `PENDING` (amber), `REJECTED` (rose), `HALF_DAY` (orange), etc. |
| **Alert Box** | `UAlert` | Informational banners for pending approvals, probation notices, and system alerts. |
| **Toast Notifications** | `useToast()` composable | Global interactive toast alerts with timeout, action buttons, and severity levels. |
| **Card Container** | `UCard` | Elevated surface containers for KPI statistics, dashboard summaries, and mobile list cards. |
| **Breadcrumbs** | `UBreadcrumb` | Contextual navigation paths (e.g., *Employees > EMP-0042 > Leaves*). |
| **Pagination Bar** | `UPagination` | Responsive pagination controls linked to `page` and `page_size` query state. |
| **Command Palette / Quick Search** | `UCommandPalette` / `UModal` global search | Quick navigation across employees, doctypes, and frequent actions. |
| **Loading & Skeleton States** | `USkeleton` + `UIcon` (`i-lucide-loader-circle animate-spin`) | Smooth content placeholders during API fetch cycles. |
| **Empty State** | Custom `EmptyState` slot pattern with `UIcon` + descriptive message | Explanatory UX when lists return 0 records with action triggers. |
| **Confirmation Popups** | `UModal` with `danger` variant button | Explicit guard for destructive operations (deactivate employee, cancel approved leave). |

---

## 2. Module & Workflow Mapping

### 2.1 Organization & Employees
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| `Employee` DocType | `/employees` (List & Cards) | `GET /api/v1/employees/` | Filter by status, unit, department; search by code/name; responsive table. |
| `Employee` Form | `/employees/create`, `/employees/[id]` | `POST /api/v1/employees/`, `GET/PUT /api/v1/employees/{id}` | Sectioned form: Personal, Org, Shift assignment, Biometric ID, Reporting Manager. |
| `Department` DocType | `/org` (Departments tab) | `GET /api/v1/org/departments`, `POST /api/v1/org/departments` | Hierarchical department listing and unit linkage. |
| `Company` / Branch | `/org` (Units tab) | `GET /api/v1/org/units`, `POST /api/v1/org/units` | Multi-unit factory/branch configuration. |
| `Designation` DocType | `/org` (Designations tab) | `GET /api/v1/designations/`, `POST /api/v1/designations/` | Designation taxonomy management. |

### 2.2 Attendance & Punching
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| `Employee Checkin` | `/attendance/checkins` | `GET/POST /api/v1/attendance/checkins` | Raw biometric/mobile punches with GPS geolocation (`IN`/`OUT`). |
| Mobile `CheckInPanel.vue` | Dashboard Widget & Quick Modal | `POST /api/v1/attendance/checkins` | One-touch web punch with geolocation capture and current shift countdown. |
| `Attendance` DocType | `/attendance` | `GET /api/v1/attendance/` | Processed daily attendance status (`PRESENT`, `ABSENT`, `HALF_DAY`, `ON_LEAVE`, `WEEKLY_OFF`, `HOLIDAY`). |
| `Attendance Request` (Regularization) | `/attendance/corrections` | `POST /api/v1/attendance/corrections`, `PATCH .../approve` | Employee punch regularisation request with manager approve/reject modal. |
| Attendance Processing Engine | Admin action on `/attendance` | `POST /api/v1/attendance/process` | Batch date-range calculation of attendance from raw punches and shift windows. |

### 2.3 Leave Management
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| `Leave Application` Dashboard | `/leaves` | `GET /api/v1/leaves/`, `GET /balance/employee/{id}` | Live balance meters, KPI metrics, status filters, self-service applications list. |
| `Leave Application` Form | `/leaves/apply` | `POST /api/v1/leaves/` | Dedicated form with real-time day calculation, consecutive-day limit checks, and ledger impact sidebar. |
| Leave Approval Desk | `/leaves/approvals` | `PATCH /api/v1/leaves/{id}/approve`, `PATCH .../reject` | Dedicated manager queue with status tabs, one-click approve, and rejection reason prompt. |
| `Leave Allocation` | `/leaves/allocations` | `GET/POST /api/v1/leaves/allocations` | Double-entry quota credit modal and master allocations history table. |
| `Leave Type` & Period Masters | `/leaves/types` | `GET/POST /api/v1/leaves/types`, `GET/POST .../periods` | Master policy configuration for paid/unpaid types, consecutive caps, carry-forward, and fiscal periods. |

### 2.4 Shift & Roster Management
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| `Shift Type` | `/shifts` | `GET/POST /api/v1/shifts/`, `PATCH .../{id}` | Master shift definitions with start/end time, auto cross-midnight detection, grace margins, and auto-attendance. |
| `Shift Assignment` | `/shifts/assignments` | `GET/POST /api/v1/shifts/assignments`, `PATCH .../cancel` | Master roster with filters; individual & bulk assignment (by Dept, Unit, or Staff) modals; cancellation action. |
| Shift Schedule & Night Shifts | `/shifts/schedule` | `GET /api/v1/shifts/employee/{id}/schedule` | Visual timeline inspection of allowed biometric punch windows (previous, active, upcoming) and overnight grouping. |

### 2.5 Work Arrangements (WFH / OD / Field)
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| Frappe custom doctype / Remote Work | `/work-arrangements/apply` | `POST /api/v1/work-arrangements/` | Requests for Work-from-Home, Out-Duty, and Field Work with date spans and reasons. |
| Approval Queue | `/work-arrangements/approvals` | `PATCH /api/v1/work-arrangements/{id}/approve` | Manager approval queue with status progression (`PENDING` $\rightarrow$ `APPROVED` / `REJECTED`). |

### 2.6 Holiday Lists
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| `Holiday List` & `Holiday` | `/holidays` | `GET/POST /api/v1/holidays/lists` | Yearly holiday calendar with auto weekly-off generator (Sunday / Alt Saturday). |

### 2.7 Reports & Analytics
| Frappe Reference | Nuxt Page / Route | FastAPI REST Endpoint | Key Workflow & Features |
| :--- | :--- | :--- | :--- |
| `Monthly Attendance Sheet` | `/reports/attendance-matrix` | `GET /api/v1/reports/attendance-matrix` | Unit-wise monthly matrix showing daily P/A/HD/L/WO status codes for all workers. |
| `Employee Leave Balance` | `/reports/leave-summary` | `GET /api/v1/reports/leave-summary` | Allocated, used, and remaining leave balances per employee and leave type. |
