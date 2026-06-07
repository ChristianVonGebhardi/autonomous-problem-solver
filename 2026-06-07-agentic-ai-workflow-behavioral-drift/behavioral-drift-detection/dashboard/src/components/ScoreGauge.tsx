import React from 'react'

interface Props {
  score: number
  size?: number
  label?: string
}

export function ScoreGauge({ score, size = 80, label }: Props) {
  const clampedScore = Math.max(0, Math.min(1, score))
  const circumference = 2 * Math.PI * 30
  const dashOffset = circumference * (1 - clampedScore)

  const color =
    clampedScore >= 0.65 ? '#fc8181'
    : clampedScore >= 0.26 ? '#f6ad55'
    : '#68d391'

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={size} height={size} viewBox="0 0 80 80">
        {/* Background ring */}
        <circle
          cx="40" cy="40" r="30"
          fill="none"
          stroke="#2d3748"
          strokeWidth="7"
        />
        {/* Score arc */}
        <circle
          cx="40" cy="40" r="30"
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform="rotate(-90 40 40)"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
        {/* Score text */}
        <text x="40" y="44" textAnchor="middle" fill={color} fontSize="14" fontWeight="700">
          {clampedScore.toFixed(2)}
        </text>
      </svg>
      {label && (
        <span style={{ fontSize: 11, color: '#718096' }}>{label}</span>
      )}
    </div>
  )
}