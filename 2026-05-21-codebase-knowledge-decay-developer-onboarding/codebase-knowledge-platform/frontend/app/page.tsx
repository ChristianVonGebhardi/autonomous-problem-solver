'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import {
  Brain,
  GitBranch,
  Search,
  Network,
  Zap,
  BookOpen,
  ArrowRight,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
} from 'lucide-react'
import { Sidebar } from '@/components/Sidebar'
import { StatusBadge } from '@/components/StatusBadge'
import { getHealthCheck, listRepositories, getQueryHistory } from '@/lib/api'

export default function DashboardPage() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealthCheck,
    refetchInterval: 30000,
  })

  const { data: repos } = useQuery({
    queryKey: ['repositories'],
    queryFn: listRepositories,
    refetchInterval: 10000,
  })

  const { data: history } = useQuery({
    queryKey: ['query-history'],
    queryFn: () => getQueryHistory(),
  })

  const readyRepos = repos?.filter((r) => r.status === 'ready') ?? []
  const ingestingRepos = repos?.filter((r) => r.status === 'ingesting') ?? []

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-6xl mx-auto space-y-8">
          {/* Header */}
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Brain className="text-brand-500" size={26} />
              Codebase Knowledge Platform
            </h1>
            <p className="text-slate-500 mt-1">
              AI-powered knowledge graph — query your codebase in natural language
            </p>
          </div>

          {/* System Status */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatusCard
              title="System"
              value={health?.status ?? '…'}
              icon={health?.status === 'ok' ? CheckCircle : AlertCircle}
              color={health?.status === 'ok' ? 'green' : 'yellow'}
            />
            <StatusCard
              title="Repositories"
              value={String(repos?.length ?? 0)}
              icon={GitBranch}
              color="blue"
              sub={readyRepos.length > 0 ? `${readyRepos.length} ready` : undefined}
            />
            <StatusCard
              title="Queries Run"
              value={String(history?.length ?? 0)}
              icon={Search}
              color="violet"
            />
            <StatusCard
              title="LLM Mode"
              value={health?.checks?.llm === 'openai' ? 'GPT-4o' : 'Mock'}
              icon={Zap}
              color={health?.checks?.llm === 'openai' ? 'green' : 'yellow'}
              sub={health?.checks?.llm === 'mock' ? 'Set OPENAI_API_KEY' : undefined}
            />
          </div>

          {/* Service Health */}
          {health && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-3">Service Health</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(health.checks).map(([service, status]) => {
                  const isOk =
                    status === 'ok' ||
                    status === 'openai' ||
                    status === 'mock' ||
                    status === true
                  const isError = typeof status === 'string' && status.startsWith('error')
                  return (
                    <div
                      key={service}
                      className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-50 border border-slate-100"
                    >
                      {isError ? (
                        <XCircle size={14} className="text-red-500 shrink-0" />
                      ) : isOk ? (
                        <CheckCircle size={14} className="text-green-500 shrink-0" />
                      ) : (
                        <AlertCircle size={14} className="text-yellow-500 shrink-0" />
                      )}
                      <div>
                        <div className="text-xs font-medium text-slate-700 capitalize">{service}</div>
                        <div className="text-[10px] text-slate-400 truncate max-w-[100px]">
                          {String(status)}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <QuickAction
              href="/ingest"
              icon={GitBranch}
              title="Ingest Repository"
              description="Index a local git repo or GitHub URL into the knowledge graph"
              color="blue"
            />
            <QuickAction
              href="/query"
              icon={Search}
              title="Ask Codebase"
              description="Query your codebase using natural language — get AI-synthesized answers"
              color="violet"
              disabled={readyRepos.length === 0}
              disabledTip="Ingest a repository first"
            />
            <QuickAction
              href="/graph"
              icon={Network}
              title="View Knowledge Graph"
              description="Visualize file relationships, authors, commits, and PRs"
              color="emerald"
              disabled={readyRepos.length === 0}
              disabledTip="Ingest a repository first"
            />
          </div>

          {/* Repositories & Recent Queries */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Repositories */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-700">Repositories</h2>
                <Link
                  href="/repositories"
                  className="text-xs text-brand-600 hover:text-brand-700 flex items-center gap-1"
                >
                  View all <ArrowRight size={11} />
                </Link>
              </div>
              {repos && repos.length > 0 ? (
                <div className="space-y-2">
                  {repos.slice(0, 5).map((repo) => (
                    <div
                      key={repo.id}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100"
                    >
                      <div>
                        <div className="text-sm font-medium text-slate-800">{repo.name}</div>
                        <div className="text-xs text-slate-400 mt-0.5">
                          {repo.file_count > 0 && `${repo.file_count} files`}
                          {repo.commit_count > 0 && ` · ${repo.commit_count} commits`}
                        </div>
                      </div>
                      <StatusBadge status={repo.status} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-slate-400">
                  <GitBranch size={28} className="mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No repositories yet</p>
                  <Link href="/ingest" className="text-xs text-brand-600 hover:underline mt-1 block">
                    Ingest your first repo →
                  </Link>
                </div>
              )}
            </div>

            {/* Recent Queries */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-700">Recent Queries</h2>
                <Link
                  href="/query"
                  className="text-xs text-brand-600 hover:text-brand-700 flex items-center gap-1"
                >
                  Ask a question <ArrowRight size={11} />
                </Link>
              </div>
              {history && history.length > 0 ? (
                <div className="space-y-2">
                  {history.slice(0, 5).map((q) => (
                    <div
                      key={q.id}
                      className="p-3 rounded-lg bg-slate-50 border border-slate-100"
                    >
                      <div className="text-sm text-slate-700 font-medium truncate">{q.question}</div>
                      <div className="text-xs text-slate-400 mt-1 truncate">{q.answer_preview}</div>
                      <div className="flex items-center gap-2 mt-1">
                        {q.repo_name && (
                          <span className="text-[10px] bg-slate-200 text-slate-600 px-1.5 rounded">
                            {q.repo_name}
                          </span>
                        )}
                        {q.latency_ms && (
                          <span className="text-[10px] text-slate-400 flex items-center gap-0.5">
                            <Clock size={9} /> {q.latency_ms}ms
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-slate-400">
                  <BookOpen size={28} className="mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No queries yet</p>
                  <p className="text-xs mt-1">Ask a question about your codebase</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

// Sub-components
function StatusCard({
  title,
  value,
  icon: Icon,
  color,
  sub,
}: {
  title: string
  value: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  color: string
  sub?: string
}) {
  const colorMap: Record<string, string> = {
    green: 'bg-green-50 text-green-600',
    blue: 'bg-blue-50 text-blue-600',
    violet: 'bg-violet-50 text-violet-600',
    yellow: 'bg-yellow-50 text-yellow-600',
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className={`w-9 h-9 rounded-lg ${colorMap[color]} flex items-center justify-center mb-3`}>
        <Icon size={18} />
      </div>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{title}</div>
      {sub && <div className="text-[10px] text-slate-400 mt-1">{sub}</div>}
    </div>
  )
}

function QuickAction({
  href,
  icon: Icon,
  title,
  description,
  color,
  disabled,
  disabledTip,
}: {
  href: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  title: string
  description: string
  color: string
  disabled?: boolean
  disabledTip?: string
}) {
  const colorMap: Record<string, string> = {
    blue: 'bg-blue-500',
    violet: 'bg-violet-500',
    emerald: 'bg-emerald-500',
  }

  const content = (
    <div
      className={`bg-white rounded-xl border ${disabled ? 'border-slate-200 opacity-60 cursor-not-allowed' : 'border-slate-200 hover:border-brand-300 hover:shadow-md cursor-pointer'} p-5 transition-all group`}
    >
      <div
        className={`w-10 h-10 rounded-lg ${colorMap[color]} flex items-center justify-center mb-3 group-hover:scale-105 transition-transform`}
      >
        <Icon size={20} className="text-white" />
      </div>
      <h3 className="font-semibold text-slate-800">{title}</h3>
      <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
      {disabled && disabledTip && (
        <p className="text-xs text-amber-600 mt-2 flex items-center gap-1">
          <AlertCircle size={11} /> {disabledTip}
        </p>
      )}
    </div>
  )

  if (disabled) return content
  return <Link href={href}>{content}</Link>
}