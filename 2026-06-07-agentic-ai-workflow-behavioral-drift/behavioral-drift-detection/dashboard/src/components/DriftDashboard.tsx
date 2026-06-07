import React, { useEffect, useState, useCallback } from 'react'
import {
  getDriftTimeseries,
  getDriftAlerts,
  getWorkflowSummary,
  getTraces,
  DriftTimeSeriesPoint,
  DriftScoreDetail,
  WorkflowSummary,
  TraceRecord,
} from '../api/client'
import { DriftChart } from './DriftChart'
import { AlertFeed } from './AlertFeed'
import { SummaryCards } from './SummaryCards'
import { TraceTable } from './TraceTable'

interface Props {
  workflowId: string
  pollIntervalMs: number
}

export function DriftDashboard({ workflowId, pollIntervalMs }: Props) {
  const [timeseries, setTimeseries] = useState<DriftTimeSeriesPoint[]>([])
  const [alerts, setAlerts] = useState<DriftScoreDetail[]>([])
  const [summary, setSummary] = useState<WorkflowSummary | null>(null)
  const [traces, setTraces] = useState<TraceRecord[]>([])
  const [hours, setHours] = useState(24)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const [ts, al, sm, tr] = await Promise.all([
        getDriftTimeseries(workflowId, hours),
        getDriftAlerts(workflowId, hours),
        getWorkflowSummary(workflowId),
        getTraces(workflowId, 100),
      ])
      setTimeseries(ts)
      setAlerts(al)
      setSummary(sm)
      setTraces(tr)
    } catch (_) {
      // silently retry
    } finally {
      setLoading(false)
    }
  }, [workflowId, hours])

  useEffect(() => {
    setLoading(true)
    refresh()
    const interval = setInterval(refresh, pollIntervalMs)
    return () => clearInterval(interval)
  }, [refresh, pollIntervalMs])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', marginTop: 60, color: '#718096' }}>
        Loading drift data…
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Summary row */}
      {summary && <SummaryCards summary={summary} />}

      {/* Controls */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        margin: '20px 0 12px',
      }}>
        <span style={{ color: '#a0aec0', fontSize: 13 }}>Time range:</span>
        {[1, 6, 24, 72].map(h => (
          <button
            key={h}
            onClick={() => setHours(h)}
            style={{
              background: hours === h ? '#4299e1' : '#2d3748',
              color: hours === h ? '#fff' : '#a0aec0',
              border: 'none',
              borderRadius: 5,
              padding: '4px 12px',
              fontSize: 12,
              cursor: 'pointer',
              fontWeight: hours === h ? 700 : 400,
            }}
          >
            {h}h
          </button>
        ))}
        <span style={{ marginLeft: 'auto', color: '#4a5568', fontSize: 12 }}>
          Auto-refresh every {pollIntervalMs / 1000}s
        </span>
      </div>

      {/* Drift timeline chart */}
      <div style={{
        background: '#1a1d27',
        borderRadius: 10,
        padding: 20,
        marginBottom: 20,
        border: '1px solid #2d3748',
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#e2e8f0' }}>
          Drift Score Timeline
        </h2>
        {timeseries.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#4a5568', padding: '40px 0', fontSize: 13 }}>
            No traces processed in this time range
          </div>
        ) : (
          <DriftChart data={timeseries} alertThreshold={0.65} />
        )}
      </div>

      {/* Alerts + Traces */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <div style={{
          background: '#1a1d27',
          borderRadius: 10,
          padding: 20,
          border: '1px solid #2d3748',
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#e2e8f0' }}>
            Recent Alerts
            {alerts.length > 0 && (
              <span style={{
                marginLeft: 8,
                background: '#c53030',
                color: '#fff',
                borderRadius: 10,
                padding: '1px 7px',
                fontSize: 11,
              }}>
                {alerts.length}
              </span>
            )}
          </h2>
          <AlertFeed alerts={alerts} />
        </div>

        <div style={{
          background: '#1a1d27',
          borderRadius: 10,
          padding: 20,
          border: '1px solid #2d3748',
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#e2e8f0' }}>
            Recent Traces
          </h2>
          <TraceTable traces={traces.slice(0, 15)} />
        </div>
      </div>
    </div>
  )
}