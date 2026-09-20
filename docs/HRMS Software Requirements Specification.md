# Software Requirements Specification (SRS) 

Human Resource Management System (HRMS) 

**Version:** 1.0 

**Target Industry:** Indian Manufacturing Companies **Frontend:** Nuxt 3 / Nuxt UI **Backend:** FastAPI / Python **Database:** PostgreSQL **Architecture:** Web-based, API-driven, role-based multi-unit HRMS 

# 1. Purpose 

The purpose of this system is to provide a centralized Human Resource Management System for manufacturing organizations having multiple units, departments, shifts, and employees. 

The system will primarily manage: 

- Employee attendance 

- Shift assignments 

- Overtime 

- Leave management 

- Attendance discrepancies 

- Department-level workforce monitoring 

- Unit-level HR monitoring 

- Salary and overtime cost reporting 

- Employee attendance/leave dashboards 

- Approval workflows 

- Role-Based Access Control (RBAC) 

- Audit trails 

The system is intentionally designed as a **focused HRMS** , rather than a complete enterprise HR/payroll/ERP system. 

# 2. Business Hierarchy 

The organization shall follow the hierarchy: 

Organization / Company │ ├── Unit 1 ││ │├── Department A ││├── Employee 1 ││├── Employee 2 ││└── Employee N ││ │├── Department B ││└── Employees ││ │└── HR Team │ ├── Unit 2 │├── Department A │├── Department B │└── HR Team │ └── Unit N 

### Important Business Rule 

Each Unit shall have its own HR personnel/team. 

Therefore: 

- Unit HR shall only access employees belonging to their Unit. 

- Department Heads shall only access employees within their Department. 

- Employees shall normally access only their own records. 

- Organization-level administrators may have cross-unit access. 

- Permissions shall be determined by RBAC + organizational scope. 

# 3. Scope 

## 3.1 In Scope 

### Employee 

- Personal HR profile 

- Attendance summary 

- Daily attendance history 

- Punch-in/punch-out information 

- Current shift 

- Past and upcoming shifts 

- Leave balance 

- Leave application 

- Leave history 

- Leave approval status 

- Overtime summary 

- Attendance discrepancy reporting 

- Missed punch correction request 

- Attendance complaint/dispute 

- Notifications 

### Department Head 

- Department employee list 

- Department attendance summary 

- Employee attendance details 

- Leave approval 

- Overtime summary 

- Department salary cost 

- Attendance trends 

- Leave trends 

- Overtime trends 

### Unit HR 

- Unit employee management 

- Unit attendance dashboard 

- Department-wise attendance 

- Department-wise salary cost 

- Overtime cost 

- Miss-punch reports 

- Attendance discrepancy management 

- Attendance correction approval 

- Leave administration 

- Employee records 

- Shift management 

- Unit reports 

### Organization Administration 

- Organization management 

- Unit management 

- Department management 

- Employee management 

- Dynamic RBAC 

- Role assignment 

- Permission management 

- Cross-unit reports 

- System configuration 

- Audit logs 

# 4. Out of Scope 

To prevent unnecessary scope expansion, the following should NOT be part of the initial version: 

- Full payroll processing 

- Income-tax calculation 

- PF/ESI payroll processing 

- Recruitment/ATS 

- Performance management 

- Employee appraisal system 

- Learning management 

- Expense management 

- Travel management 

- Asset management 

- Advanced workforce planning 

- Full accounting 

- Biometric device administration platform 

- Complex AI-based HR analytics 

The system may expose **salary and overtime cost information** for reporting, without becoming a complete payroll system. 

# 5. User Roles 

The system shall support dynamically configurable roles. 

Predefined roles should be provided initially, but administrators must be able to create additional roles. 

Recommended initial roles: 

|Role|Scope|
|---|---|
|SUPER_ADMIN|Entire organization|
|ORG_ADMIN|Organization|
|UNIT_ADMIN|Specifc Unit|
|UNIT_HR|Specifc Unit|
|DEPARTMENT_HEAD|Specifc Department|
|HR_MANAGER|Assigned Units|
|EMPLOYEE|Own records|
|ATTENDANCE_ADMIN|Assigned Unit/Units|
|AUDITOR|Read-only assigned scope|



These are **templates** , not hard-coded restrictions. 

# 6. Dynamic RBAC 

## 6.1 Requirements 

RBAC shall be permission-based rather than role-name-based. 

Example permissions: 

employee.view_self employee.view employee.create employee.update employee.deactivate 

attendance.view_self attendance.view_department attendance.view_unit attendance.correct attendance.dispute attendance.approve_correction 

leave.apply leave.view_self leave.approve leave.reject 

leave.cancel leave.manage 

shift.view_self shift.assign shift.update 

