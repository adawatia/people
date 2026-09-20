export interface Employee {
  id: number
  employee_code: string
  first_name: string
  last_name?: string | null
  full_name?: string | null
  official_email?: string | null
  phone_number?: string | null
  designation_id?: number | null
  designation_name?: string | null
  department_id?: number | null
  department_name?: string | null
  unit_id?: number | null
  unit_name?: string | null
  reporting_manager_name?: string | null
  employment_type: string
  status: string
  date_of_joining?: string | null
  created_at: string
}
export interface EmployeePage { items: Employee[], total: number, page: number, page_size: number, total_pages: number }
export interface EmployeeWorkHistory { id: number, employee_id: number, unit_id?: number | null, department_id?: number | null, designation_id?: number | null, from_date: string, to_date?: string | null, remarks?: string | null, created_at: string }
