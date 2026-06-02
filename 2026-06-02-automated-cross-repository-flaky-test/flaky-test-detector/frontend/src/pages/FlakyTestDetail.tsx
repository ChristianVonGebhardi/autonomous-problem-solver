import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Zap, GitPullRequest, Clock, CheckCircle, XCircle } from 'lucide-react'
import { api, type FlakyTestDetail, type FixProposal, type Analysis } from '../api'
import { CauseBadge } from '../components/CauseBadge'
import { ScoreBar } from '../components/ScoreBar'

function RunDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    passed: 'bg-green-500',
    failed: 'bg-red-500',
    error: 'bg-orange-500',
    skipped: 'bg-gray-500',
  }
  return (
    <div
      className={`w-3 h-3 rounded-sm ${colors[status] || 'bg-gray-600'}`}
      title={status}
    />
  )
}

export default function FlakyTestDetailPage() {
  const { id } = useParams<{ id: string }>()
  const testId = parseInt(id!)
  const [test, setTest] = useState<FlakyTestDetail | null>(null)
  const [fixes, setFixes] = useState<FixProposal[]>([])
  const [analyses, setAnalyses] = useState<Analysis[]>([])
  const [loading, setLoading] = useState(true)
  const [triggeringFix, setTriggeringFix] = useState(false)

  useEffect(() => {
    Promise.all([
      api.flakyTest(testId),
      api.fixes({ flaky_test_id: testId }),
      api.analyses(testId),
    ]).then(([t, f, a]) => {
      setTest(t)
      setFixes(f.items)
      setAnalyses(a.items)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [testId])

  const handleTriggerFix = async () => {
    setTriggeringFix(true)
    try {
      await api.triggerFix(testId)
      alert('Fix synthesis queued! Check the Fix Proposals page in a few seconds.')
    } catch (e: unknown) {
      alert('Failed: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setTriggeringFix(false)
    }
  }

  if (loading) return <div className="text-gray-500 py-12 text-center">Loading...</div>
  if (!test) return <div className="text-red-400 py-12 text-center">Test not found</div>

  const latestAnalysis = analyses[0]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/flaky-tests" className="text-gray-500 hover:text-white">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-bold text-white font-mono truncate" title={test.test_name}>
            {test.test_name}
          </h1>
          <p className="text-xs text-gray-500">{test.repo} · {test.test_file}</p>
        </div>
        <button
          onClick={handleTriggerFix}
          disabled={triggeringFix}
          className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
        >
          <Zap size={14} />
          {triggeringFix ? 'Queuing...' : 'Generate Fix'}
        </button>
      </div>

      {/* Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Flakiness Score</p>
          <p className="text-2xl font-bold text-amber-400">{Math.round(test.flakiness_score * 100)}%</p>
          <ScoreBar score={test.flakiness_score} size="sm" />
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Pass Rate</p>
          <p className="text-2xl font-bold text-green-400">
            {test.pass_rate != null ? `${Math.round(test.pass_rate * 100)}%` : 'N/A'}
          </p>
          <p className="text-xs text-gray-500">{test.total_runs} total runs</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Root Cause</p>
          <div className="mt-1">
            <CauseBadge cause={latestAnalysis?.primary_cause} />
          </div>
          {latestAnalysis && (
            <p className="text-xs text-gray-500 mt-1">
              {Math.round(latestAnalysis.confidence * 100)}% confidence
            </p>
          )}
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-xs text-gray-500 mb-1">Fix Proposals</p>
          <p className="text-2xl font-bold text-purple-400">{fixes.length}</p>
          <p className="text-xs text-gray-500">
            {fixes.filter(f => f.status === 'accepted').length} accepted
          </p>
        </div>
      </div>

      {/* Run History */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-white mb-3">
          Run History (last {test.recent_runs.length} runs)
        </h2>
        <div className="flex flex-wrap gap-1">
          {[...test.recent_runs].reverse().map((run, i) => (
            <RunDot key={run.id || i} status={run.status} />
          ))}
        </div>
        <div className="flex gap-4 mt-3 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-green-500 rounded-sm inline-block" /> Passed</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-red-500 rounded-sm inline-block" /> Failed</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-orange-500 rounded-sm inline-block" /> Error</span>
        </div>

        {/* Recent failures */}
        {test.recent_runs.filter(r => r.status !== 'passed').slice(0, 3).length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-gray-500 font-medium">Recent Failures</p>
            {test.recent_runs.filter(r => r.status !== 'passed').slice(0, 3).map((run, i) => (
              <div key={i} className="bg-gray-800 rounded-lg p-3 text-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-red-400 font-medium">{run.status}</span>
                  <span className="text-gray-500">{new Date(run.created_at).toLocaleDateString()}</span>
                </div>
                {run.error_message && (
                  <p className="text-gray-300 font-mono break-all">{run.error_message}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Root Cause Analysis */}
      {latestAnalysis && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-3">Root Cause Analysis</h2>
          <div className="flex items-center gap-3 mb-3">
            <CauseBadge cause={latestAnalysis.primary_cause} />
            <span className="text-xs text-gray-400">
              {Math.round(latestAnalysis.confidence * 100)}% confidence
              · {latestAnalysis.classifier_version}
            </span>
          </div>
          {latestAnalysis.secondary_causes && latestAnalysis.secondary_causes.length > 0 && (
            <div className="mb-3">
              <p className="text-xs text-gray-500 mb-1">Secondary causes</p>
              <div className="flex gap-2 flex-wrap">
                {latestAnalysis.secondary_causes.map((sc, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <CauseBadge cause={sc.cause} />
                    <span className="text-xs text-gray-500">{Math.round(sc.confidence * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {latestAnalysis.evidence && (
            <details className="text-xs">
              <summary className="text-gray-500 cursor-pointer hover:text-gray-300">
                Evidence details
              </summary>
              <pre className="mt-2 bg-gray-800 rounded p-3 text-gray-300 overflow-x-auto">
                {JSON.stringify(latestAnalysis.evidence, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Fix Proposals */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl">
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-white">Fix Proposals</h2>
        </div>
        {fixes.length === 0 ? (
          <p className="p-6 text-center text-gray-600 text-sm">
            No fix proposals yet. Click "Generate Fix" to trigger synthesis.
          </p>
        ) : (
          <div className="divide-y divide-gray-800">
            {fixes.map(fix => (
              <Link key={fix.id} to={`/fixes/${fix.id}`} className="flex items-center gap-4 p-4 hover:bg-gray-800/50 transition-colors">
                <GitPullRequest size={16} className="text-purple-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      fix.status === 'accepted' ? 'bg-green-900 text-green-300' :
                      fix.status === 'rejected' ? 'bg-red-900 text-red-300' :
                      fix.status === 'proposed' ? 'bg-purple-900 text-purple-300' :
                      'bg-gray-700 text-gray-400'
                    }`}>
                      {fix.status}
                    </span>
                    <CauseBadge cause={fix.root_cause} />
                  </div>
                  <p className="text-xs text-gray-400 truncate">{fix.explanation?.slice(0, 100)}...</p>
                </div>
                {fix.pr_url && (
                  <span className="text-xs text-sky-400">PR #{fix.pr_number}</span>
                )}
                {fix.confidence && (
                  <span className="text-xs text-gray-500">{Math.round(fix.confidence * 100)}%</span>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}