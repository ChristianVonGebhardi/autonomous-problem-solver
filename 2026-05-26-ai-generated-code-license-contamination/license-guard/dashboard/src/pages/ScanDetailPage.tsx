import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import RiskBadge from '../components/RiskBadge'
import { ArrowLeft, Wrench, RefreshCw } from 'lucide-react'

export default function ScanDetailPage() {
  const { scanId } = useParams<{ scanId: string }>()
  const [showRemediation, setShowRemediation] = useState(false)

  const { data: scan, isLoading, refetch } = useQuery({
    queryKey: ['scan', scanId],
    queryFn: () => api.getScan(scanId!),
    refetchInterval: (data) =>
      data?.status === 'pending' || data?.status === 'processing' ? 2000 : false,
  })

  const remediateMutation = useMutation({
    mutationFn: (matchId?: string) => api.remediate(scanId!, matchId),
    onSuccess: () => setShowRemediation(true),
  })

  if (isLoading) {
    return (
      <div className="p-8 flex justify-center">
        <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    )
  }

  if (!scan) {
    return (
      <div className="p-8 text-center text-gray-500">
        Scan not found.{' '}
        <Link to="/scans" className="text-blue-600 hover:underline">Back to list</Link>
      </div>
    )
  }

  const isPending = scan.status === 'pending' || scan.status === 'processing'

  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Back link */}
      <Link
        to="/scans"
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Scans
      </Link>

      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <RiskBadge tier={scan.risk_tier || 'unknown'} />
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                scan.status === 'completed' ? 'bg-green-100 text-green-700' :
                scan.status === 'failed' ? 'bg-red-100 text-red-700' :
                'bg-yellow-100 text-yellow-700'
              }`}>
                {isPending && <RefreshCw className="w-3 h-3 inline animate-spin mr-1" />}
                {scan.status}
              </span>
            </div>
            <h1 className="text-lg font-bold text-gray-900">
              Scan Report
            </h1>
            <p className="text-xs text-gray-400 font-mono mt-1">{scan.scan_id}</p>
          </div>
          {scan.matches.length > 0 && !remediateMutation.data && (
            <button
              onClick={() => remediateMutation.mutate(scan.matches[0]?.match_id)}
              disabled={remediateMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-50"
            >
              <Wrench className="w-4 h-4" />
              {remediateMutation.isPending ? 'Generating...' : 'Get Remediation'}
            </button>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-400 text-xs">Created</span>
            <p className="text-gray-700">{new Date(scan.created_at).toLocaleString()}</p>
          </div>
          {scan.completed_at && (
            <div>
              <span className="text-gray-400 text-xs">Completed</span>
              <p className="text-gray-700">{new Date(scan.completed_at).toLocaleString()}</p>
            </div>
          )}
          <div>
            <span className="text-gray-400 text-xs">Matches Found</span>
            <p className="font-semibold text-gray-700">{scan.matches.length}</p>
          </div>
        </div>

        {scan.recommendation && (
          <div className={`mt-4 p-3 rounded-lg text-sm ${
            scan.risk_tier === 'high' ? 'bg-red-50 text-red-700' :
            scan.risk_tier === 'medium' ? 'bg-yellow-50 text-yellow-700' :
            scan.risk_tier === 'low' ? 'bg-blue-50 text-blue-700' :
            'bg-green-50 text-green-700'
          }`}>
            {scan.recommendation}
          </div>
        )}
      </div>

      {/* Matches */}
      {scan.matches.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 mb-6">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">License Matches ({scan.matches.length})</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {scan.matches.map((match, idx) => (
              <div key={match.match_id} className="px-6 py-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <span className="text-gray-400 text-xs">#{idx + 1}</span>
                    <RiskBadge tier={match.license_risk_tier} />
                    <code className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded">
                      {match.license_spdx}
                    </code>
                    <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">
                      {match.match_type.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="text-sm font-semibold text-gray-700">
                    {Math.round(match.similarity_score * 100)}% similar
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span>Source: <strong>{match.source_repo || '—'}</strong></span>
                </div>

                {match.matched_snippet && (
                  <details className="mt-3">
                    <summary className="text-xs text-blue-600 cursor-pointer hover:underline">
                      View matched corpus snippet
                    </summary>
                    <pre className="mt-2 text-xs bg-gray-900 text-gray-300 p-3 rounded-lg overflow-auto max-h-40">
                      {match.matched_snippet}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No Matches */}
      {scan.status === 'completed' && scan.matches.length === 0 && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
          <p className="text-green-700 font-medium">✅ No license contamination detected</p>
          <p className="text-green-600 text-sm mt-1">This code appears to be clean.</p>
        </div>
      )}

      {/* Remediation */}
      {remediateMutation.data && (
        <div className="bg-white rounded-xl border border-purple-200 p-6">
          <h2 className="font-semibold text-purple-900 mb-3 flex items-center gap-2">
            <Wrench className="w-4 h-4" />
            Remediation Suggestion
          </h2>
          <p className="text-sm text-gray-600 whitespace-pre-wrap mb-4">
            {remediateMutation.data.explanation}
          </p>
          {remediateMutation.data.suggested_code && (
            <>
              <h3 className="text-sm font-medium text-gray-700 mb-2">Suggested Replacement:</h3>
              <pre className="text-xs bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-64">
                {remediateMutation.data.suggested_code}
              </pre>
            </>
          )}
          <p className="mt-3 text-xs text-gray-400">
            Remediation ID: {remediateMutation.data.remediation_id}
          </p>
        </div>
      )}

      {/* Pending state */}
      {isPending && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6 text-center">
          <RefreshCw className="w-6 h-6 animate-spin text-yellow-600 mx-auto mb-2" />
          <p className="text-yellow-700">Scan in progress... auto-refreshing</p>
          <button onClick={() => refetch()} className="mt-2 text-sm text-yellow-600 hover:underline">
            Refresh now
          </button>
        </div>
      )}
    </div>
  )
}