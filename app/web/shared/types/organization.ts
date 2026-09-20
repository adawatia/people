export interface Organization { id: number, name: string, short_name?: string | null, industry?: string | null, created_at: string }
export interface Department { id: number, unit_id: number, name: string, code?: string | null, is_active: boolean, created_at: string }
export interface Unit { id: number, organization_id: number, name: string, code?: string | null, city?: string | null, is_active: boolean, created_at: string, departments: Department[] }
export interface Designation { id: number, name: string, code?: string | null, description?: string | null, is_active: boolean, created_at: string }
