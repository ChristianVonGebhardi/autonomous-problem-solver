import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  X,
  ClipboardList,
  DollarSign,
  Clock,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'
import api from '../api'
import type { Violation } from '../types'
import { useNotificationStore } from '../store'

function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    {
      low: 'badge-severity-low',
      medium: 'badge-severity-medium',
      high: 'badge-severity-high',
      critical: 'badge-severity-critical',
    }[severity] ?? 'badge-severity-low'
  return (
    <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium border', cls)}>
      {severity}
    </span>
  )
}

function ViolationCard({ violation }: { violation: Violation }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()

  const dismissMutation = useMutation({
    mutationFn: () => api.post(`/violations/${violation.id}/dismiss`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      toast.success('Violation dismissed')
    },
  })

  const isResolved = violation.status !== 'pending'

  return (
    <div
      className={clsx(
        'card transition-colors',
        violation.severity === 'critical' && !isResolved && 'border-red-800/50',
        violation.severity === 'high' && !isResolved && 'border-orange-800/50',
      )}
    >
      <div className="flex items-start gap-4">
        <div
          className={clsx('p-2 rounded-lg flex-shrink-0', {
            'bg-red-900/40': violation.severity === 'critical',
            'bg-orange-900/40': violation.severity === 'high',
            'bg-yellow-900/40': violation.severity === 'medium',
            'bg-green-900/40': violation.severity === 'low',
          })}
        >
          <AlertTriangle
            className={clsx('w-5 h-5', {
              'text-red-400': violation.severity === 'critical',
              'text-orange-400': violation.severity === 'high',
              'text-yellow-400': violation.severity === 'medium',
              'text-green-400': violation.severity === 'low',
            })}
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <SeverityBadge severity={violation.severity} />
            <span
              className={clsx('text-xs px-2 py-0.5 rounded-full border', {
                'bg-yellow-900/30 text-yellow-400 border-yellow-800': violation.status === 'pending',
                'bg-primary-900/30 text-primary-400 border-primary-800':
                  violation.status === 'change_order_created',
                'bg-slate-800 text-slate-400 border-slate-700': violation.status === 'dismissed',
              })}
            >
              {violation.status.replace(/_/g, ' ')}
            </span>
            <span className="text-xs text-slate-500">
              {formatDistanceToNow(new Date(violation.created_at), { addSuffix: true })}
            </span>
          </div>

          <p className="text-slate-200 font-medium mb-2">{violation.summary}</p>

          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1 text-slate-400">
              <Clock className="w-3.5 h-3.5" />
              <span>{violation.estimated_hours?.toFixed(1) ?? '?'} hrs estimated</span>
            </div>
            {violation.estimated_cost && (
              <div className="flex items-center gap-1 text-green-400 font-medium">
                <DollarSign className="w-3.5 h-3.5" />
                <span>${violation.estimated_cost.toLocaleString()}</span>
              </div>
            )}
            <div className="text-slate-500">
              Score: {(violation.violation_score * 100).toFixed(0)}%
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {violation.status === 'pending' && (
            <button
              onClick={() => dismissMutation.mutate()}
              disabled={dismissMutation.isPending}
              title="Dismiss violation"
              className="text-slate-500 hover:text-red-400 p-1 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-slate-400 hover:text-white p-1 transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-slate-800 space-y-4">
          <div>
            <h4 className="text-sm font-semibold text-slate-300 mb-1">
              Out-of-Scope Work Detected
            </h4>
            <p className="text-sm text-slate-400 bg-slate-800/50 rounded-lg p-3">
              {violation.out_of_scope_work}
            </p>
          </div>

          {violation.cited_clauses && violation.cited_clauses.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-2">
                Cited Contract Clauses
              </h4>
              <div className="space-y-2">
                {violation.cited_clauses.map((clause, i) => (
                  <div
                    key={i}
                    className="bg-slate-800/50 rounded-lg p-3 border-l-2 border-primary-600"
                  >
                    <p className="text-sm text-slate-300">
                      {typeof clause === 'object' && clause !== null
                        ? (clause as { text: string }).text
                        : String(clause)}
                    </p>
                    {typeof clause === 'object' &&
                      clause !== null &&
                      (clause as { relevance?: string }).relevance && (
                        <p className="text-xs text-slate-500 mt-1 italic">
                          {(clause as { relevance: string }).relevance}
                        </p>
                      )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {violation.status === 'change_order_created' && (
            <div className="flex items-center gap-2 text-primary-400 bg-primary-900/20 rounded-lg p-3">
              <ClipboardList className="w-4 h-4" />
              <span className="text-sm">
                Change order has been auto-generated.{' '}
                <a href="/change-orders" className="underline hover:text-primary-300">
                  Review it →
                </a>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ViolationsPage() {
  const { markAllRead } = useNotificationStore()
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const { data: violations, isLoading } = useQuery<Violation[]>({
    queryKey: ['violations'],
    queryFn: async () => (await api.get('/violations/')).data,
  })

  // Mark notifications read when page loads
  useEffect(() => {
    markAllRead()
  }, [markAllRead])

  const filtered = violations?.filter(
    (v) => statusFilter === 'all' || v.status === statusFilter,
  )

  const counts = {
    all: violations?.length ?? 0,
    pending: violations?.filter((v) => v.status === 'pending').length ?? 0,
    change_order_created:
      violations?.filter((v) => v.status === 'change_order_created').length ?? 0,
    dismissed: violations?.filter((v) => v.status === 'dismissed').length ?? 0,
  }

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Violations</h1>
        <p className="text-slate-400 mt-1">Scope creep detected in client messages</p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {[
          { key: 'all', label: 'All' },
          { key: 'pending', label: 'Pending' },
          { key: 'change_order_created', label: 'Change Order Created' },
          { key: 'dismissed', label: 'Dismissed' },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setStatusFilter(key)}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              statusFilter === key
                ? 'bg-primary-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:text-white',
            )}
          >
            {label}
            {counts[key as keyof typeof counts] > 0 && (
              <span className="ml-1.5 text-xs opacity-70">
                ({counts[key as keyof typeof counts]})
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-slate-400 animate-pulse">Loading violations...</div>
      ) : !filtered?.length ? (
        <div className="card text-center py-16">
          <AlertTriangle className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">
            {statusFilter === 'all' ? 'No violations detected yet' : `No ${statusFilter} violations`}
          </h3>
          <p className="text-slate-400">
            {statusFilter === 'all'
              ? 'Analyze client messages to detect scope creep'
              : 'Try changing the filter above'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((v) => (
            <ViolationCard key={v.id} violation={v} />
          ))}
        </div>
      )}
    </div>
  )
}