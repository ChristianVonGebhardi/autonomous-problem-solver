import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { Database, RefreshCw } from 'lucide-react'
import RiskBadge from '../components/RiskBadge'

const TIER_COLORS: Record<string, string> = {
  high: 'bg-red-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-500',
  unknown: 'bg-gray-400',
}

export default function CorpusPage() {
  const { data: stats, isLoading, refetch } = useQuery({
    queryKey: ['corpus-stats'],
    queryFn: api.getCorpusStats,
  })

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">FOSS Corpus</h1>
          <p className="text-gray-500 text-sm mt-1">
            Known open-source code snippets used for license contamination detection
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="p-2 border border-gray-200 rounded-lg text-gray-500 hover:bg-gray-50"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center p-12">
          <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
        </div>
      ) : stats ? (
        <div className="space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-3 mb-2">
                <Database className="w-5 h-5 text-blue-500" />
                <span className="font-medium text-gray-700">Total Snippets</span>
              </div>
              <p className="text-3xl font-bold text-gray-900">{stats.total_snippets}</p>
            </div>

            {stats.by_risk_tier.map(({ tier, count }) => (
              <div key={tier} className="bg-white rounded-xl border border-gray-200 p-5">
                <div className="flex items-center gap-3 mb-2">
                  <RiskBadge tier={tier} />
                </div>
                <p className="text-3xl font-bold text-gray-900">{count}</p>
                <p className="text-xs text-gray-400 mt-1">snippets</p>
              </div>
            ))}
          </div>

          {/* License breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="font-semibold text-gray-900 mb-4">Licenses in Corpus</h2>
            <div className="space-y-3">
              {stats.top_licenses.map(({ license, count }) => {
                const maxCount = Math.max(...stats.top_licenses.map(l => l.count))
                const pct = Math.round((count / maxCount) * 100)
                return (
                  <div key={license} className="flex items-center gap-3">
                    <code className="text-xs font-mono w-36 text-gray-700 flex-shrink-0">{license}</code>
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 w-8 text-right">{count}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* About */}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-sm text-blue-800">
            <h3 className="font-semibold mb-2">About the Corpus</h3>
            <p className="text-blue-700">
              The LicenseGuard corpus contains representative code snippets from popular open-source 
              projects indexed with their SPDX license identifiers. Snippets are fingerprinted using 
              MinHash signatures and semantic embeddings for fast similarity comparison.
            </p>
            <p className="mt-2 text-blue-600 text-xs">
              In production, the corpus is populated from GitHub BigQuery public datasets and SPDX license DB, 
              updated nightly via an ETL pipeline.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  )
}