import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Filter, RefreshCw, Zap } from 'lucide-react'
import { api, type FlakyTestSummary, type CauseType } from '../api'
import { CauseBadge } from '../components/CauseBadge'
import { ScoreBar } from '../components/ScoreBar'

const CAUSES: CauseType[] = ['timing', 'concurrency', 'environment', 'state_leakage', 'unknown']
const PAGE_SIZE = 20

export default function FlakyTests() {
  const [tests, setTests] = useState<FlakyTestSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [causeFilter, setCauseFilter] = useState<CauseType | ''>('')
  const [search, setSearch] = useState('')

  const load = () => {
    setLoading(true)
    api.flakyTests({
      cause: causeFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    }).then(r => {
      setTests(r.items)
      setTotal(r.total)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [causeFilter, offset])

  const filtered = search
    ? tests.filter(t =>
        t.test_name.toLowerCase().includes(search.toLowerCase()) ||
        t.repo.toLowerCase().includes(search.toLowerCase())
      )
    : tests

  const pages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE)

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Flaky Tests</h1>
          <p className="text-gray-500 text-sm mt-1">{total} detected across all repositories</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-sky-500"
            placeholder="Search tests or repos..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-gray-500" />
          <div className="flex gap-1 flex-wrap">
            <button
              onClick={() => { setCauseFilter(''); setOffset(0) }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${causeFilter === '' ? 'bg-sky-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
            >
              All
            </button>
            {CAUSES.map(c => (
              <button
                key={c}
                onClick={() => { setCauseFilter(c); setOffset(0) }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${causeFilter === c ? 'bg-sky-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead className="border-b border-gray-800">
            <tr className="text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-4 py-3">Test</th>
              <th className="text-left px-4 py-3 hidden md:table-cell">Repository</th>
              <th className="text-left px-4 py-3">Flakiness</th>
              <th className="text-left px-4 py-3 hidden sm:table-cell">Root Cause</th>
              <th className="text-right px-4 py-3 hidden lg:table-cell">Runs</th>
              <th className="text-right px-4 py-3 hidden lg:table-cell">Fixes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading && (
              <tr><td colSpan={6} className="text-center py-12 text-gray-600">Loading...</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-12 text-gray-600">
                  No flaky tests found. Try seeding demo data or ingesting events.
                </td>
              </tr>
            )}
            {filtered.map(test => (
              <tr key={test.id} className="hover:bg-gray-800/50 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/flaky-tests/${test.id}`} className="group">
                    <p className="text-sm font-mono text-gray-200 group-hover:text-sky-400 truncate max-w-xs" title={test.test_name}>
                      {test.test_name.split('::').pop()}
                    </p>
                    <p className="text-xs text-gray-500 truncate md:hidden">{test.repo}</p>
                  </Link>
                </td>
                <td className="px-4 py-3 hidden md:table-cell">
                  <span className="text-xs text-gray-400 font-mono">{test.repo}</span>
                </td>
                <td className="px-4 py-3 w-36">
                  <ScoreBar score={test.flakiness_score} />
                </td>
                <td className="px-4 py-3 hidden sm:table-cell">
                  <CauseBadge cause={test.primary_cause} />
                </td>
                <td className="px-4 py-3 text-right hidden lg:table-cell">
                  <span className="text-xs text-gray-400">
                    {test.total_runs} runs
                    <span className="text-gray-600 ml-1">
                      ({test.failed_runs} ✗)
                    </span>
                  </span>
                </td>
                <td className="px-4 py-3 text-right hidden lg:table-cell">
                  {test.fix_count > 0 ? (
                    <span className="text-xs text-purple-400">
                      <Zap size={12} className="inline mr-1" />
                      {test.fix_count}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            disabled={currentPage === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="px-3 py-1.5 bg-gray-800 rounded text-sm disabled:opacity-30 hover:bg-gray-700 text-gray-300"
          >
            ← Prev
          </button>
          <span className="text-sm text-gray-500">
            Page {currentPage + 1} of {pages}
          </span>
          <button
            disabled={currentPage >= pages - 1}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="px-3 py-1.5 bg-gray-800 rounded text-sm disabled:opacity-30 hover:bg-gray-700 text-gray-300"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}