overtime.view_self overtime.view_department overtime.approve 

salary_cost.view_department salary_cost.view_unit 

reports.attendance reports.leave reports.overtime reports.salary_cost 

rbac.role.create rbac.role.update rbac.role.assign 

audit.view system.configuration 

## 6.2 Role Assignment 

A user may have: 

User ├── Role ├── Organizational Scope │ ├── Organization │ ├── Unit │ └── Department 

Example: 

Raj Role: DEPARTMENT_HEAD Department: Production Unit: Ludhiana Unit 

Raj must not be able to view attendance of another department. 

# 7. Least Privilege Security Model 

The application shall follow: 

Deny by default; grant only required permissions. 

Examples: 

### Employee 

Can: 

- View own attendance 

- View own leave 

- Apply leave 

- Request attendance correction 

- View own overtime 

- View own shifts 

#### Cannot: 

- View another employee’s salary 

- Approve leave 

- Modify attendance directly 

- View organization-wide reports 

### Department Head 

#### Can: 

- View department employees 

- View department attendance 

- Approve department employee leave 

- View department overtime 

#### Cannot: 

- Access another department 

- Modify employee salary 

- Modify organization configuration 

### Unit HR 

Can: 

- Manage employees within Unit 

- Review attendance 

- Process attendance corrections 

- Manage leave configuration 

- View unit salary/overtime reports 

Cannot: 

- Access another Unit unless explicitly assigned. 

# 8. Employee Management 

Each employee shall have a unique employee record. 

## Required Employee Information 

### Identity 

- Employee ID 

- Employee code 

- Full name 

- Date of joining 

- Employment status 

- Employment type 

### Organization 

- Organization 

- Unit 

- Department 

- Designation 

- Reporting manager 

- Department Head 

- Assigned HR 

### Attendance 

- Attendance ID / biometric identifier where applicable 

- Attendance source 

- Shift assignment 

- Weekly-off configuration 

### Cost Information 

- Salary/basic salary or configurable salary-cost field 

- Overtime eligibility 

- Overtime rate/configuration 

Sensitive salary information must have separate permissions. 

# 9. Employee Dashboard 

The employee dashboard shall provide a summarized view. 

## Dashboard Cards 

Today's Attendance Present / Absent / On Leave / Holiday 

Current Shift 09:00 AM – 06:00 PM 

Monthly Attendance Present: 22 Absent: 1 Leave: 2 Holiday: 5 

Overtime This Month: 18.5 Hours 

Leave Balance Casual: 4 Sick: 6 Earned: 8 

Pending Requests Leave: 1 Attendance Correction: 1 

# 10. Attendance Management 

Attendance shall be recorded using available attendance sources such as: 

- Biometric device 

- Machine/device integration 

- Manual HR entry 

- Imported attendance data 

- API integration 

The architecture should keep the **attendance source independent from the HRMS business logic** . 

# 11. Attendance Status 

The system should support configurable attendance statuses. 

Minimum statuses: 

PRESENT ABSENT ON_LEAVE HOLIDAY WEEKLY_OFF HALF_DAY LATE EARLY_EXIT MISSED_PUNCH ATTENDANCE_PENDING 

A single day may also have multiple attendance attributes. 

Example: 

14-Sep-2026 

Status: PRESENT Punch In: 08:57 Punch Out: 18:32 Shift: General Late: No Overtime: 00:32 

# 12. Attendance History 

Employees shall be able to view their attendance by: 

- Day 

- Week 

- Month 

- Date range 

Example: 

|Date|Shift|In|Out|Status|OT|
|---|---|---|---|---|---|
|01 Sep|General|08:58|18:10|Present|00:10|
|02 Sep|General|09:12|—|Missed|—|
|||||Punch||
|03 Sep|General|—|—|Leave|—|



# 13. Attendance Discrepancy Management 

The system shall automatically identify common attendance discrepancies. 

## Examples 

### Case 1 – Punch In Without Punch Out 

Punch In: 08:57 Punch Out: NULL 

Status: MISSED_PUNCH 

### Case 2 – Punch Out Without Punch In 

Punch In: NULL Punch Out: 18:05 

Status: MISSED_PUNCH 

### Case 3 – Multiple Punches 

08:55 IN 12:30 OUT 13:05 IN 18:10 OUT 

System should process the punches according to configured attendance rules. 

Case 4 – Late Arrival 

Shift Start: 09:00 Punch In: 09:17 

Late: TRUE Late Duration: 17 minutes 

Case 5 – Early Departure 

Shift End: 18:00 Punch Out: 17:20 Early Exit: TRUE 

# 14. Attendance Correction / Dispute Workflow 

Employees shall NOT directly modify attendance. 

Instead: 

