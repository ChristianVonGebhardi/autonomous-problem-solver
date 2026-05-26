import clsx from 'clsx'

interface RiskBadgeProps {
  tier: string
  className?: string
}

const TIER_CONFIG: Record<string, { label: string; emoji: string; classes: string }> = {
  high: {
    label: 'HIGH RISK',
    emoji: '⚠️',
    classes: 'bg-red-100 text-red-700 border border-red-200',
  },
  medium: {
    label: 'MEDIUM',
    emoji: '⚡',
    classes: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
  },
  low: {
    label: 'LOW',
    emoji: 'ℹ️',
    classes: 'bg-blue-100 text-blue-700 border border-blue-200',
  },
  clean: {
    label: 'CLEAN',
    emoji: '✅',
    classes: 'bg-green-100 text-green-700 border border-green-200',
  },
  unknown: {
    label: 'UNKNOWN',
    emoji: '❓',
    classes: 'bg-gray-100 text-gray-700 border border-gray-200',
  },
}

export default function RiskBadge({ tier, className }: RiskBadgeProps) {
  const config = TIER_CONFIG[tier] ?? TIER_CONFIG.unknown
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold',
        config.classes,
        className
      )}
    >
      <span>{config.emoji}</span>
      {config.label}
    </span>
  )
}