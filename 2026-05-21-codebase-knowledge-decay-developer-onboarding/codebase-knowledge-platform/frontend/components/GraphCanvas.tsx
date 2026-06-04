'use client'

import { useEffect, useRef } from 'react'
import type { GraphVisualization } from '@/lib/api'

interface GraphCanvasProps {
  data: GraphVisualization
}

const NODE_COLORS: Record<string, string> = {
  File: '#6366f1',
  Commit: '#f59e0b',
  Author: '#10b981',
  Repository: '#0ea5e9',
  PullRequest: '#f97316',
  Chunk: '#8b5cf6',
  Unknown: '#94a3b8',
}

const NODE_RADIUS: Record<string, number> = {
  Repository: 18,
  Author: 14,
  File: 10,
  Commit: 8,
  PullRequest: 12,
  Chunk: 6,
  Unknown: 8,
}

interface SimNode {
  id: string
  label: string
  type: string
  x: number
  y: number
  vx: number
  vy: number
}

interface SimEdge {
  source: string
  target: string
  type: string
}

export function GraphCanvas({ data }: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animRef = useRef<number>()
  const nodesRef = useRef<SimNode[]>([])
  const edgesRef = useRef<SimEdge[]>([])
  const isDragging = useRef(false)
  const dragNode = useRef<SimNode | null>(null)
  const mousePos = useRef({ x: 0, y: 0 })
  const offsetRef = useRef({ x: 0, y: 0 })
  const scaleRef = useRef(1)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const { nodes, edges } = data
    const W = canvas.width
    const H = canvas.height
    const cx = W / 2
    const cy = H / 2

    // Initialize node positions in a circle
    const simNodes: SimNode[] = nodes.map((n, i) => {
      const angle = (i / nodes.length) * Math.PI * 2
      const r = Math.min(W, H) * 0.3
      return {
        id: n.id,
        label: n.label,
        type: n.type,
        x: cx + Math.cos(angle) * r + (Math.random() - 0.5) * 50,
        y: cy + Math.sin(angle) * r + (Math.random() - 0.5) * 50,
        vx: 0,
        vy: 0,
      }
    })

    nodesRef.current = simNodes
    edgesRef.current = edges

    const nodeMap = new Map(simNodes.map((n) => [n.id, n]))

    // Simple force simulation
    const simulate = () => {
      const ns = nodesRef.current
      const alpha = 0.05

      // Repulsion
      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const dx = ns[j].x - ns[i].x
          const dy = ns[j].y - ns[i].y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = (80 * 80) / dist
          const fx = (dx / dist) * force * alpha
          const fy = (dy / dist) * force * alpha
          ns[i].vx -= fx
          ns[i].vy -= fy
          ns[j].vx += fx
          ns[j].vy += fy
        }
      }

      // Attraction along edges
      for (const edge of edgesRef.current) {
        const s = nodeMap.get(edge.source)
        const t = nodeMap.get(edge.target)
        if (!s || !t) continue
        const dx = t.x - s.x
        const dy = t.y - s.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const desiredDist = 120
        const force = (dist - desiredDist) * 0.03 * alpha
        const fx = (dx / dist) * force * dist
        const fy = (dy / dist) * force * dist
        s.vx += fx
        s.vy += fy
        t.vx -= fx
        t.vy -= fy
      }

      // Center gravity
      for (const n of ns) {
        if (n === dragNode.current) continue
        n.vx += (cx - n.x) * 0.002
        n.vy += (cy - n.y) * 0.002
        n.vx *= 0.85
        n.vy *= 0.85
        n.x += n.vx
        n.y += n.vy
      }
    }

    const draw = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const ns = nodesRef.current

      ctx.clearRect(0, 0, W, H)
      ctx.fillStyle = '#f8fafc'
      ctx.fillRect(0, 0, W, H)

      ctx.save()
      ctx.translate(offsetRef.current.x, offsetRef.current.y)
      ctx.scale(scaleRef.current, scaleRef.current)

      // Draw edges
      for (const edge of edgesRef.current) {
        const s = nodeMap.get(edge.source)
        const t = nodeMap.get(edge.target)
        if (!s || !t) continue
        ctx.beginPath()
        ctx.moveTo(s.x, s.y)
        ctx.lineTo(t.x, t.y)
        ctx.strokeStyle = '#cbd5e1'
        ctx.lineWidth = 1
        ctx.globalAlpha = 0.6
        ctx.stroke()
        ctx.globalAlpha = 1
      }

      // Draw nodes
      for (const n of ns) {
        const color = NODE_COLORS[n.type] ?? NODE_COLORS.Unknown
        const r = NODE_RADIUS[n.type] ?? 8

        // Shadow
        ctx.shadowColor = 'rgba(0,0,0,0.15)'
        ctx.shadowBlur = 6

        ctx.beginPath()
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()

        ctx.shadowBlur = 0

        ctx.beginPath()
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
        ctx.strokeStyle = 'white'
        ctx.lineWidth = 2
        ctx.stroke()

        // Label for larger nodes
        if (r >= 10) {
          ctx.font = '9px system-ui, sans-serif'
          ctx.fillStyle = '#334155'
          ctx.textAlign = 'center'
          const labelText = n.label.length > 18 ? n.label.slice(0, 16) + '…' : n.label
          ctx.fillText(labelText, n.x, n.y + r + 10)
        }
      }

      ctx.restore()
    }

    const tick = () => {
      simulate()
      draw()
      animRef.current = requestAnimationFrame(tick)
    }

    animRef.current = requestAnimationFrame(tick)

    // Mouse interaction
    const getNodeAtPos = (mx: number, my: number): SimNode | null => {
      const ox = (mx - offsetRef.current.x) / scaleRef.current
      const oy = (my - offsetRef.current.y) / scaleRef.current
      for (const n of nodesRef.current) {
        const r = NODE_RADIUS[n.type] ?? 8
        const dx = n.x - ox
        const dy = n.y - oy
        if (Math.sqrt(dx * dx + dy * dy) < r + 4) return n
      }
      return null
    }

    const onMouseDown = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const hit = getNodeAtPos(mx, my)
      if (hit) {
        isDragging.current = true
        dragNode.current = hit
      }
      mousePos.current = { x: mx, y: my }
    }

    const onMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      if (isDragging.current && dragNode.current) {
        const dx = (mx - mousePos.current.x) / scaleRef.current
        const dy = (my - mousePos.current.y) / scaleRef.current
        dragNode.current.x += dx
        dragNode.current.y += dy
        dragNode.current.vx = 0
        dragNode.current.vy = 0
      }
      mousePos.current = { x: mx, y: my }
    }

    const onMouseUp = () => {
      isDragging.current = false
      dragNode.current = null
    }

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const delta = e.deltaY > 0 ? 0.9 : 1.1
      scaleRef.current = Math.min(3, Math.max(0.2, scaleRef.current * delta))
    }

    canvas.addEventListener('mousedown', onMouseDown)
    canvas.addEventListener('mousemove', onMouseMove)
    canvas.addEventListener('mouseup', onMouseUp)
    canvas.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
      canvas.removeEventListener('mousedown', onMouseDown)
      canvas.removeEventListener('mousemove', onMouseMove)
      canvas.removeEventListener('mouseup', onMouseUp)
      canvas.removeEventListener('wheel', onWheel)
    }
  }, [data])

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={900}
        height={600}
        className="w-full rounded-xl border border-slate-200 cursor-grab active:cursor-grabbing"
        style={{ background: '#f8fafc' }}
      />
      {/* Legend */}
      <div className="absolute bottom-3 right-3 bg-white/90 backdrop-blur-sm border border-slate-200 rounded-lg p-2 text-[10px]">
        <div className="font-semibold text-slate-600 mb-1">Legend</div>
        {Object.entries(NODE_COLORS).slice(0, 5).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5 text-slate-600">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block"
              style={{ background: color }}
            />
            {type}
          </div>
        ))}
      </div>
      <div className="absolute top-3 left-3 text-[10px] text-slate-400">
        Scroll to zoom • Drag nodes
      </div>
    </div>
  )
}