Employee │ Submit correction request│ ▼ Attendance Discrepancy │ ▼ Department Head / Authorized Approver │ ├── Approve │ └── Reject │ ▼ Attendance Updated 

Each correction must record: 

- Employee 

- Attendance date 

- Existing punches 

- Requested punches 

- Reason 

- Employee comments 

- Approver 

- Approval status 

- Approval timestamp 

- Rejection reason, if applicable 

Original attendance data should never be silently overwritten. 

# 15. Attendance Audit Trail 

For every attendance modification: 

Old Value ↓ Change ↓ New Value ↓ Changed By ↓ Timestamp ↓ Reason 

This is especially important for manufacturing environments and HR audits. 

# 16. Shift Management 

The system shall support multiple shifts. 

Example: 

General Shift 09:00 – 18:00 

Morning Shift 06:00 – 14:00 

Evening Shift 

##### 14:00 – 22:00 

Night Shift 22:00 – 06:00 

Shift configuration should support: 

- Shift name 

- Start time 

- End time 

- Grace period 

- Break duration 

- Working hours 

- Overtime eligibility 

- Weekly-off rules 

- Cross-midnight shifts 

# 17. Employee Shift View 

Employees should see: 

Current Shift 

Current Shift Morning Shift 

06:00 AM – 02:00 PM 

Upcoming Shifts 

15 Sep → Morning 16 Sep → Morning 17 Sep → Evening 18 Sep → Evening 

Previous Shifts 

Employees should be able to see historical assignments. 

# 18. Shift Assignment 

Authorized HR/administrative users shall be able to assign: 

- Individual shift 

- Shift for department 

- Shift for employee group 

Every shift assignment should have: 

Employee Shift Effective From Effective To Assigned By Created At 

Historical assignments must be preserved. 

# 19. Overtime Management 

The system shall calculate/display overtime based on configurable organization/unit rules. Examples: 

Actual Working Time 

- Scheduled Working Time = Potential Overtime 

However, the system should distinguish between: 

- Calculated overtime 

- Approved overtime 

This prevents automatically treating every extra minute as payable overtime. 

# 20. Overtime Workflow 

Recommended workflow: 

Attendance 

│ ▼ Potential OT 

│ ▼ OT Validation / Approval │ ▼ Approved OT │ ▼ OT Cost Report 

The system should support configurable rules for: 

- Minimum overtime duration 

- Rounding 

- Eligibility 

- Approval requirement 

- Overtime rate 

Because overtime rules can vary between organizations, they should be configurable rather than hard-coded. 

# 21. Leave Management 

The system shall support configurable leave types. 

Initial leave types: 

- Casual Leave 

- Sick Leave 

- Earned Leave 

- Maternity Leave 

- Paternity Leave 

- Compensatory Leave 

Additional leave types may be created later by authorized HR users. 

# 22. Leave Configuration 

Each leave type should support: 

Leave Name Code Description Paid / Unpaid Annual Allocation Carry Forward Maximum Consecutive Days Requires Approval Requires Document Applicable Employee Types Applicable Units Active / Inactive 

The system should avoid hard-coding statutory leave quantities because policies can vary by establishment, state, employee category, and applicable law. 

# 23. Leave Application 

Employee workflow: 

Employee │ ▼ Select Leave Type │ ▼ Select From / To Date │ ▼ Enter Reason │ ▼ Submit │ ▼ Approver │ ├── Approve └── Reject 

The system should validate: 

- Leave balance 

- Date conflicts 

- Existing approved leave 

- Holidays 

- Weekly offs 

- Minimum/maximum duration 

- Applicable leave rules 

# 24. Leave Status 

Supported statuses: 

DRAFT PENDING APPROVED REJECTED CANCELLED WITHDRAWN 

The employee shall be able to view complete leave history. 

# 25. Leave Dashboard 

Employee: 

Casual Leave Available: 5 Pending: 1 Used: 3 

Sick Leave Available: 7 Used: 2 

Earned Leave Available: 10 Used: 4 

History: 

01 Sep – 02 Sep Casual Leave Approved 

10 Sep Sick Leave Rejected Reason: Insufficient balance 

# 26. Leave Approval 

Department Heads shall see: 

Pending Leave Requests 

Employee       Type       Dates       Days -----------------------------------------------EMP001         Casual     15-16 Sep   2 EMP002         Sick       18 Sep      1 

Actions: 

Approve Reject View Details 

Rejection should require a reason. 

# 27. Leave Cancellation 

An employee should be able to request cancellation/withdrawal of leave according to configurable policy. 

Authorized HR users should be able to cancel or modify leave with an audit trail. 

# 28. Department Dashboard 

Department Head dashboard: 

Department: Production 

Employees: 125 

