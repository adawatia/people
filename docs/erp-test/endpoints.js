/*
 * ERP endpoint catalog.
 *
 * Every entry mirrors a route registered in app/api/routers/erp_*.py.  Paths are
 * absolute and include the /api/v1 prefix so the page can join them straight
 * onto the configured base URL.
 *
 * Body editor: each endpoint declares its request body as typed *fields* rather
 * than a JSON sample, so the page renders real inputs (text, number, date, time,
 * checkbox, select, reference dropdown) and the operator never has to remember
 * parameter names or types.
 *
 * Field types
 *   text | email | password | int | float | date | time | datetime
 *   bool      -> tri-state select; `default` prefills it, otherwise "leave unchanged"
 *   select    -> fixed `options`
 *   lookup    -> reference dropdown; `lookup` is a key in lookups.js, `valueField`
 *                picks which property becomes the value (default "id")
 *   multilookup -> multiple-select producing an array
 *   text with `suggest` -> free text with datalist suggestions
 *
 * Body shapes
 *   none          no body
 *   object        `fields`
 *   object-array  one array under `arrayKey`, rows built from `itemFields`
 *   array         bare array of objects built from `itemFields`
 *   string-array  bare array of strings
 */

window.ERP_BASE_PATH = "/api/v1";

const ROLES = ["EMPLOYEE", "DEPARTMENT_MANAGER", "HR_ADMIN", "ORGANIZATION_OWNER"];
const SCOPES = ["SELF", "DEPARTMENT", "UNIT", "ORGANIZATION"];
const ATTENDANCE_STATUS = [
  "PRESENT",
  "ABSENT",
  "HALF_DAY",
  "ON_LEAVE",
  "WORK_FROM_HOME",
  "WEEKLY_OFF",
  "HOLIDAY",
  "MISSED_PUNCH",
];
const EMPLOYMENT_TYPES = ["PERMANENT", "PROBATION", "CONTRACT", "INTERN", "CONSULTANT"];

