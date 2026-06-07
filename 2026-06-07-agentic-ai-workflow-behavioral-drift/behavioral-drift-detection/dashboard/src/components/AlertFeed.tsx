import React, { useState } from 'react'
import { DriftScoreDetail } from '../api/client'

interface Props {
  alerts: DriftScoreDetail[]
}

function severityStyle(severity?: string): React.CSSProperties {
  switch (severity) {
    case 'critical': return { color: '#fc8181', background: '#742a2a30' }
    case 'high': return { color: '#f6ad55', background: '#7b341e30' }
    case 'medium': return { color: '#faf089', background: '#74480030' }
    default: return { color: '#a0aec0', background: '#2d374830' }
  }
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString([], {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function AlertFeed({ alerts }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (alerts.length === 0) {
    return (
      <div style={{ color: '#4a5568', fontSize: 13, textAlign: 'center', padding: '30px 0' }}>
        ✓ No alerts in this time range
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 400, overflowY: 'auto' }}>
      {alerts.map(alert => {
        const isOpen = expanded === alert.id
        const sStyle = severityStyle(alert.severity)

        return (
          <div
            key={alert.id}
            style={{
              background: '#0f1117',
              border: '1px solid #2d3748',
              borderRadius: 8,
              padding: '10px 12px',
              cursor: 'pointer',
              transition: 'border-color 0.15s',
            }}
            onClick={() => setExpanded(isOpen ? null : alert.id)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                ...sStyle,
                fontSize: 10,
                fontWeight: 700,
                padding: '2px 7px',
                borderRadius: 4,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
              }}>
                {alert.severity}
              </span>
              <span style={{ fontSize: 12, color: '#e2e8f0', fontFamily: 'monospace' }}>
                {alert.run_id.slice(0, 12)}…
              </span>
              <span style={{ marginLeft: 'auto', fontSize: 11, color: '#718096' }}>
                {formatTime(alert.ingested_at)}
              </span>
            </div>

            <div style={{ display: 'flex', gap: 16, marginTop: 6 }}>
              <ScorePill label="composite" value={alert.composite_score} />
              <ScorePill label="struct" value={alert.structural_score} />
              <ScorePill label="semantic" value={alert.semantic_score} />
              <ScorePill label="distrib" value={alert.distributional_score} />
            </div>

            {isOpen && (
              <div style={{ marginTop: 10, borderTop: '1px solid #2d3748', paddingTop: 10 }}>
                {alert.explanation ? (
                  <div style={{ fontSize: 12, color: '#a0aec0', lineHeight: 1.6 }}>
                    <span style={{ color: '#63b3ed', fontWeight: 600 }}>LLM Analysis: </span>
                    {alert.explanation}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: '#4a5568' }}>
                    No LLM explanation (set OPENAI_API_KEY for automated analysis)
                  </div>
                )}
                {alert.structural_detail && (
                  <div style={{ marginTop: 8 }}>
                    <span style={{ fontSize: 11, color: '#9f7aea' }}>Structural: </span>
                    <span style={{ fontSize: 11, color: '#718096' }}>
                      edit_dist={String((alert.structural_detail as any).min_edit_distance ?? '?')},
                      unexpected=[{((alert.structural_detail as any).unexpected_tools ?? []).join(', ')}]
                    </span>
                  </div>
                )}
                {alert.distributional_detail && (
                  <div style={{ marginTop: 4 }}>
                    <span style={{ fontSize: 11, color: '#f6ad55' }}>Distributional: </span>
                    <span style={{ fontSize: 11, color: '#718096' }}>
                      cusum+={(alert.distributional_detail as any).cusum_pos?.toFixed(2)},
                      signal={(alert.distributional_detail as any).signal_value?.toFixed(3)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ScorePill({ label, value }: { label: string; value?: number | null }) {
  const v = value ?? 0
  const color = v >= 0.65 ? '#fc8181' : v >= 0.26 ? '#f6ad55' : '#68d391'
  return (
    <span style={{ fontSize: 11, color: '#718096' }}>
      {label}{' '}
      <span style={{ color, fontWeight: 600 }}>{v.toFixed(3)}</span>
    </span>
  )
}