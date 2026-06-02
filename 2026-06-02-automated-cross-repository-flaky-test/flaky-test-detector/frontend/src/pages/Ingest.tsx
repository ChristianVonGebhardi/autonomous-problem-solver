import { useState } from 'react'
import { api } from '../api'
import { CheckCircle, AlertTriangle, Send, RefreshCw } from 'lucide-react'

const EXAMPLE_EVENTS = [
  {
    label: '⏱ Timing failure',
    event: {
      repo: 'acme/backend-api',
      branch: 'main',
      commit_sha: 'abc123def456',
      pipeline_id: 'run-demo-001',
      test_name: 'tests/test_payments.py::TestPayments::test_webhook_processing',
      test_file: 'tests/test_payments.py',
      test_class: 'TestPayments',
      status: 'failed',
      duration_ms: 5200,
      log_output: 'TimeoutError: Expected webhook callback within 2000ms but timed out after 5200ms',
      error_message: 'Webhook delivery took 5200ms, exceeded timeout of 2000ms',
      ci_system: 'github_actions',
    },
  },
  {
    label: '🔀 Concurrency failure',
    event: {
      repo: 'acme/backend-api',
      branch: 'main',
      commit_sha: 'def456abc789',
      pipeline_id: 'run-demo-002',
      test_name: 'tests/test_auth.py::TestAuth::test_user_login_concurrent',
      test_file: 'tests/test_auth.py',
      test_class: 'TestAuth',
      status: 'failed',
      duration_ms: 1800,
      log_output: 'ThreadSanitizer: data race on shared session counter. concurrent access: multiple threads writing to session_store',
      error_message: 'ThreadSanitizer: data race detected',
      ci_system: 'github_actions',
    },
  },
  {
    label: '🌐 Environment failure',
    event: {
      repo: 'acme/data-pipeline',
      branch: 'main',
      commit_sha: 'ghi789jkl012',
      pipeline_id: 'run-demo-003',
      test_name: 'tests/test_ingestion.py::TestIngestion::test_kafka_consumer',
      test_file: 'tests/test_ingestion.py',
      test_class: 'TestIngestion',
      status: 'error',
      duration_ms: 300,
      log_output: 'NoBrokersAvailable: Unable to connect to kafka broker localhost:9092',
      error_message: 'kafka.errors.NoBrokersAvailable: NoBrokersAvailable',
      ci_system: 'gitlab_ci',
    },
  },
  {
    label: '💧 State leakage failure',
    event: {
      repo: 'acme/frontend-web',
      branch: 'main',
      commit_sha: 'mno345pqr678',
      pipeline_id: 'run-demo-004',
      test_name: 'tests/unit/test_store.py::TestStore::test_cart_state',
      test_file: 'tests/unit/test_store.py',
      test_class: 'TestStore',
      status: 'failed',
      duration_ms: 450,
      log_output: 'AssertionError: Cart has 3 items, expected 1. Previous test left items in global store.',
      error_message: 'global state leakage: store not reset between test modules',
      ci_system: 'github_actions',
    },
  },
  {
    label: '✅ Passing test',
    event: {
      repo: 'acme/backend-api',
      branch: 'main',
      commit_sha: 'stu901vwx234',
      pipeline_id: 'run-demo-005',
      test_name: 'tests/test_auth.py::TestAuth::test_user_login_concurrent',
      test_file: 'tests/test_auth.py',
      test_class: 'TestAuth',
      status: 'passed',
      duration_ms: 850,
      log_output: 'All assertions passed.',
      ci_system: 'github_actions',
    },
  },
]

function CodeEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <textarea
      className="w-full h-72 font-mono text-xs bg-gray-950 border border-gray-700 rounded-lg p-4 text-green-300 focus:outline-none focus:border-sky-500 resize-none leading-relaxed"
      value={value}
      onChange={e => onChange(e.target.value)}
      spellCheck={false}
    />
  )
}

