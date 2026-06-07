import React, { useState, useEffect } from 'react'
import { getWorkflows, Workflow } from './api/client'
import { WorkflowSelector } from './components/WorkflowSelector'
import { DriftDashboard } from './components/DriftDashboard'

const POLL_INTERVAL_MS = 5000

export default function App() {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Read workflow from URL param on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const wfParam = params.get('workflow')
    if (wfParam) setSelectedId(wfParam)
  }, [])

  const fetchWorkflows = async () => {
    try {
      const data = await getWorkflows()
      setWorkflows(data)
      if (!selectedId && data.length > 0) {
        setSelectedId(data[0].id)
      }
      setError(null)
    } catch (err) {
      setError('Cannot reach API — is the server running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchWorkflows()
    const interval = setInterval(fetchWorkflows, POLL_INTERVAL_MS * 6)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: '#0f1117', color: '#e2e8f0' }}>
      {/* Header */}
      <header style={{
        background: '#1a1d27',
        borderBottom: '1px solid #2d3748',
        padding: '0 24px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <RadarIcon />
          <span style={{ fontWeight: 700, fontSize: 16, color: '#f7fafc' }}>
            Behavioral Drift Detection
          </span>
          <span style={{
            fontSize: 11,
            background: '#2d3748',
            color: '#a0aec0',
            padding: '2px 8px',
            borderRadius: 4,
            fontWeight: 500,
          }}>
            MVP
          </span>
        </div>

        <div style={{ flex: 1 }} />

        {!loading && !error && (
          <WorkflowSelector
            workflows={workflows}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id)
              const url = new URL(window.location.href)
              url.searchParams.set('workflow', id)
              window.history.replaceState({}, '', url.toString())
            }}
          />
        )}

        <div style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: error ? '#fc8181' : '#68d391',
          marginLeft: 8,
        }} title={error ? 'API offline' : 'API connected'} />
      </header>

      {/* Main content */}
      <main style={{ padding: '24px' }}>
        {loading && (
          <div style={{ textAlign: 'center', marginTop: 80, color: '#718096' }}>
            Connecting to API…
          </div>
        )}
        {error && (
          <div style={{
            background: '#1a202c',
            border: '1px solid #fc8181',
            borderRadius: 8,
            padding: 24,
            maxWidth: 600,
            margin: '80px auto',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 24, marginBottom: 12 }}>⚠️</div>
            <div style={{ color: '#fc8181', marginBottom: 8 }}>{error}</div>
            <div style={{ color: '#718096', fontSize: 13 }}>
              Start the API: <code style={{ color: '#68d391' }}>uvicorn api.main:app --reload --port 8000</code>
            </div>
          </div>
        )}
        {!loading && !error && workflows.length === 0 && (
          <div style={{
            textAlign: 'center',
            marginTop: 80,
            color: '#718096',
          }}>
            <div style={{ fontSize: 32, marginBottom: 16 }}>🔬</div>
            <div style={{ fontSize: 18, marginBottom: 8 }}>No workflows yet</div>
            <div style={{ fontSize: 14 }}>
              Run the simulation to get started:<br />
              <code style={{ color: '#68d391', fontSize: 13 }}>
                python -m examples.simulate_agent
              </code>
            </div>
          </div>
        )}
        {!loading && !error && selectedId && (
          <DriftDashboard workflowId={selectedId} pollIntervalMs={POLL_INTERVAL_MS} />
        )}
      </main>
    </div>
  )
}

function RadarIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#63b3ed" strokeWidth="2">
      <circle cx="12" cy="12" r="2" />
      <path d="M12 2a10 10 0 0 1 10 10" />
      <path d="M12 6a6 6 0 0 1 6 6" />
      <path d="M12 10a2 2 0 0 1 2 2" />
    </svg>
  )
}