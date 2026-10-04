export interface Organization {
  id: number
  name: string
  erp_id?: string | null
  short_name?: string | null
  industry?: string | null
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  state?: string | null
  country?: string | null
  postal_code?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
  tax_id?: string | null
  created_at: string
  updated_at?: string
}
export interface Department { id: number, unit_id: number, unit_is_active?: boolean | null, name: string, code?: string | null, is_active: boolean, created_at: string }
export interface Unit { id: number, organization_id: number, name: string, code?: string | null, city?: string | null, is_active: boolean, created_at: string, departments: Department[] }
export interface Designation { id: number, name: string, code?: string | null, description?: string | null, is_active: boolean, created_at: string }
