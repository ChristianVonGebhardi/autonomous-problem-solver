'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import {
  Layers,
  RefreshCw,
  GitBranch,
  Network,
  Search,
  Clock,
  FileCode,
  GitCommit,
} from 'lucide-react'
import { Sidebar } from '@/components/Sidebar'
import { StatusBadge } from '@/components/StatusBadge'
import { listRepositories } from '@/lib/api'

export default function RepositoriesPage() {
  const queryClient = useQueryClient()

  const { data: repos, isLoading, refetch } = useQuery({
    queryKey: ['repositories'],
    queryFn: listRepositories,
    refetchInterval: 10000,
  })

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                <Layers className="text-brand-500" size={24} />
                Repositories
              </h1>
              <p className="text-slate-500 mt-1">All indexed repositories in the knowledge platform</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => refetch()}
                className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 px-3 py-2 rounded-lg border border-slate-200 hover:bg-slate-50"
              >
                <RefreshCw size={14} />
                Refresh
              </button>
              <Link
                href="/ingest"
                className="flex items-center gap-1.5 text-sm text-white bg-brand-600 hover:bg-brand-700 px-3 py-2 rounded-lg"
              >
                <GitBranch size={14} />
                Ingest New
              </Link>
            </div>
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 h-32 skeleton" />
              ))}
            </div>
          ) : repos && repos.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {repos.map((repo) => (
                <div key={repo.id} className="bg-white rounded-xl border border-slate-200 p-5 hover:border-brand-300 hover:shadow-md transition-all">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-semibold text-slate-800 text-base">{repo.name}</h3>
                      <p className="text-xs text-slate-400 mt-0.5 truncate max-w-[220px]">
                        {repo.repo_url ?? repo.repo_path ?? '—'}
                      </p>
                    </div>
                    <StatusBadge status={repo.status} />
                  </div>

                  <div className="grid grid-cols-3 gap-2 mb-4">
                    <MetricChip
                      icon={FileCode}
                      label="Files"
                      value={repo.file_count?.toLocaleString() ?? '0'}
                    />
                    <MetricChip
                      icon={GitCommit}
                      label="Commits"
                      value={repo.commit_count?.toLocaleString() ?? '0'}
                    />
                    <MetricChip
                      icon={Clock}
                      label="Indexed"
                      value={
                        repo.last_ingested_at
                          ? new Date(repo.last_ingested_at).toLocaleDateString()
                          : 'Never'
                      }
                    />
                  </div>

                  {repo.status === 'ready' && (
                    <div className="flex gap-2">
                      <Link
                        href={`/query?repo=${repo.name}`}
                        className="flex-1 flex items-center justify-center gap-1.5 text-xs text-white bg-brand-600 hover:bg-brand-700 py-1.5 px-3 rounded-lg transition-colors"
                      >
                        <Search size={12} />
                        Query
                      </Link>
                      <Link
                        href={`/graph?repo=${repo.name}`}
                        className="flex-1 flex items-center justify-center gap-1.5 text-xs text-slate-600 bg-slate-100 hover:bg-slate-200 py-1.5 px-3 rounded-lg transition-colors"
                      >
                        <Network size={12} />
                        Graph
                      </Link>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 p-16 text-center">
              <Layers size={48} className="text-slate-300 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-slate-600">No repositories yet</h2>
              <p className="text-sm text-slate-400 mt-1 mb-4">
                Ingest a git repository to start querying your codebase
              </p>
              <Link
                href="/ingest"
                className="inline-flex items-center gap-2 text-sm text-white bg-brand-600 hover:bg-brand-700 px-4 py-2.5 rounded-lg transition-colors"
              >
                <GitBranch size={16} />
                Ingest First Repository
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function MetricChip({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>
  label: string
  value: string
}) {
  return (
    <div className="bg-slate-50 rounded-lg p-2 text-center">
      <Icon size={13} className="text-slate-400 mx-auto mb-0.5" />
      <div className="text-sm font-semibold text-slate-700">{value}</div>
      <div className="text-[9px] text-slate-400">{label}</div>
    </div>
  )
}