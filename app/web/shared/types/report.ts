import type { PaginatedResponse } from './pagination'

export interface AttendanceReportRow { employee_id: number, employee_code: string, employee_name: string, department_name?: string | null, designation_name?: string | null, day_status_map: Record<number, string>, total_present: number, total_absent: number, total_half_day: number, total_leave: number, total_late_minutes: number, total_overtime_minutes: number }
export interface AttendanceMatrix extends PaginatedResponse<AttendanceReportRow> { year: number, month: number, total_days_in_month: number, items: AttendanceReportRow[] }
export interface LeaveSummaryRow { employee_id: number, employee_code: string, employee_name: string, department_name?: string | null, leave_type_name: string, leave_type_code: string, allocated: number, used: number, pending: number, available: number }
export interface LeaveSummary extends PaginatedResponse<LeaveSummaryRow> { breakdown: { leave_type_name: string, allocated: number, used: number, pending: number }[], year: number, items: LeaveSummaryRow[] }
