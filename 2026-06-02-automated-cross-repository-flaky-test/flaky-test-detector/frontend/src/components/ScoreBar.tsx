interface Props {
  score: number  // 0-1
  size?: 'sm' | 'md'
}

export function ScoreBar({ score, size = 'md' }: Props) {
  const pct = Math.round(score * 100)
  const color =
    score >= 0.7 ? 'bg-red-500' :
    score >= 0.5 ? 'bg-orange-500' :
    score >= 0.3 ? 'bg-amber-500' :
    'bg-green-500'

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 bg-gray-700 rounded-full overflow-hidden ${size === 'sm' ? 'h-1.5' : 'h-2'}`}>
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  )
}