Today Present: 108 Absent: 8 Leave: 6 Weekly Off: 3 

Attendance % 92.3% 

Pending Leave 5 

Overtime Today: 42 hrs Month: 820 hrs 

OT Cost ₹ XXX,XXX 

# 29. Department Attendance Reports 

Department Head should be able to view: 

- Daily attendance 

- Monthly attendance 

- Employee attendance 

- Absent employees 

- Late employees 

- Early exits 

- Missed punches 

- Attendance percentage 

- Leave count 

- Overtime 

# 30. Department Attendance Trends 

Charts should support: 

Daily Trend 

Date → Attendance % 

Monthly Trend 

Month → Attendance % 

Absence Trend 

Date → Number of absent employees 

Overtime Trend 

Date → Overtime hours 

# 31. Department Salary Cost 

Department Heads with the required permission may view aggregated salary cost. 

Example: 

Department: Production 

Employees: 125 

Monthly Salary Cost: ₹XX,XX,XXX Overtime Cost: ₹X,XX,XXX Total Workforce Cost: ₹XX,XX,XXX 

Individual salary visibility should be permission-controlled. 

By default, Department Heads should receive **aggregated cost** , not individual salary information. 

# 32. Unit HR Dashboard 

Unit HR shall have a unit-level dashboard. 

Example: 

Unit: Ludhiana 

Employees: 1,250 

Today's Attendance Present       1,080 Absent           75 On Leave         60 Weekly Off       35 

Attendance Rate: 92.4% 

Miss Punches: 23 Pending Corrections: 11 Pending Leave: 18 

Overtime Today: 320 Hours Monthly OT Cost: ₹XX,XX,XXX 

# 33. Department-Wise Unit Reports 

HR shall be able to compare departments. 

|Depart<br>ment|Employees|Present %|Absent|Leave|OT Hours|Salary<br>Cost|
|---|---|---|---|---|---|---|
|Produc<br>tion|500|93%|20|14|210|₹XX|
|Quality|100|96%|2|3|35|₹XX|
|Mainte|80|91%|5|4|48|₹XX|
|nance|||||||



# 34. HR Miss-Punch Report 

HR shall have a dedicated report: 

Employee Employee ID Department Date 

Shift Punch In Punch Out Discrepancy Type Employee Request Status Approval Status Approver 

Filters: 

- Unit 

- Department 

- Employee 

- Date range 

- Status 

- Discrepancy type 

# 35. Attendance Discrepancy Management 

HR shall have a queue: 

Pending Discrepancies 

EMP001 15 Sep Punch Out Missing Employee Requested Correction 

EMP005 16 Sep Punch In Missing Awaiting Employee Response 

HR can: 

- Review 

- Approve 

- Reject 

- Request clarification 

- Correct attendance if authorized 

Every action must be audited. 

# 36. Notifications 

The system should provide notifications for important events. 

### Employee 

- Leave submitted 

- Leave approved 

- Leave rejected 

- Attendance discrepancy 

- Correction approved/rejected 

- Shift changed 

- Overtime approved 

### Manager 

- New leave request 

- Attendance correction request 

- Pending approvals 

### HR 

- Pending discrepancies 

- Excessive absenteeism alerts, if configured 

- Pending approvals 

Initial implementation may use: 

- In-app notifications 

- Email 

SMS/WhatsApp should not be part of MVP unless specifically required. 

# 37. Holiday and Weekly-Off Management 

This is an important missing component. 

The system should support: 

### Holidays 

- Unit-specific holidays 

- Organization holidays 

- Date 

- Holiday name 

- Applicable employee groups 

Weekly Off 

Support configurations such as: 

Sunday Saturday + Sunday Rotational Weekly Off Department-specific weekly off 

This is particularly important for manufacturing environments with multiple shifts. 

# 38. Attendance Calendar 

Employees should have a monthly calendar. 

Example: 

September 2026 

Mon Tue Wed Thu Fri Sat Sun 1   2   3   4   5   6   7 P   P   P   L   P   WO  WO 8   9  10  11  12  13  14 P   P  MP   P   P   WO  WO 

Where: 

P  = Present A  = Absent L  = Leave WO = Weekly Off H  = Holiday MP = Missed Punch 

# 39. Employee Self-Service 

Employees should be able to manage their own non-sensitive HR interactions. 

#### MVP: 

- View profile 

- View attendance 

- View shifts 

- Apply leave 

- View leave balance 

- View leave history 

- View overtime 

- Raise attendance discrepancy 

- View notifications 

Employees should not be allowed to directly modify system-generated attendance records. 

# 40. Reporting 

#### Minimum reports: 

### Attendance 

- Daily attendance 

- Monthly attendance 

- Employee attendance 

- Department attendance 