export default function Ingest() {
  const [raw, setRaw] = useState(JSON.stringify(EXAMPLE_EVENTS[0].event, null, 2))
  const [response, setResponse] = useState<{ run_id?: number; status?: string; error?: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [batchMode, setBatchMode] = useState(false)
  const [batchCount, setBatchCount] = useState(5)

  const handleExampleSelect = (example: typeof EXAMPLE_EVENTS[0]) => {
    setRaw(JSON.stringify(example.event, null, 2))
    setResponse(null)
  }

  const handleSubmit = async () => {
    setLoading(true)
    setResponse(null)
    try {
      const parsed = JSON.parse(raw)
      const result = await api.ingestEvent(parsed)
      setResponse(result as { run_id?: number; status?: string })
    } catch (e: unknown) {
      setResponse({ error: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  const handleBatchIngest = async () => {
    setLoading(true)
    setResponse(null)
    try {
      const base = JSON.parse(raw)
      const statuses = ['passed', 'failed', 'passed', 'failed', 'passed', 'error', 'passed', 'failed', 'passed', 'passed']
      const events = Array.from({ length: batchCount }, (_, i) => ({
        ...base,
        status: statuses[i % statuses.length],
        commit_sha: `batch_sha_${Date.now()}_${i}`,
        pipeline_id: `batch_pipeline_${Date.now()}_${i}`,
      }))
      const result = await api.ingestEvent({ ...events[0] })
      for (let i = 1; i < events.length; i++) {
        await api.ingestEvent(events[i])
      }
      setResponse({ status: `Ingested ${batchCount} events. Check flaky tests after a moment.`, run_id: undefined })
    } catch (e: unknown) {
      setResponse({ error: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  const isValidJson = (() => {
    try { JSON.parse(raw); return true } catch { return false }
  })()

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Ingest Test Event</h1>
        <p className="text-gray-500 text-sm mt-1">
          Send a test execution event to the ingestion pipeline. Events are analyzed for flakiness and root cause.
        </p>
      </div>

      {/* Quick examples */}
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Quick Examples</p>
        <div className="flex gap-2 flex-wrap">
          {EXAMPLE_EVENTS.map((ex, i) => (
            <button
              key={i}
              onClick={() => handleExampleSelect(ex)}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-300 transition-colors border border-gray-700 hover:border-gray-600"
            >
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      {/* Editor */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Event JSON</p>
          {!isValidJson && (
            <span className="text-xs text-red-400 flex items-center gap-1">
              <AlertTriangle size={12} /> Invalid JSON
            </span>
          )}
        </div>
        <CodeEditor value={raw} onChange={v => { setRaw(v); setResponse(null) }} />
      </div>

      {/* Schema Reference */}
      <details className="bg-gray-900 border border-gray-800 rounded-xl">
        <summary className="px-5 py-4 text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
          Event Schema Reference
        </summary>
        <div className="px-5 pb-5">
          <table className="w-full text-xs mt-2">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-2 pr-4">Field</th>
                <th className="text-left py-2 pr-4">Type</th>
                <th className="text-left py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {[
                ['repo', 'string*', 'Repository full name (org/repo)'],
                ['test_name', 'string*', 'Fully qualified test identifier'],
                ['status', 'string*', 'passed | failed | error | skipped'],
                ['branch', 'string', 'Branch name (default: main)'],
                ['commit_sha', 'string', 'Git commit SHA'],
                ['pipeline_id', 'string', 'CI pipeline/run ID'],
                ['test_file', 'string', 'Path to test file'],
                ['test_class', 'string', 'Test class name'],
                ['duration_ms', 'integer', 'Test duration in milliseconds'],
                ['log_output', 'string', 'Full test log output'],
                ['error_message', 'string', 'Error message if failed'],
                ['stack_trace', 'string', 'Stack trace if failed'],
                ['ci_system', 'string', 'github_actions | gitlab_ci | jenkins | circleci'],
              ].map(([field, type, desc]) => (
                <tr key={field}>
                  <td className="py-2 pr-4 font-mono text-sky-400">{field}</td>
                  <td className="py-2 pr-4 text-amber-400">{type}</td>
                  <td className="py-2 text-gray-400">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {/* Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={handleSubmit}
          disabled={!isValidJson || loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 rounded-lg text-sm text-white font-medium transition-colors"
        >
          {loading ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
          {loading ? 'Sending...' : 'Send Event'}
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={handleBatchIngest}
            disabled={!isValidJson || loading}
            className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-sm text-gray-300 transition-colors border border-gray-700"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Batch Ingest
          </button>
          <select
            value={batchCount}
            onChange={e => setBatchCount(parseInt(e.target.value))}
            className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-2 text-sm text-gray-300 focus:outline-none"
          >
            {[5, 10, 15, 20, 30].map(n => (
              <option key={n} value={n}>{n} events</option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <p className="text-xs text-gray-500 mb-2 font-medium">How it works</p>
        <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
          <li>Event is validated and stored in the database</li>
          <li>Pushed to <code className="text-sky-400">test_events_queue</code> in Redis</li>
          <li>Flakiness worker analyzes run history with KS-test and RLE statistics</li>
          <li>If flaky: root-cause classifier categorizes the failure (timing / concurrency / environment / state leakage)</li>
          <li>Fix synthesis job is queued → LLM generates a targeted patch</li>
          <li>Fix proposal appears in the <a href="/fixes" className="text-sky-400 hover:underline">Fix Proposals</a> page</li>
        </ol>
      </div>

      {/* Response */}
      {response && (
        <div className={`rounded-xl p-4 border ${
          response.error
            ? 'bg-red-900/20 border-red-700/40'
            : 'bg-green-900/20 border-green-700/40'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            {response.error
              ? <AlertTriangle size={14} className="text-red-400" />
              : <CheckCircle size={14} className="text-green-400" />
            }
            <p className={`text-sm font-medium ${response.error ? 'text-red-300' : 'text-green-300'}`}>
              {response.error ? 'Error' : 'Success'}
            </p>
          </div>
          <pre className="text-xs font-mono text-gray-300 overflow-x-auto">
            {JSON.stringify(response, null, 2)}
          </pre>
          {!response.error && (
            <p className="text-xs text-gray-500 mt-2">
              Event queued for analysis. Use "Batch Ingest" with the same test to trigger flakiness detection (needs {'>'}3 runs).
            </p>
          )}
        </div>
      )}
    </div>
  )
}