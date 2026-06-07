import React from 'react'
import { WorkflowSummary } from '../api/client'

interface Props {
  summary: WorkflowSummary
}

function scoreColor(score?: number): string {
  if (score == null) return '#718096'
  if (score >= 0.65) return '#fc8181'
  if (score >= 0.4 * 0.65) return '#f6ad55'
  return '#68d391'
}

function trendIcon(trend: string): string {
  if (trend === 'increasing') return '↑'
  if (trend === 'decreasing') return '↓'
  return '→'
}

function trendColor(trend: string): string {
  if (trend === 'increasing') return '#fc8181'
  if (trend === 'decreasing') return '#68d391'
  return '#a0aec0'
}

export function SummaryCards({ summary }: Props) {
  const score = summary.recent_composite_score

  const cards = [
    {
      label: 'Drift Score',
      value: score != null ? score.toFixed(3) : '—',
      sub: score != null
        ? (score >= 0.65 ? '🚨 Alert' : '✓ Normal')
        : 'No data',
      color: scoreColor(score),
    },
    {
      label: 'Trend (24h)',
      value: trendIcon(summary.trend),
      sub: summary.trend,
      color: trendColor(summary.trend),
    },
    {
      label: 'Alerts (24h)',
      value: String(summary.alert_count_24h),
      sub: summary.alert_count_24h > 0 ? 'Investigate' : 'Clear',
      color: summary.alert_count_24h > 0 ? '#fc8181' : '#68d391',
    },
    {
      label: 'Baselines',
      value: String(summary.baseline_count),
      sub: summary.baseline_count === 0 ? 'None approved' : 'Golden runs',
      color: summary.baseline_count === 0 ? '#f6ad55' : '#63b3ed',
    },
    {
      label: 'Traces',
      value: String(summary.trace_count_24h),
      sub: 'total stored',
      color: '#a0aec0',
    },
  ]

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(5, 1fr)',
      gap: 12,
      marginBottom: 4,
    }}>
      {cards.map(card => (
        <div key={card.label} style={{
          background: '#1a1d27',
          borderRadius: 10,
          padding: '16px 20px',
          border: '1px solid #2d3748',
        }}>
          <div style={{ fontSize: 11, color: '#718096', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 1 }}>
            {card.label}
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: card.color, lineHeight: 1 }}>
            {card.value}
          </div>
          <div style={{ fontSize: 12, color: '#718096', marginTop: 4 }}>
            {card.sub}
          </div>
        </div>
      ))}
    </div>
  )
}