import { useEffect, useRef, useCallback } from 'react'
import { useAuthStore, useNotificationStore } from '../store'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import type { WSMessage } from '../types'

export function useWebSocket() {
  const { user } = useAuthStore()
  const { addNotification } = useNotificationStore()
  const queryClient = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)

  const connect = useCallback(() => {
    if (!user?.id) return

    // Use wss:// in production, ws:// in development
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/${user.id}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0
      // Keep-alive ping every 30 seconds
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        } else {
          clearInterval(pingInterval)
        }
      }, 30000)
    }

    ws.onmessage = (event: MessageEvent) => {
      if (event.data === 'pong') return

      try {
        const message: WSMessage = JSON.parse(event.data as string)

        if (message.type === 'violation_detected') {
          const data = message.data as {
            severity?: string
            summary?: string
            estimated_cost?: number
            contract_title?: string
          }

          const severity = data.severity ?? 'medium'
          const emoji =
            severity === 'critical' ? '🚨' : severity === 'high' ? '⚠️' : '📋'

          toast(
            `${emoji} Scope Creep Detected!\n${data.summary ?? ''}`,
            {
              duration: 6000,
              style: {
                background:
                  severity === 'critical'
                    ? '#7f1d1d'
                    : severity === 'high'
                    ? '#78350f'
                    : '#1e3a5f',
                color: '#f1f5f9',
              },
            }
          )

          // Invalidate relevant queries so data refreshes
          queryClient.invalidateQueries({ queryKey: ['violations'] })
          queryClient.invalidateQueries({ queryKey: ['change-orders'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })

          addNotification(message)
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message', e)
      }
    }

    ws.onclose = () => {
      // Reconnect with exponential backoff (max 5 attempts)
      if (reconnectAttemptsRef.current < 5) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttemptsRef.current++
          connect()
        }, delay)
      }
    }

    ws.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    }
  }, [user?.id, addNotification, queryClient])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])
}