- Unit attendance 

- Absentee report 

- Late-coming report 

- Early-exit report 

- Miss-punch report 

### Leave 

- Leave balance 

- Leave utilization 

- Pending leave 

- Department leave 

- Unit leave 

- Leave type utilization 

### Overtime 

- Employee overtime 

- Department overtime 

- Unit overtime 

- Approved vs unapproved overtime 

- Overtime cost 

### Workforce Cost 

- Department salary cost 

- Unit salary cost 

- Overtime cost 

- Total workforce cost 

Reports should support: 

- Date filters 

- Unit 

- Department 

- Employee 

- CSV export 

- PDF export where required 

# 41. Search and Filtering 

The application should provide centralized search where authorized. 

Search by: 

- Employee ID 

- Employee name 

- Department 

- Designation 

- Unit 

- Attendance status 

Large tables should support: 

- Pagination 

- Sorting 

- Filtering 

- Date ranges 

- Server-side searching 

Filtering must respect RBAC. 

# 42. Audit Logging 

An audit log is mandatory for sensitive HR operations. 

Audit events should include: 

USER_LOGIN USER_LOGOUT 

EMPLOYEE_CREATED EMPLOYEE_UPDATED EMPLOYEE_DEACTIVATED 

ATTENDANCE_CORRECTED ATTENDANCE_CORRECTION_APPROVED ATTENDANCE_CORRECTION_REJECTED 

LEAVE_CREATED LEAVE_APPROVED LEAVE_REJECTED LEAVE_CANCELLED 

SHIFT_ASSIGNED SHIFT_CHANGED 

ROLE_CREATED ROLE_UPDATED ROLE_ASSIGNED 

PERMISSION_CHANGED 

Audit record: 

ID Actor User Action Entity Type Entity ID Old Value New Value Reason 

IP Address Timestamp 

Audit records should not be editable by normal users. 

# 43. Employee Lifecycle 

Employee status should be maintained. 

Minimum statuses: 

ACTIVE INACTIVE ON_NOTICE SUSPENDED TERMINATED RESIGNED 

For MVP, employee deletion should generally be avoided. 

Use **soft deactivation** instead. 

This preserves historical attendance, leave and cost records. 

# 44. Data Retention 

HR records such as: 

- Attendance 

- Leave 

- Overtime 

- Corrections 

- Approvals 

- Audit logs 

should be retained according to the organization’s retention policy and applicable legal requirements. 

The application should provide configurable retention policies rather than hard-coding a universal period. 

# 45. Indian Manufacturing Considerations 

The system should be designed to support Indian manufacturing organizations without hard-coding a particular company’s HR policy. 

Important configurable areas: 

- Multiple shifts 

- Night shifts 

- Rotational shifts 

- Weekly offs 

- Unit-specific holidays 

- Overtime rules 

- Leave policies 

- Employee categories 

- Contractor/permanent employee classification if required 

- Attendance grace period 

- Late-coming rules 

- Early-exit rules 

- Salary cost 

- Unit/department hierarchy 

Statutory rules should be implemented as **configurable policy modules** and reviewed against the organization’s applicable labour-law requirements rather than assuming one universal rule for every Indian establishment. 

# 46. Data Model – High-Level 

Recommended core PostgreSQL entities: 

organizations units departments 

employees employee_employment_details 

users roles permissions role_permissions 

user_roles role_scopes 

shifts shift_assignments 

attendance_records attendance_punches attendance_discrepancies attendance_correction_requests 

leave_types leave_policies leave_balances leave_applications overtime_records overtime_approvals holidays weekly_off_rules notifications audit_logs 

# 47. Recommended Attendance Data Model 

Attendance should be separated from raw punches. 

attendance_punches ------------------- 

id employee_id punch_time punch_type source device_id created_at Example: 

08:58 → IN 18:12 → OUT 

Then: 

attendance_records -----------------id employee_id attendance_date shift_id status first_in last_out worked_minutes overtime_minutes late_minutes early_exit_minutes 

This separation is important because raw biometric/device data should be preserved independently from processed attendance. 

# 48. Multi-Unit Data Isolation 

Every business record should be associated with the appropriate organizational scope. 

For example: 

Employee ↓ Department ↓ Unit ↓ Organization 

The backend must enforce this scope. 

Frontend hiding a menu is NOT sufficient security. 

For example: GET /api/employees 

must automatically apply the authenticated user’s permitted scope. 

A Unit HR user must not be able to bypass the UI and request another Unit’s employees directly through the API. 

# 49. API Architecture 

FastAPI shall expose REST APIs. 

Example: 

/api/v1/auth /api/v1/users /api/v1/roles /api/v1/permissions 

/api/v1/organizations /api/v1/units /api/v1/departments /api/v1/employees 

