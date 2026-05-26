import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface ScanRequest {
  code: string
  language?: string
  source: 'ai_assistant' | 'pre_commit' | 'ci_cd' | 'api'
  filename?: string
  metadata?: Record<string, unknown>
}

export interface MatchResult {
  match_id: string
  match_type: string
  similarity_score: number
  license_spdx: string
  license_risk_tier: string
  source_repo?: string
  matched_snippet?: string
}

export interface ScanResult {
  scan_id: string
  status: string
  risk_tier: string
  matches: MatchResult[]
  recommendation: string
  message: string
  created_at: string
  completed_at?: string
}

export interface DashboardStats {
  total_scans: number
  high_risk_count: number
  medium_risk_count: number
  low_risk_count: number
  clean_count: number
  top_licenses: Array<{ license: string; tier: string; count: number }>
  recent_scans: Array<{
    scan_id: string
    filename: string
    language: string
    risk_tier: string
    source: string
    created_at: string
    match_count: number
  }>
  risk_trend: Array<{
    date: string
    high: number
    medium: number
    low: number
    clean: number
    unknown: number
  }>
}

export interface CorpusStats {
  total_snippets: number
  by_risk_tier: Array<{ tier: string; count: number }>
  top_licenses: Array<{ license: string; count: number }>
}

export interface ScanListItem {
  scan_id: string
  status: string
  source: string
  language?: string
  filename?: string
  risk_tier?: string
  match_count: number
  created_at: string
}

export interface RemediationResponse {
  remediation_id: string
  scan_id: string
  original_code: string
  suggested_code?: string
  explanation?: string
  status: string
}

// API functions
export const api = {
  scan: async (req: ScanRequest): Promise<ScanResult> => {
    const { data } = await apiClient.post('/api/v1/scan/sync', req)
    return data
  },

  getScan: async (scanId: string): Promise<ScanResult> => {
    const { data } = await apiClient.get(`/api/v1/scan/${scanId}`)
    return data
  },

  listScans: async (params?: { status?: string; risk_tier?: string; limit?: number }): Promise<ScanListItem[]> => {
    const { data } = await apiClient.get('/api/v1/scans', { params })
    return data
  },

  getDashboard: async (): Promise<DashboardStats> => {
    const { data } = await apiClient.get('/api/v1/dashboard/stats')
    return data
  },

  getCorpusStats: async (): Promise<CorpusStats> => {
    const { data } = await apiClient.get('/api/v1/corpus/stats')
    return data
  },

  remediate: async (scanId: string, matchId?: string): Promise<RemediationResponse> => {
    const { data } = await apiClient.post('/api/v1/remediate', {
      scan_id: scanId,
      match_id: matchId,
    })
    return data
  },

  getHealth: async () => {
    const { data } = await apiClient.get('/api/v1/health')
    return data
  },
}