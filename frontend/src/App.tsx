import React, { useState, Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { Icon } from '@iconify/react'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import { LoginScreen } from './components/auth/LoginScreen'
import { useInspections } from './hooks/useInspections'
import { isAuthenticated, logout } from './lib/auth'

// CodeVerity operator console pages (the single production plane).
import Leads from './pages/Leads'
import Conversations from './pages/Conversations'
import Instances from './pages/Instances'
import Jobsites from './pages/Jobsites'
import Companies from './pages/Companies'

// Error Boundary Component
class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean, error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-bg-base flex flex-col items-center justify-center p-6">
          <div className="card p-8 lg:p-10 max-w-xl w-full animate-fade-up">
            <div className="w-12 h-12 rounded-2xl bg-red-50 border border-red-100 flex items-center justify-center mb-6">
              <Icon icon="solar:danger-triangle-bold" width="24" style={{ color: '#dc2626' }} />
            </div>
            <h1 className="text-2xl font-bold text-ink mb-2 tracking-tight">Something went wrong</h1>
            <p className="text-sm text-ink-muted mb-6">An unexpected error occurred in the application core.</p>
            <div className="bg-bg-elevated p-5 rounded-xl border border-border mb-8 overflow-auto max-h-60">
              <code className="text-xs text-red-500">{this.state.error?.toString()}</code>
            </div>
            <button
              onClick={() => {
                logout()
                window.location.href = '/'
              }}
              className="btn-premium w-full"
            >
              Sign out & reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

const AppContent: React.FC = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(() => {
    return localStorage.getItem('sidebar_collapsed') === 'true'
  })

  const toggleCollapse = () => {
    setIsCollapsed(prev => {
      const next = !prev
      localStorage.setItem('sidebar_collapsed', String(next))
      return next
    })
  }

  // CodeVerity live feed drives the entire operator console (single data plane).
  const { inspections, connected, approve, remove } = useInspections()
  const location = useLocation()

  const getTitle = () => {
    switch (location.pathname) {
      case '/': return 'Live Feed'
      case '/leads': return 'Claims'
      case '/instances': return 'Crew Manager'
      case '/jobsites': return 'Jobsite Management'
      case '/branches': return 'Company Branches'
      default: return 'CodeVerity'
    }
  }

  const handleLogout = () => {
    logout()
    window.location.reload()
  }

  return (
    <div className="h-screen flex overflow-hidden bg-bg-base font-sans selection:bg-brand/20 selection:text-ink relative">
      <div className="neural-overlay" />

      <Sidebar
        isOpen={isSidebarOpen}
        setIsOpen={setIsSidebarOpen}
        onLogout={handleLogout}
        isCollapsed={isCollapsed}
        onToggleCollapse={toggleCollapse}
      />

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10">
        <title>CodeVerity | Field & Operator Console</title>
        <Header
          title={getTitle()}
          isConnected={connected}
          lastUpdated={new Date()}
          leadsCount={inspections.length}
          onToggleMenu={() => setIsSidebarOpen(true)}
        />

        <div className="flex-1 overflow-y-auto custom-scrollbar bg-transparent">
          <Routes>
            <Route path="/" element={<Conversations inspections={inspections} connected={connected} approve={approve} onDelete={remove} />} />
            <Route path="/conversations" element={<Conversations inspections={inspections} connected={connected} approve={approve} onDelete={remove} />} />
            <Route path="/leads" element={<Leads inspections={inspections} approve={approve} />} />
            <Route path="/instances" element={<Instances />} />
            <Route path="/jobsites" element={<Jobsites />} />
            <Route path="/branches" element={<Companies />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}


const App: React.FC = () => {
  const [authed, setAuthed] = useState(isAuthenticated())
  return (
    <ErrorBoundary>
      <BrowserRouter>
        {authed ? <AppContent /> : <LoginScreen onSuccess={() => setAuthed(true)} />}
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
