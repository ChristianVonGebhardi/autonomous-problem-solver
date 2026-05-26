import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { Link } from 'react-router-dom'
import RiskBadge from '../components/RiskBadge'
import { RefreshCw, Filter } from 'lucide-react'

const RISK_TIERS = ['', 'high', 'medium', 'low', 'clean', 'unknown']
const STATUSES = ['', 'completed', 'pending', 'processing', 'failed']

export default function ScansListPage() {
  const [riskTier, setRiskTier] = useState('')
  const [status, setStatus] = useState('completed')

  const { data: scans, isLoading, refetch } = useQuery({
    queryKey: ['scans', riskTier, status],
    queryFn: () => api.listScans({
      risk_tier: riskTier || undefined,
      status: status || undefined,
      limit: 100,
    }),
    refetchInterval: 15_000,
  })

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Scan History</h1>
          <p className="text-gray-500 text-sm mt-1">All license contamination scans</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/scan"
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
          >
            + New Scan
          </Link>
          <button
            onClick={() => refetch()}
            className="p-2 border border-gray-200 rounded-lg text-gray-500 hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6">
        <Filter className="w-4 h-4 text-gray-400" />
        <select
          value={riskTier}
          onChange={(e) => setRiskTier(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm"
        >
          <option value="">All Risk Tiers</option>
          {RISK_TIERS.filter(Boolean).map((t) => (
            <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All Statuses'}</option>
          ))}
        </select>
        <span className="text-sm text-gray-400">
          {scans?.length ?? 0} results
        </span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              <th className="px-4 py-3 text-left font-medium text-gray-500">Risk</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">File</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Language</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Source</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Matches</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">Date</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />
                  Loading...
                </td>
              </tr>
            ) : scans?.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  No scans found.{' '}
                  <Link to="/scan" className="text-blue-600 hover:underline">
                    Run a scan
                  </Link>
                </td>
              </tr>
            ) : (
              scans?.map((scan) => (
                <tr key={scan.scan_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <RiskBadge tier={scan.risk_tier || 'unknown'} />
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-gray-700 max-w-xs truncate block">
                      {scan.filename || '—'}
                    </span>
                    <span className="text-xs text-gray-400 font-mono">{scan.scan_id.slice(0, 8)}...</span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{scan.language || '—'}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                      {scan.source}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`font-medium ${scan.match_count > 0 ? 'text-red-600' : 'text-gray-400'}`}>
                      {scan.match_count}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      scan.status === 'completed' ? 'bg-green-100 text-green-700' :
                      scan.status === 'failed' ? 'bg-red-100 text-red-700' :
                      'bg-yellow-100 text-yellow-700'
                    }`}>
                      {scan.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {new Date(scan.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/scans/${scan.scan_id}`}
                      className="text-blue-600 text-xs hover:underline"
                    >
                      Details →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}