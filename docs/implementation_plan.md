# HRMS P0 Implementation Plan — Phase 1

## Goal
Build the six core P0 modules from the SRS that are currently missing:
Org Structure → Employees → Shifts → Attendance → Leave → Overtime

Each module follows the same pattern: SQLAlchemy models → Alembic migration → FastAPI router → Pydantic schemas → Nuxt page.

---

## Build Order (strict dependency chain)

```
organizations / units / departments
        ↓
    employees
        ↓
      shifts + shift_assignments
        ↓
  attendance_records + attendance_punches
  attendance_discrepancies + corrections
        ↓
  leave_types + leave_balances + leave_applications
        ↓
  overtime_records + overtime_approvals
```

---

## Module 1 — Org Structure

### Backend

#### [MODIFY] `apps/api/db/models.py`
Add `Organization`, `Unit`, `Department` SQLAlchemy models with proper relationships to `Employee`.

#### [NEW] `apps/api/schemas/org.py`
Pydantic schemas: `OrgRead`, `UnitRead`, `UnitCreate`, `DepartmentRead`, `DepartmentCreate`.

#### [NEW] `apps/api/routers/org.py`
```
GET  /units                    — list all (scoped by user's assignments)
POST /units                    — create (Admin+)
PATCH /units/{id}              — update
GET  /units/{id}/departments   — departments in a unit
POST /departments              — create dept
PATCH /departments/{id}
```

#### Alembic migration
`add_org_unit_department_tables`

### Frontend

#### [NEW] `apps/web/app/pages/org.vue`
Org tree: Company → Units → Departments as a collapsible tree with inline management (add/edit unit/dept).
- Card per Unit, expandable to show departments
- "Add Department" inline form
- Breadcrumb: Dashboard → Organisation

---

## Module 2 — Employee Module

### Backend

#### [MODIFY] `apps/api/db/models.py`
Add `Employee` model with all SRS §8 fields:
- `employee_code`, `designation`, `employment_type` (PERMANENT/CONTRACT/TRAINEE)
- `status` (ACTIVE/INACTIVE/ON_NOTICE/SUSPENDED/TERMINATED/RESIGNED)
- `department_id`, `unit_id`, `date_of_joining`
- `biometric_id`, `monthly_salary`, `overtime_eligible`
- `reporting_manager_id` (self-ref FK)
- `shift_id` (current shift)
- `user_id` → links to auth `users` table

#### [NEW] `apps/api/schemas/employees.py`
`EmployeeRead`, `EmployeeCreate`, `EmployeeUpdate`, `PaginatedEmployeesResponse`

#### [NEW] `apps/api/routers/employees.py`
```
GET  /employees               — paginated, filterable, scoped by RBAC
POST /employees               — create (HR+)
GET  /employees/{id}          — detail with attendance summary
PATCH /employees/{id}         — update
PATCH /employees/{id}/deactivate
GET  /employees/{id}/leave-balance
GET  /employees/{id}/attendance — paginated attendance history
```

### Frontend

#### [NEW] `apps/web/app/pages/employees.vue`
Full employee table — sortable, filterable, searchable. Columns: Code, Name, Department, Designation, Shift, Status, Actions.
Actions: View, Edit, Deactivate.

#### [NEW] `apps/web/app/components/EmployeeFormModal.vue`
Create/edit modal: Personal info + Org assignment (Unit → Dept) + Shift + Employment type.

---

## Module 3 — Shifts

### Backend

#### [MODIFY] `apps/api/db/models.py`
Add `Shift`, `ShiftAssignment` models.

#### [NEW] `apps/api/schemas/shifts.py`
#### [NEW] `apps/api/routers/shifts.py`
```
GET  /shifts                     — list (by unit)
POST /shifts                     — create
POST /shift-assignments          — assign employee to shift
GET  /shift-assignments/employee/{emp_id} — history
```

### Frontend
Shifts management tab on the org/employee pages.

---

## Module 4 — Attendance

### Backend

#### [MODIFY] `apps/api/db/models.py`
Add `AttendancePunch`, `AttendanceRecord`, `AttendanceDiscrepancy`, `AttendanceCorrectionRequest`.

#### [NEW] `apps/api/routers/attendance.py`
```
GET  /attendance                    — paginated, date-filtered, scoped
POST /attendance/punches            — record a punch (HR manual entry)
GET  /attendance/employee/{emp_id}  — attendance history
GET  /attendance/calendar/{emp_id}  — monthly calendar data
GET  /attendance/discrepancies      — miss-punch queue
POST /attendance/corrections        — employee submits correction
PATCH /attendance/corrections/{id}/approve
PATCH /attendance/corrections/{id}/reject
```

### Frontend

#### [NEW] `apps/web/app/pages/attendance.vue`
- Tabs: My Attendance | Team Attendance (if has permission)
- Calendar view (color-coded daily status)
- List view with filters
- Miss-punch correction request button

---

## Module 5 — Leave Management

### Backend

#### [MODIFY] `apps/api/db/models.py`
Add `LeaveType`, `LeavePolicy`, `LeaveBalance`, `LeaveApplication`.

#### [NEW] `apps/api/routers/leaves.py`
```
GET  /leaves                        — my leave applications
POST /leaves                        — apply for leave
GET  /leaves/balance                — my leave balance
PATCH /leaves/{id}/cancel           — employee cancel
GET  /leaves/pending                — approval queue (HR/Dept Head)
PATCH /leaves/{id}/approve
PATCH /leaves/{id}/reject
GET  /leave-types                   — list configured leave types
```

### Frontend

#### [NEW] `apps/web/app/pages/leaves.vue`
- My Leave Balance cards
- Apply Leave form
- Leave history table
- (If HR/Dept Head) Pending approvals queue

---

## Module 6 — Overtime

### Backend

#### [MODIFY] `apps/api/db/models.py`
Add `OvertimeRecord`, `OvertimeApproval`.

#### [NEW] `apps/api/routers/overtime.py`
```
GET  /overtime                      — my OT records
GET  /overtime/pending              — approval queue
PATCH /overtime/{id}/approve
GET  /overtime/report               — summary (unit/dept scoped)
```

### Frontend
OT summary section on dashboard + `/overtime` page.

---

## Approach

> [!IMPORTANT]
> The demo seeder has already created these tables directly via raw SQL. We'll now rebuild them **properly** as SQLAlchemy models + Alembic migrations so they're fully managed. The seeder's raw tables will be dropped and recreated via Alembic.

1. All 6 modules' models will be added to `models.py` in one pass
2. One Alembic migration for all new tables (clean, atomic)
3. The `seed_demo_data.py` will be updated to use SQLAlchemy ORM instead of raw SQL
4. Routers built module by module, tested after each
5. Frontend pages built in parallel with the backend routers

---

## Verification Plan

### Automated
- `uv run pytest -x` after each module

### Manual
- Login as each of the 5 demo user types and verify RBAC scoping works
- Employee: can only see own data
- Dept Head: sees only their department
- Unit Head: sees whole unit
- HR Manager: sees unit employees
- Super Admin: sees everything

---

## Timeline

| Step | What |
|---|---|
| 1 | Models: all 6 modules added to models.py + migration |
| 2 | Org Structure API + frontend page |
| 3 | Employee API + employees.vue |
| 4 | Shifts API |
| 5 | Attendance API + attendance.vue |
| 6 | Leave API + leaves.vue |
| 7 | Overtime API |
| 8 | Update dashboard to pull real data |

Click **Proceed** to start execution.
