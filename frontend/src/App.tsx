import { useState, type ReactNode } from 'react'
import {
  BrowserRouter,
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'

import { AuthProvider, useAuth } from './auth/AuthContext'
import { AdminWorkspace } from './pages/AdminWorkspace'
import { AttemptPage } from './pages/AttemptPage'
import { FacultyWorkspace } from './pages/FacultyWorkspace'
import { LoginPage } from './pages/LoginPage'
import { ResultsPage } from './pages/ResultsPage'
import { StudentWorkspace } from './pages/StudentWorkspace'
import type { Role } from './types'

function Protected({ role, children }: { role?: Role; children: ReactNode }) {
  const { user, activeRole, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="loading-screen">Connecting to CampusQuiz…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (user.roles.length > 1 && !activeRole && location.pathname !== '/roles') {
    return <Navigate to="/roles" replace />
  }
  if (role && (!user.roles.includes(role) || activeRole !== role)) {
    return user.roles.length > 1 ? <Navigate to="/roles" replace /> : <NoAccess />
  }
  return <>{children}</>
}

function NoAccess() {
  return (
    <section className="panel no-access">
      <p className="eyebrow">Access restricted</p>
      <h1>This workspace is not available for your account.</h1>
      <Link to="/workspace" className="button button-primary">Return to workspace</Link>
    </section>
  )
}

function ApplicationShell() {
  const { user, activeRole, selectRole, logout } = useAuth()
  const [logoutError, setLogoutError] = useState('')
  const navigate = useNavigate()

  async function signOut() {
    setLogoutError('')
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (reason) {
      setLogoutError(reason instanceof Error ? reason.message : 'Unable to sign out')
    }
  }

  if (!user) return <Outlet />
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="wordmark" to="/workspace">
          <span className="brand-mark brand-small">CQ</span>
          <span>Campus<span>Quiz</span></span>
        </Link>
        <div className="topbar-actions">
          <span className="user-name">{user.first_name} {user.last_name}</span>
          {user.roles.length > 1 && (
            <label className="role-picker">
              <span className="sr-only">Active dashboard</span>
              <select
                value={activeRole ?? ''}
                onChange={(event) => {
                  const role = event.target.value as Role
                  selectRole(role)
                  navigate(role === 'ADMIN' ? '/admin' : role === 'FACULTY' ? '/faculty' : '/student')
                }}
              >
                <option value="" disabled>Select role</option>
                {user.roles.map((role) => <option value={role} key={role}>{role}</option>)}
              </select>
            </label>
          )}
          <button className="button button-small button-quiet" onClick={() => void signOut()}>Sign out</button>
        </div>
      </header>
      {logoutError && <p className="notice notice-error global-notice">{logoutError}</p>}
      <main className="content"><Outlet /></main>
      <footer className="app-footer">CampusQuiz · Secure classroom assessment</footer>
    </div>
  )
}

function RoleSelection() {
  const { user, selectRole } = useAuth()
  const navigate = useNavigate()
  if (!user) return <Navigate to="/login" replace />
  if (user.roles.length === 1) {
    const onlyRole = user.roles[0]
    return <Navigate to={onlyRole === 'ADMIN' ? '/admin' : onlyRole === 'FACULTY' ? '/faculty' : '/student'} replace />
  }
  return (
    <section className="role-screen">
      <p className="eyebrow">Choose your workspace</p>
      <h1>How would you like to continue?</h1>
      <p className="muted">You can switch dashboards at any time without signing out.</p>
      <div className="role-cards">
        {user.roles.map((role) => (
          <button
            className="role-card"
            key={role}
            onClick={() => {
              selectRole(role)
              navigate(role === 'ADMIN' ? '/admin' : role === 'FACULTY' ? '/faculty' : '/student')
            }}
          >
            <span className="role-icon">{role === 'ADMIN' ? '⌂' : role === 'FACULTY' ? '▤' : '✎'}</span>
            <strong>{role === 'ADMIN' ? 'Administrator' : role === 'FACULTY' ? 'Faculty' : 'Student'}</strong>
            <span className="muted">
              {role === 'ADMIN'
                ? 'Manage college academic records and accounts.'
                : role === 'FACULTY'
                  ? 'Create quizzes and manage classroom sessions.'
                  : 'Join active quizzes and review released results.'}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

function WorkspaceRedirect() {
  const { user, activeRole } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  const role = activeRole ?? (user.roles.length === 1 ? user.roles[0] : null)
  if (!role) return <Navigate to="/roles" replace />
  return <Navigate to={role === 'ADMIN' ? '/admin' : role === 'FACULTY' ? '/faculty' : '/student'} replace />
}

function RoutesView() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ApplicationShell />}>
        <Route path="/" element={<WorkspaceRedirect />} />
        <Route path="/workspace" element={<WorkspaceRedirect />} />
        <Route path="/roles" element={<Protected><RoleSelection /></Protected>} />
        <Route path="/admin" element={<Protected role="ADMIN"><AdminWorkspace /></Protected>} />
        <Route path="/faculty" element={<Protected role="FACULTY"><FacultyWorkspace /></Protected>} />
        <Route path="/student" element={<Protected role="STUDENT"><StudentWorkspace /></Protected>} />
        <Route path="/student/attempt/:attemptId" element={<Protected role="STUDENT"><AttemptPage /></Protected>} />
        <Route path="/student/results/:attemptId" element={<Protected><ResultsPage /></Protected>} />
        <Route path="*" element={<WorkspaceRedirect />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <RoutesView />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
