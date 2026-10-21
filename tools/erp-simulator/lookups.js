/*
 * Reference-data lookups.
 *
 * These endpoints require human (bearer) authentication, not ERP machine auth,
 * so the page signs in as Super Admin (or a business user) to populate the
 * dropdowns that supply numeric IDs to the ERP write endpoints.
 *
 * Every paginated endpoint returns:
 *   { items: [...], total, page, page_size, total_pages, has_next, has_prev }
 */

/*
 * The technical Super Admin is deliberately barred from workforce operations
 * (the API answers 403 TECHNICAL_ADMIN_ONLY), so it cannot be used for these
 * lookups. Reference data must be read as a *business* user — an employee with
 * sufficient scope (for example an ORGANIZATION_OWNER, or HR_ADMIN promoted to
 * ORGANIZATION scope).
 */
window.LOGIN_ENDPOINTS = [
  { id: "employee", label: "Business user (/auth/employee/login)", path: "/api/v1/auth/employee/login" },
  {
    id: "super-admin",
    label: "Technical Super Admin — no workforce access",
    path: "/api/v1/auth/super-admin/login",
  },
];

window.LOOKUP_SOURCES = {
  organization: {
    label: "Organization",
    path: "/api/v1/org/organization",
    single: true,
    labelOf: (r) => `${r.name} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  organizations: {
    label: "Organizations",
    path: "/api/v1/org/organization",
    single: true,
    labelOf: (r) => `${r.name} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  units: {
    label: "Units",
    path: "/api/v1/org/units?page_size=100",
    labelOf: (r) => `${r.name}${r.code ? ` [${r.code}]` : ""} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  departments: {
    label: "Departments",
    path: "/api/v1/org/departments?page_size=100",
    labelOf: (r) => `${r.name}${r.code ? ` [${r.code}]` : ""} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  designations: {
    label: "Designations",
    path: "/api/v1/designations/?page_size=100",
    labelOf: (r) => `${r.name}${r.code ? ` [${r.code}]` : ""} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  employees: {
    label: "Employees",
    path: "/api/v1/employees/?page_size=100",
    labelOf: (r) =>
      `${r.employee_code} — ${r.first_name}${r.last_name ? ` ${r.last_name}` : ""} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  shifts: {
    label: "Shifts",
    path: "/api/v1/shifts/?page_size=100&is_active=true",
    labelOf: (r) => `${r.name}${r.code ? ` [${r.code}]` : ""} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  shiftAssignments: {
    label: "Shift assignments",
    path: "/api/v1/shifts/assignments?page_size=100",
    labelOf: (r) => `#${r.id} — ${r.employee_name || r.employee_code || r.employee_id} → ${r.shift_name || r.shift_id}`,
    valueOf: (r) => r.id,
  },
  attendanceRecords: {
    label: "Attendance records",
    path: "/api/v1/attendance/?page_size=100",
    labelOf: (r) => `#${r.id} — emp ${r.employee_id} ${r.attendance_date} (${r.status})`,
    valueOf: (r) => r.id,
  },
  leaveTypes: {
    label: "Leave types",
    path: "/api/v1/leaves/types?page_size=100&is_active=true",
    labelOf: (r) => `${r.name} [${r.code}] (#${r.id})`,
    valueOf: (r) => r.id,
  },
  leavePeriods: {
    label: "Leave periods",
    path: "/api/v1/leaves/periods?page_size=100",
    labelOf: (r) => `${r.name} (#${r.id})`,
    valueOf: (r) => r.id,
  },
  overtime: {
    label: "Overtime records",
    path: "/api/v1/overtime/?page_size=100",
    labelOf: (r) => `#${r.id} — emp ${r.employee_id} ${r.calculated_minutes}m`,
    valueOf: (r) => r.id,
  },
  holidayLists: {
    label: "Holiday lists",
    path: "/api/v1/holidays/lists?page_size=100",
    labelOf: (r) => `${r.name} (#${r.id})`,
    valueOf: (r) => r.id,
  },
};

/* Flatten an API payload into a list of { value, label } options. */
window.extractOptions = function extractOptions(source, payload) {
  let rows;
  if (source.single) {
    rows = payload ? [payload] : [];
  } else {
    rows = Array.isArray(payload) ? payload : (payload && payload.items) || [];
  }
  return rows
    .filter(Boolean)
    .map((row) => ({ value: source.valueOf(row), label: source.labelOf(row), raw: row }));
};
