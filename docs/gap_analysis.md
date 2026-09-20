# HRMS Gap Analysis — SRS vs. Current Implementation

## ✅ What's Implemented (Working Today)

### Foundation
- [x] **Authentication** — JWT login/logout, password hashing, rate limiting
- [x] **Password management** — Reset via email, invitation flow, `set-password` page, forgot-password page
- [x] **Session management** — Idle timeout, auto-refresh tokens
- [x] **Dynamic RBAC** — `roles`, `permissions`, `role_permissions`, `user_role_assignments` tables; `has_permission()`, `get_effective_permissions()`, `scope_type/scope_id` enforcement
- [x] **7 seed roles** — SUPER_ADMIN, ADMIN, HR_OWNER, HR_MANAGER, UNIT_HEAD, DEPARTMENT_HEAD, EMPLOYEE
- [x] **Permission matrix** — 30+ permission codes seeded in DB
- [x] **User management** — Create, update, deactivate, paginated list, search, filter by role/status
- [x] **Role management UI** — Roles page, assign permissions
- [x] **Scoped role assignments** — `GET/POST/DELETE /users/{id}/assignments`
- [x] **In-app notifications** — Bell icon, read/unread, notification feed
- [x] **Dashboard** — Permission-driven widget visibility via `/dashboard/widgets`
- [x] **Profile page** — View and update own profile, change password
- [x] **Email invitations** — Invitation flow with token, Zoho Mail integration
- [x] **Audit trail partial** — API logs, some notification triggers
- [x] **PWA** — Install prompt, offline banner, update notification

---

## ❌ Missing: P0 Critical (SRS §66 — Must Have for MVP)

### 🏢 Organization Structure (SRS §8, §46, §49)
Missing tables and APIs for the org hierarchy that everything else depends on:

| Entity | Tables Needed | APIs Needed |
|---|---|---|
| **Organizations** | `organizations` | `GET/POST /organizations` |
| **Units** | `units` | `GET/POST/PATCH /units` |
| **Departments** | `departments` | `GET/POST/PATCH /departments` |
| **Employees** | `employees`, `employee_employment_details` | Full CRUD `/employees` |

> [!CAUTION]
> **Every other P0 feature depends on this.** Attendance, leave, shifts, overtime — all require `unit_id` and `department_id`. Until these tables exist, the rest of the SRS cannot be built.

---

### 👤 Employee Module (SRS §8, §43)
- [ ] Employee profile: employee code, designation, date of joining, employment type (permanent/contract)
- [ ] Department + Unit assignment for each employee
- [ ] Reporting manager assignment
- [ ] Employee status: ACTIVE / INACTIVE / SUSPENDED / TERMINATED / RESIGNED
- [ ] Biometric/attendance ID field
- [ ] Salary cost field (permission-gated)
- [ ] Overtime eligibility flag
- [ ] Frontend: `/employees` page (currently only `/users` exists — users ≠ employees)

---

### 🕐 Attendance Module (SRS §10–15, §47)
- [ ] `attendance_punches` table (raw biometric data)
- [ ] `attendance_records` table (processed daily summary per employee)
- [ ] Attendance statuses: PRESENT, ABSENT, ON_LEAVE, HOLIDAY, WEEKLY_OFF, HALF_DAY, LATE, MISSED_PUNCH
- [ ] Missed punch auto-detection
- [ ] Attendance history view (day/week/month/date-range)
- [ ] Attendance calendar (SRS §38) with color-coded status grid
- [ ] API: `GET /attendance`, `POST /attendance/punches`
- [ ] Frontend: `/attendance` page

---

### 🔄 Attendance Correction Workflow (SRS §14, §35, §56)
- [ ] `attendance_discrepancies` table
- [ ] `attendance_correction_requests` table
- [ ] Employee submits correction → Department Head/HR approves
- [ ] Audit trail per correction (old value → new value → reason → approver)
- [ ] HR miss-punch queue (SRS §34)
- [ ] API: `POST /attendance/corrections`, `PATCH /attendance/corrections/{id}/approve`

---

### 📅 Shift Management (SRS §16–18)
- [ ] `shifts` table (name, start_time, end_time, grace_period, break_duration, cross-midnight support)
- [ ] `shift_assignments` table (employee + shift + date range + assigned_by)
- [ ] Employee view: current shift, upcoming shifts, past shifts
- [ ] HR: bulk shift assignment (by department/group)
- [ ] API: `GET/POST /shifts`, `POST /shift-assignments`
- [ ] Frontend: `/shifts` page

