import { Outlet, NavLink } from 'react-router-dom'
import { Shield, LayoutDashboard, Search, List, Database, Activity } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import clsx from 'clsx'

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: 30_000,
  })

  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/scan', icon: Search, label: 'Scan Code' },
    { to: '/scans', icon: List, label: 'Scan History' },
    { to: '/corpus', icon: Database, label: 'Corpus' },
  ]

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-white flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <Shield className="w-8 h-8 text-blue-400" />
            <div>
              <h1 className="font-bold text-lg leading-tight">LicenseGuard</h1>
              <p className="text-gray-400 text-xs">License Detection</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                )
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Status indicator */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <Activity className="w-3 h-3" />
            <span>API:</span>
            <span className={health?.status === 'ok' ? 'text-green-400' : 'text-red-400'}>
              {health?.status === 'ok' ? '● Connected' : '● Disconnected'}
            </span>
          </div>
          {health && (
            <div className="mt-1 text-xs text-gray-500">
              Corpus: {health.corpus_size} snippets
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}