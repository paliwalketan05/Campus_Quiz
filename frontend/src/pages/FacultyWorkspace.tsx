import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { api, jsonBody } from '../lib/api'
import type { Quiz, QuizSession, SessionAnalytics } from '../types'

interface QuestionOption {
  option_text: string
  is_correct: boolean
  display_order: number
}

interface AuthoringQuestion {
  id: string
  question_text: string
}

const transitionActions = ['activate', 'pause', 'resume', 'complete', 'cancel'] as const

export function FacultyWorkspace() {
  const [quizzes, setQuizzes] = useState<Quiz[]>([])
  const [sessions, setSessions] = useState<QuizSession[]>([])
  const [selectedQuizId, setSelectedQuizId] = useState('')
  const [analyticsId, setAnalyticsId] = useState('')
  const [analytics, setAnalytics] = useState<SessionAnalytics | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function reload() {
    const [quizRows, sessionRows] = await Promise.all([
      api<Quiz[]>('/quizzes'),
      api<QuizSession[]>('/sessions'),
    ])
    setQuizzes(quizRows)
    setSessions(sessionRows)
    if (!selectedQuizId && quizRows.length) setSelectedQuizId(quizRows[0].id)
  }

  useEffect(() => {
    void reload().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : 'Could not load faculty data'),
    )
  }, [])

  const selectedQuiz = useMemo(
    () => quizzes.find((quiz) => quiz.id === selectedQuizId) ?? null,
    [quizzes, selectedQuizId],
  )

  async function withFeedback(action: () => Promise<void>, success: string) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await action()
      setMessage(success)
      await reload()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The operation failed')
    } finally {
      setBusy(false)
    }
  }

  async function createQuiz(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    await withFeedback(async () => {
      const quiz = await api<Quiz>('/quizzes', {
        method: 'POST',
        body: jsonBody({
          subject_id: form.get('subject_id'),
          title: form.get('title'),
          default_duration_minutes: Number(form.get('duration')),
        }),
      })
      setSelectedQuizId(quiz.id)
    }, 'Draft quiz created')
    formElement.reset()
  }

  async function addQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedQuiz) return
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    const optionLines = String(form.get('options') ?? '')
      .split('\n')
      .map((option) => option.trim())
      .filter(Boolean)
    const correctIndexes = new Set(
      String(form.get('correct_indexes') ?? '')
        .split(',')
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isInteger(value) && value >= 1),
    )
    const options: QuestionOption[] = optionLines.map((option_text, index) => ({
      option_text,
      is_correct: correctIndexes.has(index + 1),
      display_order: index + 1,
    }))
    await withFeedback(async () => {
      const question = await api<AuthoringQuestion>('/questions', {
        method: 'POST',
        body: jsonBody({
          subject_id: selectedQuiz.subject_id,
          question_type: form.get('question_type'),
          question_text: form.get('question_text'),
          default_marks: form.get('marks'),
          options,
        }),
      })
      const questions = [
        ...selectedQuiz.questions.map((item) => ({
          question_id: item.question_id,
          sequence_order: item.sequence_order,
          marks_override: item.marks_override,
        })),
        {
          question_id: question.id,
          sequence_order: selectedQuiz.questions.length + 1,
          marks_override: null,
        },
      ]
      await api(`/quizzes/${selectedQuiz.id}/questions`, {
        method: 'PUT',
        body: jsonBody({ questions }),
      })
    }, 'Question added to the draft')
    formElement.reset()
  }

  async function publishQuiz(quizId: string) {
    await withFeedback(async () => {
      await api(`/quizzes/${quizId}/publish`, { method: 'POST' })
    }, 'Quiz published')
  }

  async function scheduleSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedQuiz) return
    const form = new FormData(event.currentTarget)
    await withFeedback(async () => {
      await api('/sessions', {
        method: 'POST',
        body: jsonBody({
          quiz_id: selectedQuiz.id,
          class_id: form.get('class_id'),
          session_mode: 'STUDENT_PACED',
          start_window_time: new Date(String(form.get('start'))).toISOString(),
          end_window_time: new Date(String(form.get('end'))).toISOString(),
          duration_minutes: Number(form.get('duration')),
          negative_marking_enabled: form.get('negative_marking') === 'on',
        }),
      })
    }, 'Session scheduled')
    event.currentTarget.reset()
  }

  async function transition(sessionId: string, action: string) {
    await withFeedback(async () => {
      await api(`/sessions/${sessionId}/${action}`, { method: 'POST' })
    }, `Session ${action} successful`)
  }

  async function loadAnalytics(sessionId: string) {
    setAnalyticsId(sessionId)
    setAnalytics(null)
    setError('')
    try {
      setAnalytics(await api<SessionAnalytics>(`/sessions/${sessionId}/analytics`))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load analytics')
    }
  }

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Faculty workspace</p>
          <h1>Build, launch, review.</h1>
          <p className="muted">Manage reusable quizzes and run classroom sessions.</p>
        </div>
        <div className="hero-stat">
          <span>{sessions.filter((session) => session.status === 'ACTIVE').length}</span>
          <small>active sessions</small>
        </div>
      </section>
      {(message || error) && (
        <p className={`notice ${error ? 'notice-error' : 'notice-success'}`}>{error || message}</p>
      )}

      <section className="two-column">
        <div className="panel">
          <p className="eyebrow">New blueprint</p>
          <h2>Create a quiz draft</h2>
          <form className="form-stack compact-form" onSubmit={createQuiz}>
            <label>
              Quiz title
              <input name="title" required maxLength={255} />
            </label>
            <label>
              Subject ID
              <input name="subject_id" required placeholder="Subject UUID" />
            </label>
            <label>
              Default duration (minutes)
              <input name="duration" type="number" min={1} defaultValue={20} required />
            </label>
            <button className="button button-primary" disabled={busy}>Create draft</button>
          </form>
        </div>
        <div className="panel">
          <p className="eyebrow">Question bank</p>
          <h2>Add an MCQ or multi-select</h2>
          <form className="form-stack compact-form" onSubmit={addQuestion}>
            <label>
              Draft quiz
              <select
                value={selectedQuizId}
                onChange={(event) => setSelectedQuizId(event.target.value)}
                required
              >
                <option value="">Select a draft quiz</option>
                {quizzes.filter((quiz) => quiz.status === 'DRAFT').map((quiz) => (
                  <option value={quiz.id} key={quiz.id}>{quiz.title}</option>
                ))}
              </select>
            </label>
            <label>
              Question type
              <select name="question_type" defaultValue="MCQ">
                <option value="MCQ">Single select</option>
                <option value="MULTIPLE_SELECT">Multiple select</option>
                <option value="TRUE_FALSE">True / False</option>
              </select>
            </label>
            <label>
              Question
              <textarea name="question_text" required rows={2} />
            </label>
            <label>
              Options (one per line)
              <textarea name="options" required rows={4} placeholder={'First option\nSecond option'} />
            </label>
            <div className="form-row">
              <label>
                Correct option numbers
                <input name="correct_indexes" required placeholder="1 or 1,3" />
              </label>
              <label>
                Marks
                <input name="marks" type="number" step="0.0001" min="0.0001" defaultValue="1" />
              </label>
            </div>
            <button className="button button-primary" disabled={busy || !selectedQuiz}>
              Add question
            </button>
          </form>
          {selectedQuiz && (
            <p className="helper-text">
              {selectedQuiz.questions.length} question(s) in {selectedQuiz.title}
            </p>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Reusable content</p>
            <h2>Your quizzes</h2>
          </div>
          <button className="button button-quiet" onClick={() => void reload()}>Refresh</button>
        </div>
        {quizzes.length === 0 ? (
          <div className="empty-state"><strong>No quizzes yet</strong><span>Create your first draft above.</span></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Title</th><th>Status</th><th>Questions</th><th>Action</th></tr></thead>
              <tbody>
                {quizzes.map((quiz) => (
                  <tr key={quiz.id}>
                    <td>{quiz.title}</td>
                    <td><span className={`status-pill status-${quiz.status.toLowerCase()}`}>{quiz.status}</span></td>
                    <td>{quiz.questions.length}</td>
                    <td>
                      {quiz.status === 'DRAFT' ? (
                        <button className="button button-small button-primary" disabled={busy} onClick={() => void publishQuiz(quiz.id)}>
                          Publish
                        </button>
                      ) : <span className="muted">Ready to schedule</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="two-column">
        <div className="panel">
          <p className="eyebrow">Classroom</p>
          <h2>Schedule a session</h2>
          <form className="form-stack compact-form" onSubmit={scheduleSession}>
            <label>
              Published quiz
              <select
                value={selectedQuizId}
                onChange={(event) => setSelectedQuizId(event.target.value)}
                required
              >
                <option value="">Select a published quiz</option>
                {quizzes.filter((quiz) => quiz.status === 'PUBLISHED').map((quiz) => (
                  <option value={quiz.id} key={quiz.id}>{quiz.title}</option>
                ))}
              </select>
            </label>
            <label>
              Class ID
              <input name="class_id" required placeholder="Class UUID" />
            </label>
            <div className="form-row">
              <label>Starts<input name="start" type="datetime-local" required /></label>
              <label>Ends<input name="end" type="datetime-local" required /></label>
            </div>
            <div className="form-row">
              <label>Duration (minutes)<input name="duration" type="number" min={1} defaultValue={20} required /></label>
              <label className="checkbox-label">
                <input name="negative_marking" type="checkbox" />
                Enable negative marking
              </label>
            </div>
            <button className="button button-primary" disabled={busy || selectedQuiz?.status !== 'PUBLISHED'}>
              Schedule session
            </button>
          </form>
        </div>
        <div className="panel">
          <div className="section-heading">
            <div><p className="eyebrow">Live and recent</p><h2>Sessions</h2></div>
          </div>
          {sessions.length === 0 ? (
            <div className="empty-state"><strong>No sessions scheduled</strong><span>Publish a quiz to schedule one.</span></div>
          ) : (
            <div className="session-list">
              {sessions.map((session) => (
                <article className="session-list-item" key={session.id}>
                  <div>
                    <span className={`status-pill status-${session.status.toLowerCase()}`}>{session.status}</span>
                    <p className="session-code">{session.session_code}</p>
                    <small className="muted">{new Date(session.start_window_time).toLocaleString()}</small>
                  </div>
                  <div className="session-controls">
                    {transitionActions.map((action) => (
                      <button
                        className="button button-small button-quiet"
                        key={action}
                        disabled={
                          busy ||
                          (action === 'activate' && session.status !== 'SCHEDULED') ||
                          (action === 'pause' && session.status !== 'ACTIVE') ||
                          (action === 'resume' && session.status !== 'PAUSED') ||
                          (action === 'complete' && !['ACTIVE', 'PAUSED'].includes(session.status)) ||
                          (action === 'cancel' && !['ACTIVE', 'PAUSED', 'SCHEDULED'].includes(session.status))
                        }
                        onClick={() => void transition(session.id, action)}
                      >
                        {action}
                      </button>
                    ))}
                    <button className="button button-small button-primary" onClick={() => void loadAnalytics(session.id)}>
                      Analytics
                    </button>
                    {session.status === 'COMPLETED' &&
                      session.result_visibility === 'UPON_FACULTY_RELEASE' &&
                      !session.results_released_at && (
                        <button
                          className="button button-small button-warning"
                          disabled={busy}
                          onClick={() => void withFeedback(async () => {
                            await api(`/sessions/${session.id}/release-results`, { method: 'POST' })
                          }, 'Results released to students')}
                        >
                          Release results
                        </button>
                      )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>

      {analytics && analyticsId && (
        <section className="panel">
          <p className="eyebrow">Session analytics</p>
          <h2>Participation and results</h2>
          <div className="metric-row">
            <Metric label="Joined" value={analytics.total_attempts} />
            <Metric label="In progress" value={analytics.in_progress_attempts} />
            <Metric label="Submitted" value={analytics.finalized_attempts} />
            <Metric label="Average score" value={analytics.average_score ?? '—'} />
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Student</th><th>Status</th><th>Score</th></tr></thead>
              <tbody>
                {analytics.attempts.map((attempt) => (
                  <tr key={attempt.attempt_id}>
                    <td>{attempt.first_name} {attempt.last_name}</td>
                    <td>{attempt.status}</td>
                    <td>{attempt.total_score ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="subheading">Question performance</h3>
          <div className="question-performance">
            {analytics.question_performance.map((question) => (
              <div key={question.question_id}>
                <span>Q{question.sequence_order}</span>
                <strong>{question.question_text}</strong>
                <small>{question.correct_count} correct · {question.response_count} answered · avg {question.average_awarded_marks}</small>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric-card"><span>{value}</span><small>{label}</small></div>
}
