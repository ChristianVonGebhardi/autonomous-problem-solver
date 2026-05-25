import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, WSMessage } from './types'

interface AuthState {
  token: string | null
  user: User | null
  setAuth: (token: string, user: User) => void
  clearAuth: () => void
  updateUser: (user: User) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      clearAuth: () => set({ token: null, user: null }),
      updateUser: (user) => set({ user }),
    }),
    {
      name: 'scopeguard-auth',
    }
  )
)

interface NotificationState {
  notifications: WSMessage[]
  unreadCount: number
  addNotification: (msg: WSMessage) => void
  clearNotifications: () => void
  markAllRead: () => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,
  addNotification: (msg) =>
    set((state) => ({
      notifications: [msg, ...state.notifications].slice(0, 50),
      unreadCount: state.unreadCount + 1,
    })),
  clearNotifications: () => set({ notifications: [], unreadCount: 0 }),
  markAllRead: () => set({ unreadCount: 0 }),
}))