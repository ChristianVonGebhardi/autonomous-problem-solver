import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import StatCard from '../components/StatCard'
import RiskBadge from '../components/RiskBadge'
import { Link } from 'react-router-dom'
import { AlertCircle, RefreshCw } from 'lucide-react'

export default function Dashboard() {
  const { data: stats, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 60_000,
  })

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-2" />
          <p className="text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-700">Cannot connect to API</h3>
            <p className="text-red-600 text-sm mt-1">
              Make sure the backend is running: <code className="bg-red-100 px-1 rounded">docker compose up -d</code>
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!stats) return null

  const totalRisky = stats.high_risk_count + stats.medium_risk_count + stats.low_risk_count
  const riskRate = stats.total_scans > 0
    ? Math.round((totalRisky / stats.total_scans) * 100)
    : 0

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Compliance Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">License contamination overview</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          title="Total Scans"
          value={stats.total_scans}
          subtitle="completed"
          icon="🔍"
        />
        <StatCard
          title="High Risk"
          value={stats.high_risk_count}
          subtitle="require immediate action"
          color="red"
          icon="⚠️"
        />
        <StatCard
          title="Medium Risk"
          value={stats.medium_risk_count}
          subtitle="need review"
          color="yellow"
          icon="⚡"
        />
        <StatCard
          title="Clean"
          value={stats.clean_count}
          subtitle="no contamination"
          color="green"
          icon="✅"
        />
      </div>

      {/* Risk Rate Banner */}
      {stats.total_scans > 0 && (
        <div className={`rounded-xl p-4 mb-8 border ${
          riskRate > 30 ? 'bg-red-50 border-red-200' :
          riskRate > 10 ? 'bg-yellow-50 border-yellow-200' :
          'bg-green-50 border-green-200'
        }`}>
          <p className="text-sm font-medium">
            <strong>{riskRate}%</strong> of scanned code had license contamination issues
            {riskRate > 30 && ' — above industry average of 35%'}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
        {/* Risk Trend Chart */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Risk Trend (Last 7 Days)</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stats.risk_trend} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="high" name="High" fill="#ef4444" stackId="a" />
              <Bar dataKey="medium" name="Medium" fill="#f59e0b" stackId="a" />
              <Bar dataKey="low" name="Low" fill="#3b82f6" stackId="a" />
              <Bar dataKey="clean" name="Clean" fill="#22c55e" stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Top Licenses */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Top Detected Licenses</h2>
          {stats.top_licenses.length === 0 ? (
            <p className="text-gray-400 text-sm">No matches yet. Run some scans.</p>
          ) : (
            <div className="space-y-3">
              {stats.top_licenses.slice(0, 8).map((l, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <RiskBadge tier={l.tier} />
                    <span className="text-sm font-mono text-gray-700">{l.license}</span>
                  </div>
                  <span className="text-sm text-gray-500">{l.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Scans */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Recent Scans</h2>
          <Link to="/scans" className="text-blue-600 text-sm hover:underline">
            View all →
          </Link>
        </div>
        {stats.recent_scans.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            <p className="mb-2">No scans yet.</p>
            <Link to="/scan" className="text-blue-600 hover:underline text-sm">
              Run your first scan →
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {stats.recent_scans.map((scan) => (
              <Link
                key={scan.scan_id}
                to={`/scans/${scan.scan_id}`}
                className="flex items-center gap-4 px-6 py-3 hover:bg-gray-50 transition-colors"
              >
                <RiskBadge tier={scan.risk_tier} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {scan.filename || 'unknown file'}
                  </p>
                  <p className="text-xs text-gray-400">
                    {scan.language} • {scan.source} • {scan.match_count} matches
                  </p>
                </div>
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  {new Date(scan.created_at).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}