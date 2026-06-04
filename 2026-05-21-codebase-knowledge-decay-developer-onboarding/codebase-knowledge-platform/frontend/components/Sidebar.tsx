'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Brain,
  Search,
  GitBranch,
  Network,
  Activity,
  ChevronRight,
  Layers,
} from 'lucide-react'
import { clsx } from 'clsx'

const navItems = [
  { href: '/', label: 'Dashboard', icon: Activity },
  { href: '/ingest', label: 'Ingest Repository', icon: GitBranch },
  { href: '/query', label: 'Ask Codebase', icon: Search },
  { href: '/graph', label: 'Knowledge Graph', icon: Network },
  { href: '/repositories', label: 'Repositories', icon: Layers },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-64 min-h-screen bg-slate-900 text-white flex flex-col">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-700">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center shadow-lg group-hover:bg-brand-600 transition-colors">
            <Brain className="w-4.5 h-4.5 text-white" size={18} />
          </div>
          <div>
            <div className="text-sm font-bold text-white leading-tight">CodeKnow</div>
            <div className="text-[10px] text-slate-400 leading-tight">Knowledge Platform</div>
          </div>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/' && pathname.startsWith(href))
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150',
                active
                  ? 'bg-brand-600 text-white shadow-md'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              )}
            >
              <Icon size={17} className="shrink-0" />
              <span className="flex-1">{label}</span>
              {active && <ChevronRight size={14} className="text-brand-200" />}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-700">
        <div className="text-xs text-slate-500">v1.0.0 — MVP</div>
      </div>
    </aside>
  )
}