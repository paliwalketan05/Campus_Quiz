import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, jsonBody } from '../lib/api'
import type { StudentSession } from '../types'

export function StudentWorkspace() {
  const [sessions, setSessions] = useState<StudentSession[]>([])
  const [sessionCode, setSessionCode] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  async function loadSessions() {
    setLoading(true)
    setError('')
    try {
      setSessions(await api<StudentSession[]>('/student/sessions'))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load active sessions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSessions()
  }, [])

  const nextSession = useMemo(
    () =>
      [...sessions].sort(
        (left, right) =>
          new Date(left.end_window_time).getTime() -
          new Date(right.end_window_time).getTime(),
      )[0],
    [sessions],
  )

  async function joinByCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')
    try {
      const session = await api<StudentSession>('/student/sessions/join', {
        method: 'POST',
        body: jsonBody({ session_code: sessionCode }),
      })
      setNotice(`Session found: ${session.quiz_title}`)
      await startSession(session)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to join session')
    }
  }

  async function startSession(session: StudentSession) {
    setError('')
    try {
      const attempt = await api<{
        attempt_id: string
        questions: unknown[]
        deadline: string
      }>(`/attempts/sessions/${session.id}/start`, {
        method: 'POST',
      })
      sessionStorage.setItem(
        `campusquiz-attempt-${attempt.attempt_id}`,
        JSON.stringify({
          session_id: session.id,
          deadline: attempt.deadline,
          questions: attempt.questions,
        }),
      )
      navigate(`/student/attempt/${attempt.attempt_id}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to start this quiz')
    }
  }

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Student workspace</p>
          <h1>Ready when you are.</h1>
          <p className="muted">
            Active quizzes for your enrolled classes appear here. Your answers sync with the
            server as you work.
          </p>
        </div>
        <div className="hero-stat">
          <span>{sessions.length}</span>
          <small>available now</small>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Join a classroom quiz</p>
            <h2>Enter session code</h2>
          </div>
        </div>
        <form className="join-form" onSubmit={joinByCode}>
          <input
            required
            minLength={6}
            maxLength={10}
            value={sessionCode}
            onChange={(event) => setSessionCode(event.target.value.toUpperCase())}
            placeholder="e.g. QZ8K4P2A"
            aria-label="Session code"
          />
          <button className="button button-primary">Find and join</button>
        </form>
        {notice && <p className="notice notice-success">{notice}</p>}
        {error && <p className="notice notice-error">{error}</p>}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Your classes</p>
            <h2>Active sessions</h2>
          </div>
          <button className="button button-quiet" onClick={() => void loadSessions()}>
            Refresh
          </button>
        </div>
        {loading ? (
          <p className="muted">Loading sessions…</p>
        ) : sessions.length === 0 ? (
          <div className="empty-state">
            <strong>No active quizzes right now</strong>
            <span>When a teacher starts a quiz for your class, it will show up here.</span>
          </div>
        ) : (
          <div className="session-grid">
            {sessions.map((session) => (
              <article className="session-card" key={session.id}>
                <div className="session-topline">
                  <span className="status-pill status-active">Live now</span>
                  <span className="session-code">{session.session_code}</span>
                </div>
                <h3>{session.quiz_title}</h3>
                <p className="muted">
                  {session.duration_minutes} minutes · {session.total_marks} marks
                </p>
                <p className="session-instructions">
                  {session.instructions || 'Follow your teacher’s instructions before starting.'}
                </p>
                <button className="button button-primary" onClick={() => void startSession(session)}>
                  Start quiz
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
      {nextSession && (
        <p className="helper-text">
          Session access is checked again by the server when you start.{' '}
          <Link to="/student">Refresh availability</Link>
        </p>
      )}
    </div>
  )
}