/api/v1/attendance /api/v1/attendance/discrepancies /api/v1/attendance/corrections 

/api/v1/shifts /api/v1/shift-assignments 

/api/v1/leaves /api/v1/leave-balances 

/api/v1/overtime 

/api/v1/reports 

/api/v1/notifications /api/v1/audit-logs 

# 50. Authentication 

Authentication shall be handled by the backend. 

Recommended: 

Nuxt Frontend │ ▼ FastAPI Authentication │ ▼ Authenticated Session / Token │ ▼ RBAC Authorization │ ▼ Business API 

The frontend should never be trusted to enforce authorization. 

The backend must enforce: 

Authentication + Role + Permission + Organization Scope 

# 51. Authorization Example 

Request: 

GET /api/v1/attendance/department/15 

Backend checks: 

Is user authenticated? ↓ Does user have attendance.view_department? ↓ Is Department 15 within user's permitted scope? ↓ 

YES → Return data NO  → 403 Forbidden 

# 52. Database Security 

PostgreSQL should use a dedicated application database user. 

Do not use the PostgreSQL superuser for the application. 

Recommended: 

PostgreSQL Server 

Database: hrms 

Users: 

hrms_app → application access 

hrms_readonly 

→ reporting/read-only operations where required 

postgres 

- → administrative use only 

Database credentials must be stored in environment/secret management and never committed to source control. 

# 53. Frontend Architecture 

Nuxt application structure: 

app/ ├── pages/ │├── login │├── dashboard │├── attendance │├── leaves │├── shifts 

│├── overtime │├── employees │├── reports │├── settings │└── admin │ ├── components/ │ ├── composables/ │ ├── middleware/ │ ├── layouts/ │ └── stores/ 

Navigation should be permission-aware. 

However, permission-based UI is only for user experience. Backend authorization remains mandatory. 

# 54. Backend Architecture 

Recommended FastAPI structure: 

app/ ├── main.py │ ├── api/ │└── v1/ │ ├── core/ │├── config.py │├── security.py │└── permissions.py │ ├── models/ │ ├── schemas/ │ ├── services/ │├── attendance/ 

│├── leave/ │├── overtime/ │├── employee/ │└── reporting/ │ ├── repositories/ │ ├── db/ │ └── audit/ 

Business rules should be kept in service/domain layers rather than putting all logic inside API route handlers. 

55. Leave Workflow Employee │ ▼ Create Leave Application │ ▼ System Validation │ ├── Insufficient Balance → Reject submission │ ├── Date Conflict → Reject submission │ └── Valid │ ▼ PENDING │ ▼ Department Head │ ├───────────────┐ ▼ ▼ APPROVED         REJECTED │ │ ▼ ▼ 

Balance          Reason Updated          Required 

# 56. Attendance Correction Workflow 

Attendance System │ ▼ Discrepancy Detected │ ▼ Employee Notification │ ▼ Employee Submits Correction │ ▼ Approver │ ┌───┴────┐ ▼ ▼ Approve   Reject │ │ ▼ ▼ Update    Record Attendance Reason │ ▼ Audit Log 

# 57. Overtime Workflow 

Attendance │ ▼ Calculate Potential OT │ ▼ OT Validation 

│ ▼ Approval │ ┌──┴───┐ ▼ ▼ Yes     No │ │ ▼ ▼ Approved Not Payable/Unapproved OT │ ▼ Cost Reporting 

# 58. Dashboard Design Principles 

The application should be designed for operational HR use. Prioritize: 

- Clear status indicators 

- Tables 

- Filters 

- Search 

- Date range 

- Drill-down 

- Approval queues 

- Action buttons 

- Export 

Avoid excessive dashboards with unnecessary charts. 

Charts should answer practical questions such as: 

How many employees are absent today? Which department has the highest overtime? How many attendance discrepancies are pending? What is this month’s attendance trend? 

# 59. Security Requirements 

Minimum requirements: 

- Secure authentication 

- Password hashing 

- Session/token security 

- RBAC 

- Permission checks 

- Organizational scope checks 

- HTTPS in production 

- Input validation 

- SQL injection protection through parameterized ORM/database access 

- Rate limiting for authentication endpoints 

- Audit logging 

- Secure password reset 

- Account activation/deactivation 

- Session expiration 

- Secure HTTP headers 

- Secrets outside source control 

Sensitive information such as salary should require explicit permissions. 

# 60. Password and Account Management 

The system should support: 

- Account activation 

- Account deactivation 

- Password reset 

- Password change 

- Failed login protection 

- Session management 

MFA/OTP may be introduced later but should not block the MVP architecture. 

The authentication system should be designed so MFA can be added later. 

# 61. Notifications and Approval SLA 

