import React from 'react'
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'
import { DriftTimeSeriesPoint } from '../api/client'

interface Props {
  data: DriftTimeSeriesPoint[]
  alertThreshold: number
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function severityDot(props: any) {
  const { cx, cy, payload } = props
  if (!payload.alert_triggered) return null
  return (
    <circle
      key={`dot-${cx}-${cy}`}
      cx={cx}
      cy={cy}
      r={5}
      fill="#fc8181"
      stroke="#fff"
      strokeWidth={1.5}
    />
  )
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload as DriftTimeSeriesPoint
  if (!d) return null

  return (
    <div style={{
      background: '#1a202c',
      border: '1px solid #4a5568',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: 12,
    }}>
      <div style={{ color: '#a0aec0', marginBottom: 6 }}>{formatTime(d.timestamp)}</div>
      <div style={{ color: '#e2e8f0' }}>run: {d.run_id.slice(0, 8)}…</div>
      <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 14px' }}>
        <span style={{ color: '#63b3ed' }}>composite</span>
        <span style={{ color: '#63b3ed', fontWeight: 700 }}>{d.composite_score.toFixed(3)}</span>
        <span style={{ color: '#9f7aea' }}>structural</span>
        <span style={{ color: '#9f7aea' }}>{(d.structural_score ?? 0).toFixed(3)}</span>
        <span style={{ color: '#68d391' }}>semantic</span>
        <span style={{ color: '#68d391' }}>{(d.semantic_score ?? 0).toFixed(3)}</span>
        <span style={{ color: '#f6ad55' }}>distributional</span>
        <span style={{ color: '#f6ad55' }}>{(d.distributional_score ?? 0).toFixed(3)}</span>
      </div>
      {d.alert_triggered && (
        <div style={{ marginTop: 6, color: '#fc8181', fontWeight: 600 }}>
          🚨 {d.severity?.toUpperCase()}
        </div>
      )}
    </div>
  )
}

export function DriftChart({ data, alertThreshold }: Props) {
  const chartData = data.map(d => ({
    ...d,
    time: formatTime(d.timestamp),
  }))

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" vertical={false} />
        <XAxis
          dataKey="time"
          tick={{ fill: '#718096', fontSize: 11 }}
          axisLine={{ stroke: '#2d3748' }}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fill: '#718096', fontSize: 11 }}
          axisLine={{ stroke: '#2d3748' }}
          tickLine={false}
          tickFormatter={(v: number) => v.toFixed(1)}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(value: string) => (
            <span style={{ color: '#a0aec0' }}>{value}</span>
          )}
        />
        <ReferenceLine
          y={alertThreshold}
          stroke="#fc8181"
          strokeDasharray="6 3"
          label={{ value: 'Alert threshold', fill: '#fc8181', fontSize: 11, position: 'insideTopRight' }}
        />
        {/* Shaded alert zone */}
        <Area
          type="monotone"
          dataKey="composite_score"
          stroke="none"
          fill="#fc818120"
          fillOpacity={1}
          name="alert zone"
          legendType="none"
          activeDot={false}
        />
        <Line
          type="monotone"
          dataKey="structural_score"
          stroke="#9f7aea"
          strokeWidth={1.5}
          dot={false}
          name="structural"
          strokeOpacity={0.8}
        />
        <Line
          type="monotone"
          dataKey="semantic_score"
          stroke="#68d391"
          strokeWidth={1.5}
          dot={false}
          name="semantic"
          strokeOpacity={0.8}
        />
        <Line
          type="monotone"
          dataKey="distributional_score"
          stroke="#f6ad55"
          strokeWidth={1.5}
          dot={false}
          name="distributional"
          strokeOpacity={0.8}
        />
        <Line
          type="monotone"
          dataKey="composite_score"
          stroke="#63b3ed"
          strokeWidth={2.5}
          dot={severityDot}
          activeDot={{ r: 4, fill: '#63b3ed' }}
          name="composite"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}