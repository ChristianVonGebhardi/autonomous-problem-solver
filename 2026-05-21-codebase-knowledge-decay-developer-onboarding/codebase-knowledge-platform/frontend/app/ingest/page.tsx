'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  GitBranch,
  Github,
  FolderOpen,
  Link as LinkIcon,
  Loader2,
  CheckCircle,
  AlertCircle,
  RefreshCw,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { Sidebar } from '@/components/Sidebar'
import { StatusBadge } from '@/components/StatusBadge'
import { ingestGitRepo, ingestGitHubRepo, getJobStatus, listRepositories } from '@/lib/api'

export default function IngestPage() {
  const [activeTab, setActiveTab] = useState<'local' | 'github'>('local')
  const [repoPath, setRepoPath] = useState('')
  const [repoName, setRepoName] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: repos, refetch: refetchRepos } = useQuery({
    queryKey: ['repositories'],
    queryFn: listRepositories,
    refetchInterval: 5000,
  })

  const { data: jobStatus } = useQuery({
    queryKey: ['job', activeJobId],
    queryFn: () => getJobStatus(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (data) => {
      if (!data || data.status === 'completed' || data.status === 'failed') return false
      return 2000
    },
  })

  useEffect(() => {
    if (jobStatus?.status === 'completed') {
      toast.success('Repository ingested successfully!')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
    } else if (jobStatus?.status === 'failed') {
      toast.error(`Ingestion failed: ${jobStatus.error_message ?? 'Unknown error'}`)
    }
  }, [jobStatus?.status, queryClient])

  const localMutation = useMutation({
    mutationFn: () => ingestGitRepo(repoPath.trim(), repoName.trim()),
    onSuccess: (data) => {
      setActiveJobId(data.job_id)
      toast.success('Ingestion started!')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Ingestion failed'
      toast.error(msg)
    },
  })

  const githubMutation = useMutation({
    mutationFn: () => ingestGitHubRepo(repoUrl.trim(), repoName.trim()),
    onSuccess: (data) => {
      setActiveJobId(data.job_id)
      toast.success('GitHub ingestion started!')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Ingestion failed'
      toast.error(msg)
    },
  })

  const autoName = (val: string) => {
    if (!repoName) {
      const parts = val.replace(/\.git$/, '').split(/[/\\]/)
      const name = parts[parts.length - 1]
      if (name) setRepoName(name)
    }
  }

  const progress = jobStatus?.celery_state?.info?.progress as number | undefined
    ?? jobStatus?.progress ?? 0
  const progressMsg = jobStatus?.celery_state?.info?.message as string | undefined ?? ''

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-3xl mx-auto space-y-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <GitBranch className="text-brand-500" size={24} />
              Ingest Repository
            </h1>
            <p className="text-slate-500 mt-1">
              Index your codebase into the knowledge graph for AI-powered querying
            </p>
          </div>

          {/* Tabs */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="flex border-b border-slate-200">
              <button
                className={`flex-1 flex items-center justify-center gap-2 py-3.5 text-sm font-medium transition-colors ${
                  activeTab === 'local'
                    ? 'bg-brand-50 text-brand-700 border-b-2 border-brand-500'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
                onClick={() => setActiveTab('local')}
              >
                <FolderOpen size={16} />
                Local Repository
              </button>
              <button
                className={`flex-1 flex items-center justify-center gap-2 py-3.5 text-sm font-medium transition-colors ${
                  activeTab === 'github'
                    ? 'bg-brand-50 text-brand-700 border-b-2 border-brand-500'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
                onClick={() => setActiveTab('github')}
              >
                <Github size={16} />
                GitHub Repository
              </button>
            </div>

            <div className="p-6 space-y-5">
              {activeTab === 'local' ? (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Repository Path
                    </label>
                    <input
                      type="text"
                      placeholder="/home/user/myproject or /Users/user/code/myrepo"
                      value={repoPath}
                      onChange={(e) => {
                        setRepoPath(e.target.value)
                        autoName(e.target.value)
                      }}
                      className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    />
                    <p className="text-xs text-slate-400 mt-1">
                      Absolute path to a local git repository accessible by the backend container
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Repository Name
                    </label>
                    <input
                      type="text"
                      placeholder="my-project"
                      value={repoName}
                      onChange={(e) => setRepoName(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    />
                  </div>
                  <button
                    onClick={() => localMutation.mutate()}
                    disabled={!repoPath.trim() || !repoName.trim() || localMutation.isPending}
                    className="w-full py-2.5 px-4 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
                  >
                    {localMutation.isPending ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Starting ingestion…
                      </>
                    ) : (
                      <>
                        <GitBranch size={16} />
                        Start Ingestion
                      </>
                    )}
                  </button>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      GitHub URL
                    </label>
                    <input
                      type="text"
                      placeholder="https://github.com/owner/repo"
                      value={repoUrl}
                      onChange={(e) => {
                        setRepoUrl(e.target.value)
                        autoName(e.target.value)
                      }}
                      className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    />
                    <p className="text-xs text-slate-400 mt-1">
                      Public repo or private repo (requires GITHUB_TOKEN in .env)
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Repository Name
                    </label>
                    <input
                      type="text"
                      placeholder="repo-name"
                      value={repoName}
                      onChange={(e) => setRepoName(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    />
                  </div>
                  <button
                    onClick={() => githubMutation.mutate()}
                    disabled={!repoUrl.trim() || !repoName.trim() || githubMutation.isPending}
                    className="w-full py-2.5 px-4 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
                  >
                    {githubMutation.isPending ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Starting ingestion…
                      </>
                    ) : (
                      <>
                        <Github size={16} />
                        Clone & Ingest
                      </>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Job Progress */}
          {activeJobId && jobStatus && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-700">Ingestion Progress</h3>
                <StatusBadge status={jobStatus.status} />
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2.5 mb-2">
                <div
                  className="h-2.5 rounded-full bg-brand-500 transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>{progressMsg || `${progress}% complete`}</span>
                <span>{progress}%</span>
              </div>
              {jobStatus.status === 'completed' && (
                <div className="mt-3 flex items-center gap-2 text-sm text-green-600">
                  <CheckCircle size={16} />
                  Ingestion complete! You can now query this repository.
                </div>
              )}
              {jobStatus.status === 'failed' && (
                <div className="mt-3 flex items-center gap-2 text-sm text-red-600">
                  <AlertCircle size={16} />
                  {jobStatus.error_message ?? 'Ingestion failed'}
                </div>
              )}
            </div>
          )}

          {/* Repository List */}
          {repos && repos.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-700">Ingested Repositories</h3>
                <button
                  onClick={() => refetchRepos()}
                  className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"
                >
                  <RefreshCw size={12} />
                  Refresh
                </button>
              </div>
              <div className="space-y-2">
                {repos.map((repo) => (
                  <div
                    key={repo.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100"
                  >
                    <div>
                      <div className="text-sm font-medium text-slate-800">{repo.name}</div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {repo.repo_path ?? repo.repo_url ?? '—'}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {repo.file_count > 0 && `${repo.file_count} files`}
                        {repo.commit_count > 0 && ` · ${repo.commit_count} commits`}
                        {repo.last_ingested_at &&
                          ` · ${new Date(repo.last_ingested_at).toLocaleString()}`}
                      </div>
                    </div>
                    <StatusBadge status={repo.status} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}