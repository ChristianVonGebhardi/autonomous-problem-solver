import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { Activity, AlertTriangle, GitPullRequest, BarChart3, Zap, Radio } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import FlakyTests from './pages/FlakyTests'
import FlakyTestDetail from './pages/FlakyTestDetail'
import Fixes from './pages/Fixes'
import FixDetail from './pages/FixDetail'
import Ingest from './pages/Ingest'
import LiveFeed from './components/LiveFeed'
import { useWebSocket } from './hooks/useWebSocket'
import { useState } from 'react'

function NavItem({ to, icon: Icon, label }: { to: string; icon: React.ElementType; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? 'bg-sky-500/20 text-sky-400'
            : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
        }`
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  )
}

function Layout({ children }: { children: React.ReactNode }) {
  const { events, connected } = useWebSocket()
  const [showFeed, setShowFeed] = useState(false)
  const location = useLocation()

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Zap className="text-sky-400" size={22} />
            <div>
              <div className="text-sm font-semibold text-white">Flaky Detector</div>
              <div className="text-xs text-gray-500">CI/CD Intelligence</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          <NavItem to="/" icon={BarChart3} label="Dashboard" />
          <NavItem to="/flaky-tests" icon={AlertTriangle} label="Flaky Tests" />
          <NavItem to="/fixes" icon={GitPullRequest} label="Fix Proposals" />
          <NavItem to="/ingest" icon={Activity} label="Ingest Event" />
        </nav>

        <div className="p-3 border-t border-gray-800">
          <button
            onClick={() => setShowFeed(!showFeed)}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <Radio size={14} className={connected ? 'text-green-400 animate-pulse' : 'text-gray-600'} />
            {connected ? 'Live feed active' : 'Connecting...'}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto p-6">
          {children}
        </div>
      </main>

      {/* Live Feed Panel */}
      {showFeed && (
        <LiveFeed events={events} onClose={() => setShowFeed(false)} />
      )}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout><Dashboard /></Layout>} />
        <Route path="/flaky-tests" element={<Layout><FlakyTests /></Layout>} />
        <Route path="/flaky-tests/:id" element={<Layout><FlakyTestDetail /></Layout>} />
        <Route path="/fixes" element={<Layout><Fixes /></Layout>} />
        <Route path="/fixes/:id" element={<Layout><FixDetail /></Layout>} />
        <Route path="/ingest" element={<Layout><Ingest /></Layout>} />
      </Routes>
    </BrowserRouter>
  )
}