/* Fields shared by the employee create/upsert/update endpoints. */
function employeeFields({ update = false, account = false } = {}) {
  const optionalDefault = (value) => (update ? undefined : value);
  const fields = [];
  if (!update) {
    fields.push({ name: "employee_code", type: "text", required: true, section: "Identity", placeholder: "EMP001" });
  }
  fields.push(
    {
      name: "role",
      type: "select",
      section: "Identity",
      options: ROLES,
      default: optionalDefault("EMPLOYEE"),
      help: "Business role; drives default access scope.",
    },
    { name: "first_name", type: "text", required: true, section: "Identity" },
    { name: "last_name", type: "text", section: "Identity" },
    { name: "date_of_joining", type: "date", section: "Identity" },
    {
      name: "employment_type",
      type: "text",
      section: "Identity",
      suggest: EMPLOYMENT_TYPES,
      default: optionalDefault("PERMANENT"),
    },
    { name: "status", type: "select", section: "Identity", options: ["ACTIVE", "INACTIVE"], default: optionalDefault("ACTIVE") },
    { name: "overtime_eligible", type: "bool", section: "Identity", default: optionalDefault(true) },
    { name: "biometric_id", type: "text", section: "Identity" },

    { name: "official_email", type: "email", section: "Contact" },
    { name: "personal_email", type: "email", section: "Contact" },
    {
      name: "phone_number",
      type: "text",
      section: "Contact",
      required: !update && account,
      placeholder: "9876543210",
      help: "Indian mobile: 10 digits starting 6-9.",
    },
    { name: "date_of_birth", type: "date", section: "Contact" },
    { name: "gender", type: "text", section: "Contact", suggest: ["MALE", "FEMALE", "OTHER"] },
    {
      name: "marital_status",
      type: "text",
      section: "Contact",
      suggest: ["SINGLE", "MARRIED", "DIVORCED", "WIDOWED"],
    },
    { name: "blood_group", type: "text", section: "Contact", suggest: ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"] },

    { name: "emergency_contact_name", type: "text", section: "Emergency contact" },
    { name: "emergency_contact_phone", type: "text", section: "Emergency contact" },
    { name: "emergency_contact_relation", type: "text", section: "Emergency contact" },

    { name: "current_address", type: "text", section: "Address" },
    { name: "permanent_address", type: "text", section: "Address" },

    { name: "pan_number", type: "text", section: "Statutory & bank" },
    { name: "aadhaar_number", type: "text", section: "Statutory & bank" },
    { name: "bank_name", type: "text", section: "Statutory & bank" },
    { name: "bank_account_number", type: "text", section: "Statutory & bank" },
    { name: "bank_ifsc_code", type: "text", section: "Statutory & bank" },

    { name: "designation", type: "text", section: "Assignment" },
    { name: "designation_id", type: "lookup", lookup: "designations", section: "Assignment" },
    { name: "unit_id", type: "lookup", lookup: "units", section: "Assignment" },
    { name: "department_id", type: "lookup", lookup: "departments", section: "Assignment" },
    { name: "shift_id", type: "lookup", lookup: "shifts", section: "Assignment" },
    { name: "reporting_manager_id", type: "lookup", lookup: "employees", section: "Assignment" },
    { name: "monthly_salary", type: "float", section: "Assignment" },
  );

  if (account) {
    fields.push(
      { name: "create_user_account", type: "bool", section: "Portal account", default: true },
      { name: "username", type: "text", section: "Portal account" },
      { name: "initial_password", type: "password", section: "Portal account", required: true },
    );
  }

  if (update) {
    fields.push(
      {
        name: "business_role",
        type: "select",
        section: "Access",
        options: ROLES,
        help: "Explicit role grant for ERP-driven provisioning.",
      },
      { name: "access_scope", type: "select", section: "Access", options: SCOPES },
      { name: "access_scope_id", type: "int", section: "Access" },
      { name: "exit_date", type: "date", section: "Access" },
      { name: "exit_reason", type: "text", section: "Access" },
    );
  }
  return fields;
}

window.ENDPOINTS = [
  // ── Organization + master data ────────────────────────────────────────────
  {
    id: "org-upsert",
    group: "Organization & master data",
    label: "Upsert organization",
    method: "PUT",
    path: "/api/v1/integrations/erp/organization/{erp_id}",
    scope: "master-data:write",
    pathParams: [{ name: "erp_id", sample: "ORG-001" }],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", required: true, section: "Organization", help: "Required on first create." },
        { name: "short_name", type: "text", section: "Organization" },
        { name: "industry", type: "text", section: "Organization" },
        { name: "phone", type: "text", section: "Contact" },
        { name: "email", type: "email", section: "Contact" },
        { name: "website", type: "text", section: "Contact" },
        { name: "tax_id", type: "text", section: "Contact" },
        { name: "address_line1", type: "text", section: "Address" },
        { name: "address_line2", type: "text", section: "Address" },
        { name: "city", type: "text", section: "Address" },
        { name: "state", type: "text", section: "Address" },
        { name: "country", type: "text", section: "Address" },
        { name: "postal_code", type: "text", section: "Address" },
      ],
    },
  },
  {
    id: "org-list",
    group: "Organization & master data",
    label: "List organizations",
    method: "GET",
    path: "/api/v1/integrations/erp/organizations",
    scope: "master-data:read",
    pathParams: [],
    body: { shape: "none" },
  },
  {
    id: "org-update",
    group: "Organization & master data",
    label: "Update organization",
    method: "PATCH",
    path: "/api/v1/integrations/erp/organization",
    scope: "master-data:write",
    pathParams: [],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", section: "Organization" },
        { name: "short_name", type: "text", section: "Organization" },
        { name: "industry", type: "text", section: "Organization" },
        { name: "phone", type: "text", section: "Contact" },
        { name: "email", type: "email", section: "Contact" },
        { name: "website", type: "text", section: "Contact" },
        { name: "tax_id", type: "text", section: "Contact" },
        { name: "address_line1", type: "text", section: "Address" },
        { name: "address_line2", type: "text", section: "Address" },
        { name: "city", type: "text", section: "Address" },
        { name: "state", type: "text", section: "Address" },
        { name: "country", type: "text", section: "Address" },
        { name: "postal_code", type: "text", section: "Address" },
      ],
    },
  },

  // ── Employees ─────────────────────────────────────────────────────────────

  // ── Employees ─────────────────────────────────────────────────────────────
  {
    id: "employee-create",
    group: "Employees",
    label: "Create employee + login",
    method: "POST",
    path: "/api/v1/integrations/erp/employees",
    scope: "employees:write",
    pathParams: [],
    body: { shape: "object", fields: employeeFields({ account: true }) },
  },
  {
    id: "employee-upsert",
    group: "Employees",
    label: "Upsert employee (by ERP id)",
    method: "PUT",
    path: "/api/v1/integrations/erp/employees/by-erp-id/{erp_id}",
    scope: "employees:write",
    pathParams: [{ name: "erp_id", sample: "EMP-001" }],
    body: { shape: "object", fields: employeeFields({ account: true }) },
    notes: "First call creates the linked login; later calls update ERP-owned fields without touching the password.",
  },
  {
    id: "employee-update",
    group: "Employees",
    label: "Update employee",
    method: "PATCH",
    path: "/api/v1/integrations/erp/employees/{employee_id}",
    scope: "employees:write",
    pathParams: [{ name: "employee_id", sample: "1", lookup: "employees" }],
    body: { shape: "object", fields: employeeFields({ update: true }) },
  },
  {
    id: "employee-deactivate",
    group: "Employees",
    label: "Deactivate employee",
    method: "PATCH",
    path: "/api/v1/integrations/erp/employees/{employee_id}/deactivate",
    scope: "employees:write",
    pathParams: [{ name: "employee_id", sample: "1", lookup: "employees" }],
    body: {
      shape: "object",
      fields: [
        { name: "exit_date", type: "date", section: "Exit" },
        { name: "exit_reason", type: "text", section: "Exit" },
      ],
    },
  },
  {
    id: "employee-activate",
    group: "Employees",
    label: "Activate employee",
    method: "PATCH",
    path: "/api/v1/integrations/erp/employees/{employee_id}/activate",
    scope: "employees:write",
    pathParams: [{ name: "employee_id", sample: "1", lookup: "employees" }],
    body: { shape: "none" },
  },
  {
    id: "employee-password-reset",
    group: "Employees",
    label: "Set temporary password",
    method: "POST",
    path: "/api/v1/integrations/erp/employees/{employee_id}/password-reset",
    scope: "identity:write",
    pathParams: [{ name: "employee_id", sample: "1", lookup: "employees" }],
    body: {
      shape: "object",
      fields: [
        {
          name: "temporary_password",
          type: "password",
          required: true,
          section: "Password",
          help: "Must satisfy the password policy; the employee must change it after signing in.",
        },
      ],
    },
  },

  // ── Shifts ────────────────────────────────────────────────────────────────
  {
    id: "shift-create",
    group: "Shifts",
    label: "Create shift",
    method: "POST",
    path: "/api/v1/integrations/erp/shifts",
    scope: "shifts:write",
    pathParams: [],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", required: true, section: "Shift" },
        { name: "code", type: "text", section: "Shift" },
        { name: "start_time", type: "time", required: true, section: "Shift" },
        { name: "end_time", type: "time", required: true, section: "Shift" },
        { name: "grace_minutes", type: "int", default: 10, section: "Shift" },
        { name: "break_minutes", type: "int", default: 30, section: "Shift" },
        { name: "is_cross_midnight", type: "bool", default: false, section: "Shift" },
        { name: "is_active", type: "bool", default: true, section: "Shift" },
        { name: "unit_id", type: "lookup", lookup: "units", section: "Shift" },
      ],
    },
  },
  {
    id: "shift-upsert",
    group: "Shifts",
    label: "Upsert shift (by ERP id)",
    method: "PUT",
    path: "/api/v1/integrations/erp/shifts/by-erp-id/{erp_id}",
    scope: "shifts:write",
    pathParams: [{ name: "erp_id", sample: "SHIFT-001" }],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", required: true, section: "Shift" },
        { name: "code", type: "text", section: "Shift" },
        { name: "start_time", type: "time", required: true, section: "Shift" },
        { name: "end_time", type: "time", required: true, section: "Shift" },
        { name: "grace_minutes", type: "int", default: 10, section: "Shift" },
        { name: "break_minutes", type: "int", default: 30, section: "Shift" },
        { name: "is_cross_midnight", type: "bool", default: false, section: "Shift" },
        { name: "is_active", type: "bool", default: true, section: "Shift" },
        { name: "unit_id", type: "lookup", lookup: "units", section: "Shift" },
      ],
    },
  },
  {
    id: "shift-update",
    group: "Shifts",
    label: "Update shift",
    method: "PATCH",
    path: "/api/v1/integrations/erp/shifts/{shift_id}",
    scope: "shifts:write",
    pathParams: [{ name: "shift_id", sample: "1", lookup: "shifts" }],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", section: "Shift" },
        { name: "code", type: "text", section: "Shift" },
        { name: "start_time", type: "time", section: "Shift" },
        { name: "end_time", type: "time", section: "Shift" },
        { name: "grace_minutes", type: "int", section: "Shift" },
        { name: "break_minutes", type: "int", section: "Shift" },
        { name: "is_cross_midnight", type: "bool", section: "Shift" },
        { name: "is_active", type: "bool", section: "Shift" },
      ],
    },
  },
  {
    id: "shift-assign",
    group: "Shifts",
    label: "Assign shift to employee",
    method: "POST",
    path: "/api/v1/integrations/erp/shifts/assignments",
    scope: "shifts:write",
    pathParams: [],
    body: {
      shape: "object",
      fields: [
        { name: "employee_id", type: "lookup", lookup: "employees", required: true, section: "Assignment" },
        { name: "shift_id", type: "lookup", lookup: "shifts", required: true, section: "Assignment" },
        { name: "effective_from", type: "date", required: true, section: "Assignment" },
        { name: "effective_to", type: "date", section: "Assignment" },
      ],
    },
  },
  {
    id: "shift-bulk-assign",
    group: "Shifts",
    label: "Bulk assign shifts",
    method: "POST",
    path: "/api/v1/integrations/erp/shifts/assignments/bulk",
    scope: "shifts:write",
    pathParams: [],
    body: {
      shape: "object",
      fields: [
        { name: "shift_id", type: "lookup", lookup: "shifts", required: true, section: "Assignment" },
        { name: "effective_from", type: "date", required: true, section: "Assignment" },
        { name: "effective_to", type: "date", section: "Assignment" },
        { name: "employee_ids", type: "multilookup", lookup: "employees", section: "Targets", help: "Leave empty to use department/unit." },
        { name: "department_id", type: "lookup", lookup: "departments", section: "Targets" },
        { name: "unit_id", type: "lookup", lookup: "units", section: "Targets" },
      ],
    },
  },
  {
    id: "shift-assignment-cancel",
    group: "Shifts",
    label: "Cancel shift assignment",
    method: "PATCH",
    path: "/api/v1/integrations/erp/shifts/assignments/{assignment_id}/cancel",
    scope: "shifts:write",
    pathParams: [{ name: "assignment_id", sample: "1", lookup: "shiftAssignments" }],
    body: { shape: "none" },
  },

  // ── Attendance ────────────────────────────────────────────────────────────
  {
    id: "attendance-bulk",
    group: "Attendance",
    label: "Bulk sync attendance records",
    method: "POST",
    path: "/api/v1/integrations/erp/attendance/records/bulk",
    scope: "attendance:write",
    pathParams: [],
    body: {
      shape: "object-array",
      arrayKey: "records",
      arrayLabel: "Records",
      itemFields: [
        { name: "employee_id", type: "lookup", lookup: "employees", label: "Employee" },
        { name: "employee_code", type: "lookup", lookup: "employees", valueField: "employee_code", label: "Employee code" },
        { name: "erp_record_id", type: "text", required: true, placeholder: "ERP-ATT-20260920-EMP001" },
        { name: "attendance_date", type: "date", required: true },
        { name: "status", type: "select", options: ATTENDANCE_STATUS, required: true, default: "PRESENT" },
        { name: "shift_id", type: "lookup", lookup: "shifts" },
        { name: "punch_in", type: "time" },
        { name: "punch_out", type: "time" },
        { name: "worked_minutes", type: "int" },
        { name: "overtime_minutes", type: "int" },
        { name: "late_minutes", type: "int" },
        { name: "early_exit_minutes", type: "int" },
      ],
    },
    notes: "Retries are idempotent by erp_record_id. Provide employee_id or employee_code.",
  },

  // ── Overtime ──────────────────────────────────────────────────────────────
  {
    id: "overtime-bulk",
    group: "Overtime",
    label: "Bulk sync overtime records",
    method: "POST",
    path: "/api/v1/integrations/erp/overtime/records/bulk",
    scope: "overtime:write",
    pathParams: [],
    body: {
      shape: "array",
      arrayLabel: "Overtime records",
      itemFields: [
        { name: "erp_event_id", type: "text", required: true, placeholder: "ERP-OT-1001" },
        { name: "employee_id", type: "lookup", lookup: "employees", label: "Employee" },
        { name: "employee_code", type: "lookup", lookup: "employees", valueField: "employee_code", label: "Employee code" },
        { name: "attendance_record_id", type: "lookup", lookup: "attendanceRecords", required: true },
        { name: "overtime_start", type: "datetime" },
        { name: "overtime_end", type: "datetime" },
        { name: "calculated_minutes", type: "int", required: true },
        { name: "approved_minutes", type: "int" },
        { name: "status", type: "select", options: ["APPROVED", "PENDING", "REJECTED"], default: "APPROVED" },
      ],
    },
    notes: "approved_minutes cannot exceed calculated_minutes. The attendance record must belong to the same employee.",
  },

  // ── Holidays ──────────────────────────────────────────────────────────────
  {
    id: "holidays-bulk",
    group: "Holidays",
    label: "Bulk sync holidays",
    method: "POST",
    path: "/api/v1/integrations/erp/holidays/bulk",
    scope: "holidays:write",
    pathParams: [],
    body: {
      shape: "array",
      arrayLabel: "Holidays",
      itemFields: [
        { name: "erp_holiday_id", type: "text", required: true, placeholder: "HOL-2026-01" },
        { name: "name", type: "text", required: true, placeholder: "Republic Day" },
        { name: "holiday_date", type: "date", required: true },
        { name: "description", type: "text" },
        { name: "is_active", type: "bool", default: true, help: "Set false to delete the holiday." },
      ],
    },
  },

  // ── Leaves ────────────────────────────────────────────────────────────────
  {
    id: "leave-changes",
    group: "Leaves",
    label: "Get leave status changes",
    method: "GET",
    path: "/api/v1/integrations/erp/leaves/changes",
    scope: "leaves:read",
    pathParams: [],
    queryParams: [
      { name: "since", value: "" },
      { name: "limit", value: "100" },
    ],
    body: { shape: "none" },
    notes: "Optional since is an ISO timestamp; leave blank to fetch all unacknowledged changes.",
  },
  {
    id: "leave-changes-ack",
    group: "Leaves",
    label: "Acknowledge leave changes",
    method: "POST",
    path: "/api/v1/integrations/erp/leaves/changes/ack",
    scope: "leaves:write",
    pathParams: [],
    body: { shape: "string-array", arrayLabel: "ERP event IDs", placeholder: "ERP-LEAVE-EVENT-ID" },
    notes: "Event IDs come from the changes feed above.",
  },
  {
    id: "leave-balances-bulk",
    group: "Leaves",
    label: "Bulk sync leave balances",
    method: "POST",
    path: "/api/v1/integrations/erp/leaves/balances/bulk",
    scope: "leaves:write",
    pathParams: [],
    body: {
      shape: "array",
      arrayLabel: "Leave balances",
      itemFields: [
        { name: "employee_id", type: "lookup", lookup: "employees", label: "Employee" },
        { name: "employee_code", type: "lookup", lookup: "employees", valueField: "employee_code", label: "Employee code" },
        { name: "leave_code", type: "lookup", lookup: "leaveTypes", valueField: "code", required: true, label: "Leave code" },
        { name: "year", type: "int", required: true, default: new Date().getFullYear() },
        { name: "allocated", type: "float", default: 0 },
        { name: "used", type: "float", default: 0 },
        { name: "pending", type: "float", default: 0 },
      ],
    },
  },
  {
    id: "leave-period-create",
    group: "Leaves",
    label: "Create leave period",
    method: "POST",
    path: "/api/v1/integrations/erp/leaves/periods",
    scope: "leave-master:write",
    pathParams: [],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", required: true, section: "Period" },
        { name: "from_date", type: "date", required: true, section: "Period" },
        { name: "to_date", type: "date", required: true, section: "Period" },
        { name: "is_active", type: "bool", default: true, section: "Period" },
      ],
    },
  },
  {
    id: "leave-type-create",
    group: "Leaves",
    label: "Create leave type",
    method: "POST",
    path: "/api/v1/integrations/erp/leaves/types",
    scope: "leave-master:write",
    pathParams: [],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", required: true, section: "Leave type" },
        { name: "code", type: "text", required: true, section: "Leave type" },
        { name: "is_paid", type: "bool", default: true, section: "Leave type" },
        { name: "annual_allocation", type: "int", default: 0, section: "Leave type" },
        { name: "max_consecutive_days", type: "int", section: "Leave type" },
        { name: "requires_approval", type: "bool", default: true, section: "Leave type" },
        { name: "carry_forward", type: "bool", default: false, section: "Leave type" },
        { name: "include_holidays", type: "bool", default: false, section: "Leave type" },
        { name: "is_active", type: "bool", default: true, section: "Leave type" },
      ],
    },
  },
  {
    id: "leave-type-update",
    group: "Leaves",
    label: "Update leave type",
    method: "PATCH",
    path: "/api/v1/integrations/erp/leaves/types/{type_id}",
    scope: "leave-master:write",
    pathParams: [{ name: "type_id", sample: "1", lookup: "leaveTypes" }],
    body: {
      shape: "object",
      fields: [
        { name: "name", type: "text", section: "Leave type" },
        { name: "code", type: "text", section: "Leave type" },
        { name: "is_paid", type: "bool", section: "Leave type" },
        { name: "annual_allocation", type: "int", section: "Leave type" },
        { name: "max_consecutive_days", type: "int", section: "Leave type" },
        { name: "requires_approval", type: "bool", section: "Leave type" },
        { name: "carry_forward", type: "bool", section: "Leave type" },
        { name: "include_holidays", type: "bool", section: "Leave type" },
        { name: "is_active", type: "bool", section: "Leave type" },
      ],
    },
  },
];

