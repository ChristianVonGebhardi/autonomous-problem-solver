import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Legend
} from 'recharts'
import { AlertTriangle, GitPullRequest, Activity, CheckCircle, XCircle } from 'lucide-react'
import { api, type DashboardStats, type TrendPoint } from '../api'
import { StatCard } from '../components/StatCard'
import { CauseBadge } from '../components/CauseBadge'
import { ScoreBar } from '../components/ScoreBar'
import type { CauseType } from '../api'

const CAUSE_PIE_COLORS: Record<string, string> = {
  timing: '#f59e0b',
  concurrency: '#a855f7',
  environment: '#3b82f6',
  state_leakage: '#ef4444',
  unknown: '#6b7280',
}

const DAYS_OPTIONS = [7, 14, 30, 60]

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [trends, setTrends] = useState<TrendPoint[]>([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([api.stats(), api.trends(days)])
      .then(([s, t]) => {
        setStats(s)
        setTrends(t.data)
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [days])

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-500">Loading dashboard...</div>
  if (error) return (
    <div className="bg-red-900/30 border border-red-700 rounded-xl p-6 text-red-300">
      <p className="font-medium">Failed to load dashboard</p>
      <p className="text-sm mt-1">{error}</p>
      <p className="text-sm mt-2 text-gray-400">Make sure the backend is running: <code>uvicorn app.main:app</code></p>
    </div>
  )
  if (!stats) return null

  const causeData = Object.entries(stats.cause_breakdown).map(([name, value]) => ({
    name, value
  }))

  const totalFeedback = stats.fixes_accepted + stats.fixes_rejected

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Flaky test detection and auto-healing overview</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Active Flaky Tests"
          value={stats.active_flaky_tests}
          sub={`of ${stats.total_flaky_tests} detected`}
          icon={<AlertTriangle size={24} />}
          color="text-amber-400"
        />
        <StatCard
          label="Total Test Runs"
          value={stats.total_test_runs.toLocaleString()}
          sub={`across ${stats.total_repos} repos`}
          icon={<Activity size={24} />}
          color="text-sky-400"
        />
        <StatCard
          label="Fix Proposals"
          value={stats.fixes_proposed}
          sub={`${stats.fixes_accepted} accepted`}
          icon={<GitPullRequest size={24} />}
          color="text-purple-400"
        />
        <StatCard
          label="Acceptance Rate"
          value={totalFeedback > 0 ? `${Math.round(stats.acceptance_rate * 100)}%` : 'N/A'}
          sub={totalFeedback > 0 ? `${stats.fixes_accepted}✓ / ${stats.fixes_rejected}✗` : 'No feedback yet'}
          icon={<CheckCircle size={24} />}
          color={stats.acceptance_rate > 0.7 ? 'text-green-400' : 'text-yellow-400'}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trend chart */}
        <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white">Test Run Trends</h2>
            <div className="flex gap-1">
              {DAYS_OPTIONS.map(d => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-2 py-1 text-xs rounded ${days === d ? 'bg-sky-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>
          {trends.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-gray-600 text-sm">
              No data for selected period. Ingest some test events first.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={trends.map(t => ({
                ...t,
                day: new Date(t.day).toLocaleDateString('en', { month: 'short', day: 'numeric' }),
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="day" tick={{ fill: '#6b7280', fontSize: 11 }} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#f3f4f6' }}
                />
                <Legend />
                <Line type="monotone" dataKey="total_runs" stroke="#0ea5e9" name="Total Runs" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="failed_runs" stroke="#ef4444" name="Failed" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Cause breakdown pie */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-4">Root Cause Breakdown</h2>
          {causeData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-gray-600 text-sm">
              No classifications yet
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie
                    data={causeData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    dataKey="value"
                    paddingAngle={2}
                  >
                    {causeData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={CAUSE_PIE_COLORS[entry.name] || '#6b7280'}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1 mt-2">
                {causeData.map(({ name, value }) => (
                  <div key={name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ background: CAUSE_PIE_COLORS[name] || '#6b7280' }}
                      />
                      <CauseBadge cause={name as CauseType} />
                    </div>
                    <span className="text-gray-400 font-mono">{value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Top flaky tests */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl">
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-white">Top Flaky Tests</h2>
          <Link to="/flaky-tests" className="text-xs text-sky-400 hover:underline">View all →</Link>
        </div>
        <div className="divide-y divide-gray-800">
          {stats.top_flaky_tests.length === 0 && (
            <p className="p-6 text-center text-gray-600 text-sm">
              No flaky tests detected yet. Try ingesting some events.
            </p>
          )}
          {stats.top_flaky_tests.slice(0, 8).map(test => (
            <Link
              key={test.id}
              to={`/flaky-tests/${test.id}`}
              className="flex items-center gap-4 p-4 hover:bg-gray-800/50 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-gray-200 truncate" title={test.test_name}>
                  {test.test_name.split('::').pop()}
                </p>
                <p className="text-xs text-gray-500 truncate">{test.repo}</p>
              </div>
              <div className="w-32 hidden sm:block">
                <ScoreBar score={test.flakiness_score} size="sm" />
              </div>
              <CauseBadge cause={test.primary_cause} />
              <span className="text-xs text-gray-500 w-16 text-right hidden md:block">
                {test.total_runs} runs
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}