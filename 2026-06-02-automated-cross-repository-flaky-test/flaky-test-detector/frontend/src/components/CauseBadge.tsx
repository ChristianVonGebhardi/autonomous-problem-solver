import type { CauseType } from '../api'

export const CAUSE_COLORS: Record<CauseType, string> = {
  timing: 'bg-amber-900/60 text-amber-300 border border-amber-700/40',
  concurrency: 'bg-purple-900/60 text-purple-300 border border-purple-700/40',
  environment: 'bg-blue-900/60 text-blue-300 border border-blue-700/40',
  state_leakage: 'bg-red-900/60 text-red-300 border border-red-700/40',
  unknown: 'bg-gray-800 text-gray-400 border border-gray-700',
}

export const CAUSE_LABELS: Record<CauseType, string> = {
  timing: '⏱ Timing',
  concurrency: '🔀 Concurrency',
  environment: '🌐 Environment',
  state_leakage: '💧 State Leakage',
  unknown: '❓ Unknown',
}

export function CauseBadge({ cause }: { cause: CauseType | null | undefined }) {
  if (!cause) return null
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${CAUSE_COLORS[cause] || CAUSE_COLORS.unknown}`}>
      {CAUSE_LABELS[cause] || cause}
    </span>
  )
}