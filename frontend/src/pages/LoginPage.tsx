import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const [collegeId, setCollegeId] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) return <Navigate to="/workspace" replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(collegeId, email, password)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to sign in')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="brand-mark">CQ</div>
        <p className="eyebrow">Campus Quiz</p>
        <h1>Welcome back</h1>
        <p className="muted">Sign in with your college account to continue.</p>
        <form className="form-stack" onSubmit={submit}>
          <label>
            College ID
            <input
              required
              value={collegeId}
              onChange={(event) => setCollegeId(event.target.value)}
              placeholder="College UUID"
              autoComplete="organization"
            />
          </label>
          <label>
            College email
            <input
              required
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error && <p className="notice notice-error">{error}</p>}
          <button className="button button-primary button-wide" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="login-footnote">Your session is protected with secure, HTTP-only cookies.</p>
      </section>
    </main>
  )
}
