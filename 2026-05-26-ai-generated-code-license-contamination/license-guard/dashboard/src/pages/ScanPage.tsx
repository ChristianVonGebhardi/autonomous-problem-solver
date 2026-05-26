import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, ScanResult } from '../api/client'
import RiskBadge from '../components/RiskBadge'
import { Search, Copy, CheckCircle, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const LANGUAGE_OPTIONS = [
  'python', 'javascript', 'typescript', 'go', 'java', 'c', 'cpp', 'rust', 'ruby', 'php', 'csharp',
]

const EXAMPLE_SNIPPETS = {
  'GPL heapsort (python)': `def heappush(heap, item):
    """Push item onto heap, maintaining the heap invariant."""
    heap.append(item)
    _siftdown(heap, 0, len(heap)-1)

def heappop(heap):
    """Pop the smallest item off the heap, maintaining the heap invariant."""
    lastelt = heap.pop()
    if heap:
        returnitem = heap[0]
        heap[0] = lastelt
        _siftup(heap, 0)
        return returnitem
    return lastelt`,

  'MIT debounce (javascript)': `function debounce(func, wait, options) {
  let lastArgs, lastThis, result, timerId, lastCallTime;
  let lastInvokeTime = 0;
  let leading = false;
  let trailing = true;

  if (typeof func !== 'function') {
    throw new TypeError('Expected a function');
  }
  wait = +wait || 0;

  function invokeFunc(time) {
    const args = lastArgs;
    const thisArg = lastThis;
    lastArgs = lastThis = undefined;
    lastInvokeTime = time;
    result = func.apply(thisArg, args);
    return result;
  }
  return invokeFunc;
}`,

  'Clean code (python)': `def calculate_tax(income: float, tax_rate: float = 0.2) -> float:
    """Calculate tax amount based on income and tax rate."""
    if income < 0:
        raise ValueError("Income cannot be negative")
    if not 0 <= tax_rate <= 1:
        raise ValueError("Tax rate must be between 0 and 1")
    return round(income * tax_rate, 2)`,
}

export default function ScanPage() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [language, setLanguage] = useState('')
  const [filename, setFilename] = useState('')
  const [result, setResult] = useState<ScanResult | null>(null)
  const [remediationRequested, setRemediationRequested] = useState(false)

  const scanMutation = useMutation({
    mutationFn: () => api.scan({
      code,
      language: language || undefined,
      source: 'api',
      filename: filename || undefined,
    }),
    onSuccess: (data) => setResult(data),
  })

  const remediateMutation = useMutation({
    mutationFn: () => api.remediate(result!.scan_id),
    onSuccess: () => setRemediationRequested(true),
  })

  const loadExample = (name: string) => {
    setCode(EXAMPLE_SNIPPETS[name as keyof typeof EXAMPLE_SNIPPETS])
    if (name.includes('python')) setLanguage('python')
    else if (name.includes('javascript')) setLanguage('javascript')
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Scan Code</h1>
        <p className="text-gray-500 text-sm mt-1">
          Paste code to check for open-source license contamination
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Input Panel */}
        <div>
          {/* Examples */}
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <span className="text-xs text-gray-500">Examples:</span>
            {Object.keys(EXAMPLE_SNIPPETS).map((name) => (
              <button
                key={name}
                onClick={() => loadExample(name)}
                className="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded hover:bg-blue-100"
              >
                {name}
              </button>
            ))}
          </div>

          {/* Code textarea */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Code Snippet
            </label>
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Paste your AI-generated code here..."
              className="w-full h-64 font-mono text-sm bg-gray-900 text-green-400 p-4 rounded-lg border border-gray-700 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              spellCheck={false}
            />
          </div>

          {/* Options */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              >
                <option value="">Auto-detect</option>
                {LANGUAGE_OPTIONS.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Filename (optional)</label>
              <input
                type="text"
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                placeholder="e.g. utils.py"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>

          {/* Scan Button */}
          <button
            onClick={() => {
              setResult(null)
              setRemediationRequested(false)
              scanMutation.mutate()
            }}
            disabled={!code.trim() || scanMutation.isPending}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {scanMutation.isPending ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Scanning...
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                Scan for License Contamination
              </>
            )}
          </button>

          {scanMutation.error && (
            <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
              Error: {String(scanMutation.error)}
            </div>
          )}
        </div>

        {/* Results Panel */}
        <div>
          {!result && !scanMutation.isPending && (
            <div className="h-full flex items-center justify-center text-gray-400 text-center">
              <div>
                <Search className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">Results will appear here after scanning</p>
              </div>
            </div>
          )}

          {result && (
            <div className="space-y-4">
              {/* Risk Summary */}
              <div className={`rounded-xl p-5 border-2 ${
                result.risk_tier === 'high' ? 'border-red-300 bg-red-50' :
                result.risk_tier === 'medium' ? 'border-yellow-300 bg-yellow-50' :
                result.risk_tier === 'low' ? 'border-blue-300 bg-blue-50' :
                'border-green-300 bg-green-50'
              }`}>
                <div className="flex items-center gap-3 mb-2">
                  <RiskBadge tier={result.risk_tier} className="text-sm" />
                  <span className="text-sm font-medium text-gray-700">
                    {result.matches.length} match{result.matches.length !== 1 ? 'es' : ''} found
                  </span>
                </div>
                <p className="text-sm text-gray-600">{result.recommendation}</p>
              </div>

              {/* Matches */}
              {result.matches.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <h3 className="font-medium text-gray-900 text-sm">License Matches</h3>
                  </div>
                  <div className="divide-y divide-gray-100">
                    {result.matches.map((match) => (
                      <div key={match.match_id} className="px-4 py-3">
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <RiskBadge tier={match.license_risk_tier} />
                            <code className="text-xs font-mono bg-gray-100 px-1.5 py-0.5 rounded">
                              {match.license_spdx}
                            </code>
                          </div>
                          <span className="text-xs text-gray-500">
                            {Math.round(match.similarity_score * 100)}% similar
                          </span>
                        </div>
                        <p className="text-xs text-gray-500">
                          {match.match_type.replace('_', ' ')} • {match.source_repo}
                        </p>
                        {match.matched_snippet && (
                          <details className="mt-2">
                            <summary className="text-xs text-blue-600 cursor-pointer hover:underline">
                              View matched snippet
                            </summary>
                            <pre className="mt-1 text-xs bg-gray-900 text-gray-300 p-2 rounded overflow-auto max-h-32">
                              {match.matched_snippet}
                            </pre>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => navigate(`/scans/${result.scan_id}`)}
                  className="flex-1 text-sm px-4 py-2 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50"
                >
                  View Full Report
                </button>
                {result.matches.length > 0 && !remediationRequested && (
                  <button
                    onClick={() => remediateMutation.mutate()}
                    disabled={remediateMutation.isPending}
                    className="flex-1 text-sm px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
                  >
                    {remediateMutation.isPending ? 'Getting suggestion...' : '🔧 Get Remediation'}
                  </button>
                )}
              </div>

              {/* Remediation Result */}
              {remediateMutation.data && (
                <div className="bg-white rounded-xl border border-purple-200 p-4">
                  <h3 className="font-medium text-purple-900 mb-2 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    Remediation Suggestion
                  </h3>
                  <p className="text-sm text-gray-600 whitespace-pre-wrap">
                    {remediateMutation.data.explanation}
                  </p>
                  {remediateMutation.data.suggested_code && (
                    <pre className="mt-3 text-xs bg-gray-900 text-green-400 p-3 rounded overflow-auto max-h-48">
                      {remediateMutation.data.suggested_code}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}