The system should maintain notification state: 

UNREAD READ 

For approvals, the system should record: 

Created At Assigned At Actioned At Actioned By 

This allows future reporting on pending approval duration. 

# 62. Performance Requirements 

The backend should use: 

- Pagination 

- Database indexes 

- Server-side filtering 

- Aggregated queries for dashboards 

- Proper PostgreSQL indexes 

- Connection pooling 

Large reports should not load thousands of records into the browser unnecessarily. 

Example: 

GET /attendance?page=1&page_size=50 

rather than loading the entire year’s attendance data. 

# 63. Availability and Reliability 

The system should: 

- Handle database connection failures gracefully 

- Log application errors 

- Provide health-check endpoints 

- Support database backups 

- Avoid data loss during attendance imports 

- Maintain transactional integrity for leave and attendance updates 

Recommended endpoints: 

/health /ready 

# 64. Audit and Data Integrity Principles 

Important HR records should be treated as historical records. 

The system should generally avoid: 

DELETE attendance DELETE approved leave DELETE audit log 

Instead use: 

status inactive cancelled reversed corrected 

This preserves historical information. 

# 65. Important Business Rules 

Rule 1 

Employee cannot approve their own leave. 

Rule 2 

Employee cannot approve their own attendance correction. 

Rule 3 

Department Head cannot access employees outside their authorized department. 

Rule 4 

Unit HR cannot access another Unit unless explicitly authorized. 

Rule 5 

Salary information requires separate permission. 

### Rule 6 

Attendance corrections must preserve original data. 

### Rule 7 

Rejected requests must contain a reason. 

Rule 8 

Deactivated employees retain historical records. 

### Rule 9 

Approved leave must affect leave balance according to the configured policy. 

Rule 10 

Potential overtime and approved overtime must be distinguishable. 

Rule 11 

All sensitive changes must generate audit records. 

Rule 12 

Backend authorization must enforce all permissions and scopes. 

# 66. MVP Feature Prioritization 

P0 – Mandatory 

These should be implemented first. 

Organization 

- Organization 

- Units 

- Departments 

####  Employees 

### Authentication 

- Login 

- Logout 

- Password management 

- Account activation/deactivation 

### RBAC 

- Roles 

- Permissions 

- Role assignment 

- Scope assignment 

### Attendance 

- Attendance records 

- Punches 

- Attendance calendar 

- Daily/monthly summary 

- Missed punch detection 

- Attendance discrepancy 

- Correction workflow 

### Shifts 

- Shift creation 

- Shift assignment 

- Current shift 

- Historical shift 

- Upcoming shift 

### Leave 

- Leave types 

- Leave balance 

- Leave application 

- Leave approval 

- Leave rejection 

- Leave history 

### Overtime 

- OT calculation/display 

- OT approval 

- OT summary 

### Reporting 

- Employee 

- Department 

- Unit 

- Attendance 

- Leave 

- Overtime 

- Salary cost 

### Audit 

- Audit logging 

# 67. P1 – Important but Can Follow MVP 

- Email notifications 

- Advanced attendance trends 

- Holiday calendar 

- Rotational weekly offs 

- CSV export 

- PDF reports 

- Bulk employee import 

- Bulk shift assignment 

- Bulk attendance import 

- Advanced filtering 

- Approval reminders 

# 68. P2 – Future 

Potential future modules: 

- MFA 

- Biometric integrations 

- Payroll integration 

- PF/ESI integration 

- Recruitment 

- Performance management 

- Employee documents 

- Mobile application 

- WhatsApp notifications 

- Advanced workforce analytics 

These should not be allowed to complicate the initial architecture. 

# 69. Recommended MVP Navigation 

## Employee 

##### Dashboard 

Attendance 

├── My Attendance 

├── Attendance Calendar └── Discrepancies 

Leave 

├── Apply Leave 

├── Leave Balance └── Leave History 

##### Overtime 

└── My Overtime 

##### Shifts 

└── My Shifts 

Notifications Profile 

## Department Head 

Dashboard 

Employees 

##### Attendance 

├── Department Attendance ├── Discrepancies └── Trends 

Leave 

├── Pending Approvals └── Leave History 

Overtime 

Reports 

## Unit HR 

Dashboard 

Employees 

Attendance 

├── Unit Attendance ├── Department Attendance ├── Miss Punch └── Corrections 

Leave 

├── Applications ├── Balances └── Reports 

Shifts 

Overtime 

Reports 

Unit Settings 

## Organization Admin 

Dashboard 

Organization 

├── Units ├── Departments └── Employees 

##### Access Control 

├── Users ├── Roles 

##### └── Permissions 

Reports 

Audit Logs 

System Configuration 

# 70. High-Level System Flow 



