const BASE = '/api/v1'

export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${path}: ${res.status} ${text}`)
  }
  return res.json()
}

// ---- Types ----

export type CauseType = 'timing' | 'concurrency' | 'environment' | 'state_leakage' | 'unknown'

export interface DashboardStats {
  total_repos: number
  total_test_runs: number
  total_flaky_tests: number
  active_flaky_tests: number
  fixes_proposed: number
  fixes_accepted: number
  fixes_rejected: number
  acceptance_rate: number
  cause_breakdown: Record<CauseType, number>
  top_flaky_tests: FlakyTestSummary[]
}

export interface FlakyTestSummary {
  id: number
  repo: string
  test_name: string
  test_file: string | null
  flakiness_score: number
  total_runs: number
  failed_runs: number
  pass_rate: number | null
  is_active: boolean
  first_detected_at: string
  last_seen_at: string | null
  last_analyzed_at: string | null
  primary_cause: CauseType | null
  cause_confidence: number | null
  fix_count: number
}

export interface FlakyTestDetail extends FlakyTestSummary {
  repo_id: number
  recent_runs: TestRun[]
}

export interface TestRun {
  id: number
  status: 'passed' | 'failed' | 'error' | 'skipped'
  duration_ms: number | null
  branch: string | null
  commit_sha: string | null
  error_message: string | null
  created_at: string
}

export interface FixProposal {
  id: number
  flaky_test_id: number
  status: 'pending' | 'synthesizing' | 'proposed' | 'accepted' | 'rejected' | 'applied'
  root_cause: CauseType | null
  patch_diff: string | null
  explanation: string | null
  affected_files: string[] | null
  confidence: number | null
  pr_url: string | null
  pr_number: number | null
  feedback_accepted: boolean | null
  llm_model: string | null
  created_at: string
  test_name: string
  repo: string
}

export interface Analysis {
  id: number
  flaky_test_id: number
  primary_cause: CauseType
  confidence: number
  secondary_causes: { cause: CauseType; confidence: number }[] | null
  evidence: Record<string, unknown> | null
  classifier_version: string
  created_at: string
  test_name: string
  repo: string
}

export interface TrendPoint {
  day: string
  total_runs: number
  failed_runs: number
  unique_tests: number
}

// ---- API calls ----

export const api = {
  stats: () => apiFetch<DashboardStats>('/dashboard/stats'),
  trends: (days = 30) => apiFetch<{ days: number; data: TrendPoint[] }>(`/dashboard/trends?days=${days}`),
  fixStats: () => apiFetch<{ by_status: { status: string; count: number }[]; by_cause: { root_cause: string; total: number; accepted: number; rejected: number; avg_confidence: number }[] }>('/dashboard/fix-stats'),

  flakyTests: (params?: { repo?: string; cause?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.repo) q.set('repo', params.repo)
    if (params?.cause) q.set('cause', params.cause)
    if (params?.limit) q.set('limit', String(params.limit))
    if (params?.offset) q.set('offset', String(params.offset))
    return apiFetch<{ total: number; items: FlakyTestSummary[] }>(`/flaky-tests?${q}`)
  },

  flakyTest: (id: number) => apiFetch<FlakyTestDetail>(`/flaky-tests/${id}`),

  fixes: (params?: { status?: string; flaky_test_id?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.flaky_test_id) q.set('flaky_test_id', String(params.flaky_test_id))
    if (params?.limit) q.set('limit', String(params.limit))
    return apiFetch<{ total: number; items: FixProposal[] }>(`/fixes?${q}`)
  },

  fix: (id: number) => apiFetch<FixProposal>(`/fixes/${id}`),

  feedback: (fixId: number, accepted: boolean, note?: string) =>
    apiFetch(`/fixes/${fixId}/feedback?accepted=${accepted}${note ? `&note=${encodeURIComponent(note)}` : ''}`, { method: 'POST' }),

  triggerFix: (flakyTestId: number) =>
    apiFetch(`/fixes/trigger/${flakyTestId}`, { method: 'POST' }),

  analyses: (flakyTestId?: number) => {
    const q = flakyTestId ? `?flaky_test_id=${flakyTestId}` : ''
    return apiFetch<{ items: Analysis[] }>(`/analyses${q}`)
  },

  repositories: () => apiFetch<{ items: { id: number; full_name: string; flaky_test_count: number; total_runs: number }[] }>('/repositories'),

  ingestEvent: (event: Record<string, unknown>) =>
    apiFetch('/events/ingest', { method: 'POST', body: JSON.stringify(event) }),
}