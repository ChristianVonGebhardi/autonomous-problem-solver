import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types
export interface Repository {
  id: string
  name: string
  repo_path?: string
  repo_url?: string
  status: 'pending' | 'ingesting' | 'ready' | 'error'
  file_count: number
  commit_count: number
  last_ingested_at?: string
  created_at: string
}

export interface IngestionJob {
  job_id: string
  repo_name: string
  job_type: string
  status: string
  progress: number
  error_message?: string
  celery_state?: { state: string; info: Record<string, unknown> }
  created_at: string
  completed_at?: string
}

export interface QuerySource {
  file_path: string
  chunk_type: string
  name: string
  score: number
  start_line: number
  end_line: number
}

export interface QueryResponse {
  answer: string
  sources: QuerySource[]
  model_used: string
  latency_ms: number
  cached: boolean
  context_chunks_used: number
  repo_name?: string
}

export interface QueryHistory {
  id: string
  question: string
  answer_preview: string
  repo_name?: string
  latency_ms?: number
  created_at: string
}

export interface GraphStats {
  total_files: number
  total_commits: number
  total_authors: number
  total_chunks: number
  total_prs: number
  top_authors: Array<{ name: string; email: string; commit_count: number }>
}

export interface GraphVisualization {
  nodes: Array<{
    id: string
    label: string
    type: string
    data: Record<string, string>
  }>
  edges: Array<{
    source: string
    target: string
    type: string
  }>
  repo_name: string
  stats: { node_count: number; edge_count: number }
}

export interface HealthCheck {
  status: string
  version: string
  checks: Record<string, string | boolean>
}

// API functions
export const listRepositories = () =>
  api.get<Repository[]>('/ingest/repositories').then((r) => r.data)

export const ingestGitRepo = (repoPath: string, repoName: string) =>
  api.post('/ingest/git', { repo_path: repoPath, repo_name: repoName }).then((r) => r.data)

export const ingestGitHubRepo = (repoUrl: string, repoName: string) =>
  api.post('/ingest/github', { repo_url: repoUrl, repo_name: repoName }).then((r) => r.data)

export const getJobStatus = (jobId: string) =>
  api.get<IngestionJob>(`/ingest/jobs/${jobId}`).then((r) => r.data)

export const queryCodebase = (question: string, repoName?: string, topK = 8) =>
  api
    .post<QueryResponse>('/query', { question, repo_name: repoName || null, top_k: topK })
    .then((r) => r.data)

export const getQueryHistory = (repoName?: string) =>
  api
    .get<QueryHistory[]>('/query/history', { params: repoName ? { repo_name: repoName } : {} })
    .then((r) => r.data)

export const getGraphStats = (repoName: string) =>
  api.get<{ repo_name: string; stats: GraphStats }>(`/graph/${repoName}/stats`).then((r) => r.data)

export const getGraphVisualization = (repoName: string, limit = 80) =>
  api
    .get<GraphVisualization>(`/graph/${repoName}/visualization`, { params: { limit } })
    .then((r) => r.data)

export const getFileHistory = (repoName: string, filePath: string) =>
  api
    .get(`/graph/${repoName}/file-history`, { params: { file_path: filePath } })
    .then((r) => r.data)

export const getHealthCheck = () =>
  api.get<HealthCheck>('/health').then((r) => r.data)