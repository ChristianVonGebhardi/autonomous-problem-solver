import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import ScanPage from './pages/ScanPage'
import ScansListPage from './pages/ScansListPage'
import ScanDetailPage from './pages/ScanDetailPage'
import CorpusPage from './pages/CorpusPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="scan" element={<ScanPage />} />
          <Route path="scans" element={<ScansListPage />} />
          <Route path="scans/:scanId" element={<ScanDetailPage />} />
          <Route path="corpus" element={<CorpusPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}