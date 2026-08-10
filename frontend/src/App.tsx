import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import AppLayout from './components/AppLayout'
// DashboardPage 暂时隐藏，保留代码
// import DashboardPage from './pages/DashboardPage'
import SocialAccountsPage from './pages/SocialAccountsPage'
import WebsitesPage from './pages/WebsitesPage'
import MonitorDetailPage from './pages/MonitorDetailPage'
import SettingsPage from './pages/SettingsPage'
import HotTopicsPage from './pages/HotTopicsPage'
import SentimentPage from './pages/SentimentPage'
import IntelligenceReportPage from './pages/IntelligenceReportPage'
import AccountMatchPage from './pages/AccountMatchPage'
import CockpitPage from './pages/CockpitPage'
import './pages/CockpitPage.css'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    setIsAuthenticated(!!token)
    setLoading(false)
  }, [])

  if (loading) return null

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={
          isAuthenticated ? <Navigate to="/" /> : <LoginPage onLogin={() => setIsAuthenticated(true)} />
        } />
        <Route path="/*" element={
          isAuthenticated ? (
            <AppLayout onLogout={() => { localStorage.removeItem('token'); setIsAuthenticated(false) }}>
              <Routes>
                {/* DashboardPage 暂时隐藏，/ 重定向到驾驶舱 */}
                <Route path="/" element={<Navigate to="/cockpit" />} />
                <Route path="/cockpit" element={<CockpitPage />} />
                <Route path="/social" element={<SocialAccountsPage />} />
                <Route path="/websites" element={<WebsitesPage />} />
                <Route path="/detail/:type/:id" element={<MonitorDetailPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/hot-topics" element={<HotTopicsPage />} />
                <Route path="/sentiment" element={<SentimentPage />} />
                <Route path="/intelligence" element={<IntelligenceReportPage />} />
                <Route path="/account-match" element={<AccountMatchPage />} />
              </Routes>
            </AppLayout>
          ) : <Navigate to="/login" />
        } />
      </Routes>
    </BrowserRouter>
  )
}

export default App