---

### 🌴 Leave Management (SRS §21–27, §55)
- [ ] `leave_types` table (Casual, Sick, Earned, Maternity, Paternity, Compensatory)
- [ ] `leave_policies` table (allocation, carry-forward, max consecutive days, paid/unpaid)
- [ ] `leave_balances` table (per employee per leave type)
- [ ] `leave_applications` table (with PENDING/APPROVED/REJECTED/CANCELLED status)
- [ ] Leave application workflow with balance validation + date conflict check
- [ ] Department Head leave approval queue
- [ ] Leave cancellation/withdrawal
- [ ] API: `POST /leaves`, `PATCH /leaves/{id}/approve`, `GET /leave-balances`
- [ ] Frontend: `/leaves` page

---

### ⏰ Overtime Module (SRS §19–20, §57)
- [ ] `overtime_records` table (calculated OT per attendance day)
- [ ] `overtime_approvals` table (approved vs unapproved OT)
- [ ] OT calculation from attendance worked_minutes vs shift scheduled_minutes
- [ ] Minimum OT duration rules (configurable)
- [ ] API: `GET /overtime`, `POST /overtime/{id}/approve`
- [ ] Frontend: `/overtime` page

---

### 📅 Holidays & Weekly-Off (SRS §37)
- [ ] `holidays` table (organization/unit-specific, date, name)
- [ ] `weekly_off_rules` table (Sunday / Sat+Sun / Rotational / Department-specific)
- [ ] API: `GET/POST /holidays`

---

### 📋 Reports (SRS §40)
- [ ] Daily/Monthly attendance report
- [ ] Department attendance summary
- [ ] Absentee report, Late-coming report, Miss-punch report
- [ ] Leave balance report, Leave utilization report
- [ ] Overtime report (employee/department/unit)
- [ ] Salary/workforce cost report
- [ ] CSV export
- [ ] Frontend: `/reports` page

---

### 🗒️ Audit Log (SRS §42)
- [ ] `audit_logs` table (actor, action, entity_type, entity_id, old_value, new_value, reason, ip, timestamp)
- [ ] Events: EMPLOYEE_CREATED, ATTENDANCE_CORRECTED, LEAVE_APPROVED, ROLE_ASSIGNED, etc.
- [ ] API: `GET /audit-logs` (Super Admin/Auditor only)
- [ ] Frontend: Audit log viewer in admin section

---

## ⚠️ Missing: P1 (Important, follow MVP)

- [ ] Email notifications for leave/attendance events (infrastructure exists, triggers missing)
- [ ] Holiday calendar UI
- [ ] Rotational weekly-off configuration UI
- [ ] CSV/PDF export for reports
- [ ] Advanced attendance trend charts (attendance %, absence trend over time)

---

## 📊 Current Implementation Score

| Module | Status |
|---|---|
| Auth & Security | ✅ ~90% |
| Dynamic RBAC | ✅ ~85% |
| User Management | ✅ ~80% |
| Notifications | ✅ ~75% |
| Dashboard (framework) | ✅ ~60% |
| **Organization Structure** | ❌ 0% |
| **Employee Module** | ❌ 0% |
| **Attendance** | ❌ 0% |
| **Attendance Corrections** | ❌ 0% |
| **Shifts** | ❌ 0% |
| **Leave Management** | ❌ 0% |
| **Overtime** | ❌ 0% |
| **Holiday/Weekly-off** | ❌ 0% |
| **Reports** | ❌ 0% |
| **Audit Log** | ❌ 0% |

---

## 🔢 Recommended Build Order (from SRS §66 P0)

1. **Org Structure** → organizations, units, departments tables + APIs
2. **Employee Module** → employees table + CRUD + `/employees` page
3. **Shifts** → shifts + shift_assignments + assignment UI
4. **Attendance** → punches + records + calendar + discrepancy
5. **Attendance Corrections** → correction workflow + approval queue
6. **Leave Management** → leave types + balance + application + approval
7. **Overtime** → OT records + approval workflow
8. **Holidays** → holiday + weekly-off tables
9. **Reports** → aggregated report endpoints + export
10. **Audit Log** → audit_logs table + viewer
