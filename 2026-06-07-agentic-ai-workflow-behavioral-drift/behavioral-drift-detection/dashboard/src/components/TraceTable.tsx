import React from 'react'
import { TraceRecord } from '../api/client'

interface Props {
  traces: TraceRecord[]
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function scoreBar(score?: number | null): React.ReactNode {
  if (score == null) return <span style={{ color: '#4a5568' }}>—</span>
  const pct = Math.round(score * 100)
  const color = score >= 0.65 ? '#fc8181' : score >= 0.26 ? '#f6ad55' : '#68d391'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 50,
        height: 5,
        background: '#2d3748',
        borderRadius: 3,
        overflow: 'hidden',
      }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 11, color }}>{score.toFixed(3)}</span>
    </div>
  )
}

export function TraceTable({ traces }: Props) {
  if (traces.length === 0) {
    return (
      <div style={{ color: '#4a5568', fontSize: 13, textAlign: 'center', padding: '30px 0' }}>
        No traces yet
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto', maxHeight: 380, overflowY: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #2d3748' }}>
            {['Run ID', 'Time', 'Tools', 'Drift', 'Status'].map(h => (
              <th key={h} style={{
                textAlign: 'left',
                padding: '6px 8px',
                color: '#718096',
                fontWeight: 500,
                fontSize: 11,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {traces.map(t => (
            <tr key={t.run_id} style={{
              borderBottom: '1px solid #1a202c',
              background: t.alert_triggered ? '#1a0a0a' : 'transparent',
            }}>
              <td style={{ padding: '6px 8px', color: '#a0aec0', fontFamily: 'monospace' }}>
                {t.run_id.slice(0, 10)}…
              </td>
              <td style={{ padding: '6px 8px', color: '#718096' }}>
                {formatTime(t.start_time)}
              </td>
              <td style={{ padding: '6px 8px', color: '#a0aec0', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {(t.tool_sequence || []).join(' → ')}
              </td>
              <td style={{ padding: '6px 8px' }}>
                {t.processed ? scoreBar(t.composite_score) : (
                  <span style={{ color: '#4a5568', fontSize: 11 }}>pending…</span>
                )}
              </td>
              <td style={{ padding: '6px 8px' }}>
                {!t.processed ? (
                  <span style={{ color: '#718096', fontSize: 11 }}>⏳</span>
                ) : t.alert_triggered ? (
                  <span style={{ color: '#fc8181', fontSize: 11 }}>🚨 {t.severity}</span>
                ) : (
                  <span style={{ color: '#68d391', fontSize: 11 }}>✓ ok</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}