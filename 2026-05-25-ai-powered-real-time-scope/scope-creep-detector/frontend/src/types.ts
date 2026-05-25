export interface User {
  id: string
  email: string
  full_name: string
  company_name?: string
  hourly_rate: number
  created_at: string
}

export interface Contract {
  id: string
  title: string
  client_name: string
  file_name?: string
  status: 'processing' | 'active' | 'archived' | 'error'
  project_value?: number
  start_date?: string
  end_date?: string
  created_at: string
  clause_count: number
}

export interface Message {
  id: string
  contract_id: string
  source: string
  sender_name?: string
  sender_email?: string
  subject?: string
  content: string
  analyzed: boolean
  created_at: string
}

export type SeverityLevel = 'low' | 'medium' | 'high' | 'critical'
export type ViolationStatus = 'pending' | 'change_order_created' | 'dismissed'
export type ChangeOrderStatus = 'draft' | 'approved' | 'sent' | 'accepted' | 'declined'

export interface CitedClause {
  text: string
  relevance: string
}

export interface Violation {
  id: string
  contract_id: string
  message_id: string
  violation_score: number
  severity: SeverityLevel
  summary: string
  out_of_scope_work: string
  cited_clauses?: CitedClause[]
  estimated_hours?: number
  estimated_cost?: number
  status: ViolationStatus
  created_at: string
}

export interface ChangeOrder {
  id: string
  violation_id: string
  title: string
  description: string
  scope_addition: string
  estimated_hours: number
  hourly_rate: number
  total_cost: number
  terms?: string
  pdf_path?: string
  status: ChangeOrderStatus
  created_at: string
}

export interface DashboardStats {
  total_contracts: number
  active_contracts: number
  total_violations: number
  pending_violations: number
  total_change_orders: number
  approved_change_orders: number
  recovered_revenue: number
  potential_revenue: number
  monthly_recovered: number
}

export interface WSMessage {
  type: string
  data: Record<string, unknown>
}