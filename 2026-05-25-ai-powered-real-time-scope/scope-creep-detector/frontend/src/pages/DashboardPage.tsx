import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  FileText,
  AlertTriangle,
  ClipboardList,
  DollarSign,
  Activity,
  ChevronRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import api from '../api'
import type { DashboardStats, Violation, ChangeOrder } from '../types'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ElementType
  color: string
}) {
  return (
    <div className="card flex items-start gap-4">
      <div className={clsx('p-3 rounded-lg', color)}>
        <Icon className="w-5 h-5 text-white" />
      </div>
      <div>
        <div className="text-2xl font-bold text-white">{value}</div>
        <div className="text-sm text-slate-400">{label}</div>
        {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const cls = {
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

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: async () => (await api.get('/dashboard/stats')).data,
    refetchInterval: 30_000,
  })

  const { data: violations } = useQuery<Violation[]>({
    queryKey: ['violations', 'recent'],
    queryFn: async () => (await api.get('/violations/?status=pending')).data,
  })

  const { data: changeOrders } = useQuery<ChangeOrder[]>({
    queryKey: ['change-orders', 'recent'],
    queryFn: async () => (await api.get('/change-orders/?status=draft')).data,
  })

  if (statsLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-slate-400 animate-pulse">Loading dashboard...</div>
      </div>
    )
  }

  const s = stats

  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-slate-400 mt-1">Monitor your scope creep and recovered revenue</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          label="Recovered Revenue"
          value={`$${(s?.recovered_revenue ?? 0).toLocaleString()}`}
          sub={`$${(s?.monthly_recovered ?? 0).toLocaleString()} this month`}
          icon={DollarSign}
          color="bg-green-600"
        />
        <StatCard
          label="Violations Detected"
          value={s?.total_violations ?? 0}
          sub={`${s?.pending_violations ?? 0} pending review`}
          icon={AlertTriangle}
          color="bg-orange-500"
        />
        <StatCard
          label="Change Orders"
          value={s?.total_change_orders ?? 0}
          sub={`${s?.approved_change_orders ?? 0} approved`}
          icon={ClipboardList}
          color="bg-primary-600"
        />
        <StatCard
          label="Active Contracts"
          value={s?.active_contracts ?? 0}
          sub={`${s?.total_contracts ?? 0} total`}
          icon={FileText}
          color="bg-violet-600"
        />
      </div>

      {/* Potential revenue alert */}
      {(s?.potential_revenue ?? 0) > 0 && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TrendingUp className="w-5 h-5 text-amber-400" />
            <div>
              <span className="text-amber-300 font-medium">
                ${(s?.potential_revenue ?? 0).toLocaleString()} in potential billings detected
              </span>
              <span className="text-slate-400 text-sm ml-2">
                — approve change orders to recover this revenue
              </span>
            </div>
          </div>
          <Link to="/change-orders" className="text-amber-400 hover:text-amber-300 text-sm flex items-center gap-1">
            Review <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Recent violations */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-orange-400" />
              Recent Violations
            </h2>
            <Link to="/violations" className="text-primary-400 hover:text-primary-300 text-sm">
              View all
            </Link>
          </div>

          {!violations?.length ? (
            <div className="text-center py-8 text-slate-500">
              <Activity className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p>No violations detected yet</p>
              <p className="text-sm mt-1">Upload a contract and analyze client messages to start</p>
            </div>
          ) : (
            <div className="space-y-3">
              {violations.slice(0, 5).map((v) => (
                <div
                  key={v.id}
                  className="flex items-start gap-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700/50"
                >
                  <SeverityBadge severity={v.severity} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 line-clamp-2">{v.summary}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs text-slate-500">
                        {formatDistanceToNow(new Date(v.created_at), { addSuffix: true })}
                      </span>
                      {v.estimated_cost && (
                        <span className="text-xs text-green-400 font-medium">
                          +${v.estimated_cost.toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pending change orders */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <ClipboardList className="w-5 h-5 text-primary-400" />
              Pending Change Orders
            </h2>
            <Link to="/change-orders" className="text-primary-400 hover:text-primary-300 text-sm">
              View all
            </Link>
          </div>

          {!changeOrders?.length ? (
            <div className="text-center py-8 text-slate-500">
              <ClipboardList className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p>No pending change orders</p>
              <p className="text-sm mt-1">Change orders are auto-generated when scope creep is detected</p>
            </div>
          ) : (
            <div className="space-y-3">
              {changeOrders.slice(0, 5).map((co) => (
                <div
                  key={co.id}
                  className="flex items-center gap-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700/50"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">{co.title}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {formatDistanceToNow(new Date(co.created_at), { addSuffix: true })}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-green-400">
                      ${co.total_cost.toLocaleString()}
                    </div>
                    <div className="text-xs text-slate-500">{co.estimated_hours}h</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Quick start guide (shown when no contracts) */}
      {(s?.total_contracts ?? 0) === 0 && (
        <div className="card border-dashed border-slate-600">
          <h3 className="text-lg font-semibold text-white mb-4">🚀 Get Started</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              {
                step: '1',
                title: 'Upload Your Contract',
                desc: 'Upload a PDF or DOCX signed contract. We\'ll parse and index every clause.',
                link: '/contracts',
                cta: 'Upload Contract',
              },
              {
                step: '2',
                title: 'Paste a Client Message',
                desc: 'Paste any client email or Slack message that might be requesting extra work.',
                link: '/messages',
                cta: 'Analyze Message',
              },
              {
                step: '3',
                title: 'Review & Send',
                desc: 'Review the AI-generated change order and send it to your client in one click.',
                link: '/change-orders',
                cta: 'View Change Orders',
              },
            ].map(({ step, title, desc, link, cta }) => (
              <div key={step} className="bg-slate-800 rounded-lg p-4">
                <div className="text-primary-400 font-bold text-lg mb-2">Step {step}</div>
                <h4 className="font-medium text-white mb-1">{title}</h4>
                <p className="text-sm text-slate-400 mb-3">{desc}</p>
                <Link to={link} className="text-primary-400 hover:text-primary-300 text-sm font-medium flex items-center gap-1">
                  {cta} <ChevronRight className="w-3 h-3" />
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}