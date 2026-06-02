import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink, CheckCircle, XCircle, GitPullRequest, Code } from 'lucide-react'
import { api, type FixProposal } from '../api'
import { CauseBadge } from '../components/CauseBadge'

const STATUS_STYLES: Record<string, string> = {
  proposed: 'bg-purple-900/60 text-purple-300 border border-purple-700/40',
  accepted: 'bg-green-900/60 text-green-300 border border-green-700/40',
  rejected: 'bg-red-900/60 text-red-300 border border-red-700/40',
  pending: 'bg-gray-700 text-gray-400 border border-gray-600',
  synthesizing: 'bg-sky-900/60 text-sky-300 border border-sky-700/40',
  applied: 'bg-teal-900/60 text-teal-300 border border-teal-700/40',
}

function DiffView({ diff }: { diff: string }) {
  if (!diff) return <p className="text-gray-600 text-sm italic">No patch available</p>

  return (
    <div className="font-mono text-xs overflow-x-auto">
      {diff.split('\n').map((line, i) => {
        let cls = 'text-gray-400'
        if (line.startsWith('+++') || line.startsWith('---')) cls = 'text-gray-300 font-semibold'
        else if (line.startsWith('+')) cls = 'text-green-400 bg-green-900/20'
        else if (line.startsWith('-')) cls = 'text-red-400 bg-red-900/20'
        else if (line.startsWith('@@')) cls = 'text-sky-400 bg-sky-900/20'
        return (
          <div key={i} className={`px-3 py-0.5 whitespace-pre ${cls}`}>
            {line || ' '}
          </div>
        )
      })}
    </div>
  )
}

export default function FixDetail() {
  const { id } = useParams<{ id: string }>()
  const fixId = parseInt(id!)
  const navigate = useNavigate()
  const [fix, setFix] = useState<FixProposal | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [feedbackNote, setFeedbackNote] = useState('')
  const [feedbackDone, setFeedbackDone] = useState(false)

  useEffect(() => {
    api.fix(fixId)
      .then(f => { setFix(f); setLoading(false) })
      .catch(() => setLoading(false))
  }, [fixId])

  const handleFeedback = async (accepted: boolean) => {
    if (!fix) return
    setSubmitting(true)
    try {
      await api.feedback(fixId, accepted, feedbackNote || undefined)
      setFix(prev => prev ? {
        ...prev,
        status: accepted ? 'accepted' : 'rejected',
        feedback_accepted: accepted,
      } : prev)
      setFeedbackDone(true)
    } catch (e: unknown) {
      alert('Failed to submit feedback: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="text-gray-500 py-12 text-center">Loading...</div>
  if (!fix) return (
    <div className="text-red-400 py-12 text-center">
      Fix proposal not found.{' '}
      <Link to="/fixes" className="text-sky-400 hover:underline">Back to fixes</Link>
    </div>
  )

  const hasFeedback = fix.feedback_accepted !== null && fix.feedback_accepted !== undefined

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Link to="/fixes" className="text-gray-500 hover:text-white mt-0.5">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded font-medium border ${STATUS_STYLES[fix.status] || 'bg-gray-700 text-gray-400 border-gray-600'}`}>
              {fix.status}
            </span>
            <CauseBadge cause={fix.root_cause} />
            {fix.confidence !== null && fix.confidence !== undefined && (
              <span className="text-xs text-gray-500">
                {Math.round(fix.confidence * 100)}% confidence
              </span>
            )}
            {fix.llm_model && (
              <span className="text-xs text-gray-600 bg-gray-800 px-2 py-0.5 rounded">
                {fix.llm_model}
              </span>
            )}
          </div>
          <h1 className="text-lg font-bold text-white font-mono truncate" title={fix.test_name}>
            {fix.test_name}
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            <Link to={`/flaky-tests/${fix.flaky_test_id}`} className="text-sky-400 hover:underline">
              {fix.repo}
            </Link>
            {' · '}
            {new Date(fix.created_at).toLocaleString()}
          </p>
        </div>
      </div>

      {/* PR Link */}
      {fix.pr_url && (
        <div className="bg-purple-900/20 border border-purple-700/40 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <GitPullRequest size={18} className="text-purple-400" />
            <div>
              <p className="text-sm font-medium text-white">Pull Request #{fix.pr_number}</p>
              <p className="text-xs text-gray-400">{fix.pr_url}</p>
            </div>
          </div>
          <a
            href={fix.pr_url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-700 hover:bg-purple-600 rounded-lg text-xs text-white transition-colors"
          >
            <ExternalLink size={12} />
            View PR
          </a>
        </div>
      )}

      {/* Explanation */}
      {fix.explanation && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-3">Analysis &amp; Explanation</h2>
          <p className="text-sm text-gray-300 leading-relaxed">{fix.explanation}</p>
        </div>
      )}

      {/* Affected Files */}
      {fix.affected_files && fix.affected_files.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Code size={14} />
            Affected Files
          </h2>
          <div className="space-y-1">
            {fix.affected_files.map((f, i) => (
              <span key={i} className="inline-block mr-2 mb-1 text-xs font-mono bg-gray-800 text-gray-300 px-2 py-1 rounded">
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Patch Diff */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Code size={14} />
            Proposed Patch
          </h2>
          {fix.patch_diff && (
            <button
              onClick={() => {
                navigator.clipboard.writeText(fix.patch_diff || '')
              }}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              Copy
            </button>
          )}
        </div>
        <div className="bg-gray-950 rounded-b-xl overflow-auto max-h-[500px]">
          <DiffView diff={fix.patch_diff || ''} />
        </div>
      </div>

      {/* Feedback Section */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-white mb-3">Developer Feedback</h2>

        {hasFeedback || feedbackDone ? (
          <div className={`flex items-center gap-3 p-4 rounded-lg ${
            fix.feedback_accepted
              ? 'bg-green-900/30 border border-green-700/40'
              : 'bg-red-900/30 border border-red-700/40'
          }`}>
            {fix.feedback_accepted
              ? <CheckCircle size={18} className="text-green-400" />
              : <XCircle size={18} className="text-red-400" />
            }
            <div>
              <p className={`text-sm font-medium ${fix.feedback_accepted ? 'text-green-300' : 'text-red-300'}`}>
                Fix {fix.feedback_accepted ? 'Accepted' : 'Rejected'}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                Thank you for your feedback. This helps improve future fix proposals.
              </p>
            </div>
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-400 mb-4">
              Review the proposed fix above. Your feedback trains the classifier to improve future proposals.
            </p>
            <textarea
              className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-sky-500 mb-4 resize-none"
              rows={3}
              placeholder="Optional: explain why you're accepting or rejecting this fix..."
              value={feedbackNote}
              onChange={e => setFeedbackNote(e.target.value)}
            />
            <div className="flex gap-3">
              <button
                onClick={() => handleFeedback(true)}
                disabled={submitting}
                className="flex items-center gap-2 px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 rounded-lg text-sm text-white font-medium transition-colors"
              >
                <CheckCircle size={14} />
                Accept Fix
              </button>
              <button
                onClick={() => handleFeedback(false)}
                disabled={submitting}
                className="flex items-center gap-2 px-4 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-50 rounded-lg text-sm text-white font-medium transition-colors"
              >
                <XCircle size={14} />
                Reject Fix
              </button>
              <Link
                to={`/flaky-tests/${fix.flaky_test_id}`}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
              >
                View Test
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  )
}