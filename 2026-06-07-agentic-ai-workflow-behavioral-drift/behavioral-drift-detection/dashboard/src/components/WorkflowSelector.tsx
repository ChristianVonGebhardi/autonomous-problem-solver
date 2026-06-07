import React from 'react'
import { Workflow } from '../api/client'

interface Props {
  workflows: Workflow[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function WorkflowSelector({ workflows, selectedId, onSelect }: Props) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 13, color: '#718096' }}>Workflow:</span>
      <select
        value={selectedId || ''}
        onChange={e => onSelect(e.target.value)}
        style={{
          background: '#2d3748',
          color: '#e2e8f0',
          border: '1px solid #4a5568',
          borderRadius: 6,
          padding: '4px 12px',
          fontSize: 13,
          cursor: 'pointer',
          outline: 'none',
        }}
      >
        {workflows.map(wf => (
          <option key={wf.id} value={wf.id}>
            {wf.name}
          </option>
        ))}
      </select>
    </div>
  )
}