<!-- Start of picture text -->
┌─────────────────┐<br>                       Organization  │ │<br>└────────┬────────┘<br>│<br>┌────────▼────────┐<br>                          Units      │ │<br>└────────┬────────┘<br>│<br>┌────────▼────────┐<br>                       Departments   │ │<br>└────────┬────────┘<br>│<br>┌────────▼────────┐<br>                        Employees    │ │<br>└────────┬────────┘<br>│<br>┌──────────────────┼──────────────────┐<br>│ │ │<br>▼ ▼ ▼<br>     Attendance           Leave             Shifts<br>│ │ │<br>▼ ▼ ▼<br>   Discrepancies         Approval          Assignment<br>│ │<br>└──────────┬───────┘<br>▼<br>                 Overtime<br>│<br>▼<br>                  Reports<br>│<br><!-- End of picture text -->

▼ HR / Management 

# 71. Recommended Technical Architecture 



<!-- Start of picture text -->
┌─────────────────────┐<br>                         Nuxt 3 Web      │ │<br>                          Frontend       │ │<br>└──────────┬──────────┘<br>                                HTTPS│<br>▼<br>┌─────────────────────┐<br>                          FastAPI        │ │<br>                          REST API       │ │<br>└──────────┬──────────┘<br>│<br>┌────────────────┼────────────────┐<br>│ │ │<br>▼ ▼ ▼<br>          Auth/RBAC        HR Services      Reporting<br>│ │ │<br>└────────────────┼────────────────┘<br>▼<br>┌─────────────────────┐<br>                         PostgreSQL      │ │<br>└─────────────────────┘<br><!-- End of picture text -->

External attendance devices can later integrate through: 

Biometric / Attendance Device │ ▼ Integration API │ ▼ Attendance Service │ ▼ PostgreSQL 

# 72. Core Design Principle 

The HRMS should be designed around the following authorization model: 

WHO │ ├── User │ ▼ WHAT CAN THEY DO? │ ├── Permission │ ▼ WHERE CAN THEY DO IT? │ ├── Organization ├── Unit └── Department │ ▼ WHAT DATA CAN THEY SEE? │ ├── Own ├── Department ├── Unit └── Organization 

This is preferable to implementing permissions simply as: 

if role == "HR": allow() 

Instead: 

User → Role → Permissions → Scope → Resource → Action 

This will make the system much easier to maintain when the company creates new roles in the future. 

# 73. Final MVP Definition 

The first production version should answer these questions reliably: 

### Employee 

What is my attendance? Did I miss a punch? What is my current shift? What are my upcoming shifts? How much leave do I have? What leave have I applied for? Was my leave approved? How much overtime did I work? 

Do I have an attendance issue to resolve? 

### Department Head 

Who is present today? Who is absent? Who is on leave? Which employees have attendance discrepancies? Which leave requests need approval? How much overtime is being generated? 

What is my department’s workforce cost? 

### Unit HR 

What is today’s unit attendance? Which department has attendance problems? Which employees have missed punches? Which corrections are pending? What is the leave situation? What is the overtime cost? What is the salary cost by department? 

### Organization Admin 

What is happening across all units? 

Who can access what? 

Which roles exist? 

Which users have which permissions? 

What changes have been made to HR data? 

# 74. Key Recommendation 

The most important architectural decision for this HRMS is to **separate these four concepts** : 

##### 1. Identity 

Who is the user? 

##### 2. Role 

What role has been assigned? 

##### 3. Permission 

What actions can they perform? 

##### 4. Scope 

Which organization/unit/department/data can they access? 

For example: 

User: Amit 

Role: DEPARTMENT_HEAD 

Permissions: attendance.view leave.approve overtime.view 

Scope: Unit = Ludhiana Department = Production 

This provides a clean **least-privilege, multi-unit RBAC model** without creating dozens of hard-coded roles. 

# 75. Conclusion 

The proposed HRMS should remain a focused workforce-management platform centered around: 

#### **Attendance + Shifts + Leave + Overtime + Approvals + Workforce Cost + Reporting + RBAC + Audit** 

The system should be configurable enough for different Indian manufacturing units while avoiding unnecessary payroll, recruitment, performance-management, and ERP functionality. 

The architecture should prioritize: 

1. **Least privilege** 

2. **Unit-level data isolation** 

3. **Configurable roles and permissions** 

4. **Immutable/auditable attendance history** 

5. **Configurable shift and leave policies** 

6. **Approval workflows** 

7. **Clear employee self-service** 

8. **Operational HR dashboards** 

9. **PostgreSQL-backed transactional integrity** 

10. **FastAPI-enforced authorization** 

11. **Nuxt permission-aware UI** 

12. **Future integration capability without overengineering the MVP** 

