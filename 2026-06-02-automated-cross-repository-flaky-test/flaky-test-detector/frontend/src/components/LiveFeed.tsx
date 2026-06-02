import { X, Activity } from 'lucide-react'
import type { WsEvent } from '../hooks/useWebSocket'
import { CAUSE_COLORS, CAUSE_LABELS } from './CauseBadge'
import type { CauseType } from '../api'

interface Props {
  events: WsEvent[]
  onClose: () => void
}

const EVENT_LABELS: Record<string, string> = {
  test_run_ingested: 'Test Run',
  fix_proposed: 'Fix Proposed',
  fix_feedback: 'Feedback',
  flaky_detected: 'Flaky Detected',
}

export default function LiveFeed({ events, onClose }: Props) {
  return (
    <div className="w-80 flex-shrink-0 bg-gray-900 border-l border-gray-800 flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-gray-800">
        <div className="flex items-center gap-2 text-sm font-medium text-white">
          <Activity size={16} className="text-green-400" />
          Live Events
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin">
        {events.length === 0 && (
          <p className="text-xs text-gray-600 text-center mt-8">
            Waiting for events...
          </p>
        )}
        {events.map((ev, i) => (
          <div key={i} className="bg-gray-800 rounded-lg p-3 text-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-medium text-sky-400">
                {EVENT_LABELS[ev.type] || ev.type}
              </span>
              {ev.status && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                  ev.status === 'passed'
                    ? 'bg-green-900 text-green-300'
                    : 'bg-red-900 text-red-300'
                }`}>
                  {String(ev.status)}
                </span>
              )}
            </div>
            {ev.test_name && (
              <p className="text-gray-300 font-mono truncate" title={String(ev.test_name)}>
                {String(ev.test_name).split('::').pop()}
              </p>
            )}
            {ev.root_cause && (
              <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${
                CAUSE_COLORS[ev.root_cause as CauseType] || 'bg-gray-700 text-gray-300'
              }`}>
                {CAUSE_LABELS[ev.root_cause as CauseType] || String(ev.root_cause)}
              </span>
            )}
            {ev.pr_url && (
              <a
                href={String(ev.pr_url)}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline block truncate"
              >
                View PR →
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}