import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE || ''

export const api = axios.create({
  baseURL: BASE,
  timeout: 15000,
})

export interface Workflow {
  id: string
  name: string
  description?: string
  expected_tools?: string[]
  created_at: string
  is_active: boolean
}

export interface DriftTimeSeriesPoint {
  timestamp: string
  run_id: string
  composite_score: number
  structural_score?: number
  semantic_score?: number
  distributional_score?: number
  severity?: string
  alert_triggered: boolean
}

export interface DriftScoreDetail {
  id: string
  run_id: string
  workflow_id: string
  ingested_at: string
  structural_score?: number
  semantic_score?: number
  distributional_score?: number
  composite_score?: number
  alert_triggered: boolean
  severity?: string
  structural_detail?: Record<string, unknown>
  semantic_detail?: Record<string, unknown>
  distributional_detail?: Record<string, unknown>
  explanation?: string
}

export interface WorkflowSummary {
  workflow_id: string
  workflow_name: string
  recent_composite_score?: number
  trend: string
  alert_count_24h: number
  baseline_count: number
  trace_count_24h: number
  last_alert_at?: string
}

export interface TraceRecord {
  run_id: string
  workflow_id: string
  start_time: number
  step_count?: number
  tool_sequence?: string[]
  processed: boolean
  composite_score?: number
  severity?: string
  alert_triggered: boolean
}

export const getWorkflows = () =>
  api.get<Workflow[]>('/api/v1/workflows').then(r => r.data)

export const getWorkflowSummary = (id: string) =>
  api.get<WorkflowSummary>(`/api/v1/workflows/${id}/summary`).then(r => r.data)

export const getDriftTimeseries = (workflowId: string, hours = 24) =>
  api.get<DriftTimeSeriesPoint[]>(`/api/v1/drift/timeseries/${workflowId}`, {
    params: { hours },
  }).then(r => r.data)

export const getDriftAlerts = (workflowId: string, hours = 24) =>
  api.get<DriftScoreDetail[]>(`/api/v1/drift/alerts/${workflowId}`, {
    params: { hours },
  }).then(r => r.data)

export const getTraces = (workflowId: string, limit = 50) =>
  api.get<TraceRecord[]>('/api/v1/traces', {
    params: { workflow_id: workflowId, limit },
  }).then(r => r.data)

export const getLatestScore = (workflowId: string) =>
  api.get<DriftScoreDetail | null>(`/api/v1/drift/latest/${workflowId}`)
    .then(r => r.data)
    .catch(() => null)