'use client'

import { useState, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'next/navigation'
import { Network, Users, GitCommit, FileCode, GitPullRequest, RefreshCw, Loader2 } from 'lucide-react'
import { Sidebar } from '@/components/Sidebar'
import { GraphCanvas } from '@/components/GraphCanvas'
import { listRepositories, getGraphStats, getGraphVisualization } from '@/lib/api'

function GraphPageInner() {
  const searchParams = useSearchParams()
  const initialRepo = searchParams.get('repo') ?? ''
  const [selectedRepo, setSelectedRepo] = useState<string>(initialRepo)

  const { data: repos } = useQuery({
    queryKey: ['repositories'],
    queryFn: listRepositories,
  })

  const readyRepos = repos?.filter((r) => r.status === 'ready') ?? []

  const { data: stats } = useQuery({
    queryKey: ['graph-stats', selectedRepo],
    queryFn: () => getGraphStats(selectedRepo),
    enabled: !!selectedRepo,
  })

  const {
    data: graphData,
    isLoading: graphLoading,
    refetch,
  } = useQuery({
    queryKey: ['graph-viz', selectedRepo],
    queryFn: () => getGraphVisualization(selectedRepo, 80),
    enabled: !!selectedRepo,
  })

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-6xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                <Network className="text-brand-500" size={24} />
                Knowledge Graph
              </h1>
              <p className="text-slate-500 mt-1">
                Visual map of files, commits, authors, and architectural relationships
              </p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                className="text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                <option value="">Select repository…</option>
                {readyRepos.map((r) => (
                  <option key={r.id} value={r.name}>
                    {r.name}
                  </option>
                ))}
              </select>
              {selectedRepo && (
                <button
                  onClick={() => refetch()}
                  className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 px-3 py-2 rounded-lg border border-slate-200 hover:bg-slate-50"
                >
                  <RefreshCw size={14} />
                  Refresh
                </button>
              )}
            </div>
          </div>

          {!selectedRepo && (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
              <Network size={48} className="text-slate-300 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-slate-600">Select a repository</h2>
              <p className="text-sm text-slate-400 mt-1">
                Choose a repository to explore its knowledge graph
              </p>
              {readyRepos.length === 0 && (
                <p className="text-sm text-amber-600 mt-3">
                  No ready repositories found. Please ingest a repository first.
                </p>
              )}
            </div>
          )}

          {selectedRepo && (
            <>
              {stats && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <StatCard label="Files" value={stats.stats.total_files} icon={FileCode} color="violet" />
                  <StatCard label="Commits" value={stats.stats.total_commits} icon={GitCommit} color="amber" />
                  <StatCard label="Authors" value={stats.stats.total_authors} icon={Users} color="emerald" />
                  <StatCard label="Chunks" value={stats.stats.total_chunks} icon={FileCode} color="blue" />
                  <StatCard label="PRs" value={stats.stats.total_prs} icon={GitPullRequest} color="rose" />
                </div>
              )}

              {stats?.stats.top_authors && stats.stats.top_authors.length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 p-5">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3">Top Contributors</h3>
                  <div className="flex flex-wrap gap-2">
                    {stats.stats.top_authors.map((author) => (
                      <div
                        key={author.email}
                        className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-full"
                      >
                        <div className="w-5 h-5 rounded-full bg-brand-500 text-white text-[9px] font-bold flex items-center justify-center">
                          {(author.name || author.email || 'U')[0].toUpperCase()}
                        </div>
                        <span className="text-xs font-medium text-slate-700">
                          {author.name || author.email}
                        </span>
                        <span className="text-[10px] text-slate-400">{author.commit_count} commits</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-700">
                    Relationship Graph
                    {graphData && (
                      <span className="ml-2 text-xs text-slate-400 font-normal">
                        {graphData.stats.node_count} nodes · {graphData.stats.edge_count} edges
                      </span>
                    )}
                  </h3>
                </div>

                {graphLoading && (
                  <div className="flex items-center justify-center h-64 text-slate-400 gap-2">
                    <Loader2 size={20} className="animate-spin" />
                    Loading graph data…
                  </div>
                )}

                {graphData && graphData.nodes.length > 0 && <GraphCanvas data={graphData} />}

                {graphData && graphData.nodes.length === 0 && (
                  <div className="flex items-center justify-center h-64 text-slate-400">
                    <div className="text-center">
                      <Network size={32} className="mx-auto mb-2 opacity-50" />
                      <p className="text-sm">No graph data available yet</p>
                      <p className="text-xs mt-1">The repository may still be indexing</p>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

export default function GraphPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen bg-slate-50 items-center justify-center text-slate-400">Loading…</div>}>
      <GraphPageInner />
    </Suspense>
  )
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: number
  icon: React.ComponentType<{ size?: number; className?: string }>
  color: string
}) {
  const colorMap: Record<string, string> = {
    violet: 'bg-violet-50 text-violet-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    blue: 'bg-blue-50 text-blue-600',
    rose: 'bg-rose-50 text-rose-600',
  }
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className={`w-8 h-8 rounded-lg ${colorMap[color]} flex items-center justify-center mb-2`}>
        <Icon size={16} />
      </div>
      <div className="text-xl font-bold text-slate-900">{value.toLocaleString()}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  )
}