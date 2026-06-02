import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GitPullRequest, CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react'
import { api, type FixProposal } from '../api'
import { CauseBadge } from '../components/CauseBadge'

const STATUSES = ['proposed', 'accepted', 'rejected', 'pending', 'synthesizing']

const STATUS_STYLES: Record<string, string> = {
  proposed: 'bg-purple-900/60 text-purple-300',
  accepted: 'bg-green-900/60 text-green-300',
  rejected: 'bg-red-900/60 text-red-300',
  pending: 'bg-gray-700 text-gray-400',
  synthesizing: 'bg-sky-900/60 text-sky-300 animate-pulse',
}

export default function Fixes() {
  const [fixes, setFixes] = useState<FixProposal[]>([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.fixes({ status: status || undefined, limit: 50 }).then(r => {
      setFixes(r.items)
      setTotal(r.total)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [status])

  const accepted = fixes.filter(f => f.feedback_accepted === true).length
  const rejected = fixes.filter(f => f.feedback_accepted === false).length

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Fix Proposals</h1>
          <p className="text-gray-500 text-sm mt-1">
            {total} proposals · {accepted} accepted · {rejected} rejected
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setStatus('')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium ${!status ? 'bg-sky-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
        >
          All
        </button>
        {STATUSES.map(s => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium ${status === s ? 'bg-sky-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Fix cards */}
      <div className="space-y-3">
        {loading && <p className="text-center text-gray-600 py-12">Loading...</p>}
        {!loading && fixes.length === 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center text-gray-600">
            No fix proposals found.
          </div>
        )}
        {fixes.map(fix => (
          <Link
            key={fix.id}
            to={`/fixes/${fix.id}`}
            className="block bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-colors"
          >
            <div className="flex items-start gap-4">
              <GitPullRequest size={18} className="text-purple-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${STATUS_STYLES[fix.status] || 'bg-gray-700 text-gray-400'}`}>
                    {fix.status}
                  </span>
                  <CauseBadge cause={fix.root_cause} />
                  {fix.confidence && (
                    <span className="text-xs text-gray-500">
                      {Math.round(fix.confidence * 100)}% confidence
                    </span>
                  )}
                  {fix.llm_model && (
                    <span className="text-xs text-gray-600">{fix.llm_model}</span>
                  )}
                </div>
                <p className="text-sm font-mono text-gray-300 truncate">{fix.test_name}</p>
                <p className="text-xs text-gray-500 mt-0.5">{fix.repo}</p>
                {fix.explanation && (
                  <p className="text-xs text-gray-400 mt-2 line-clamp-2">{fix.explanation}</p>
                )}
              </div>
              <div className="text-right flex-shrink-0">
                {fix.pr_url ? (
                  <span className="text-xs text-sky-400">PR #{fix.pr_number}</span>
                ) : null}
                {fix.feedback_accepted === true && (
                  <div className="flex items-center gap-1 text-green-400 text-xs mt-1">
                    <CheckCircle size={12} /> Accepted
                  </div>
                )}
                {fix.feedback_accepted === false && (
                  <div className="flex items-center gap-1 text-red-400 text-xs mt-1">
                    <XCircle size={12} /> Rejected
                  </div>
                )}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}