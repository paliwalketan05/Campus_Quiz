import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, jsonBody } from '../lib/api'
import type { Attempt, AttemptQuestion, AttemptResult } from '../types'

interface ResponseState {
  selected_option_ids: string[]
  is_marked_for_review: boolean
  client_version: number
}

interface AttemptSnapshot extends Attempt {
  session_id?: string
}

interface AttemptStateResponse {
  attempt_id: string
  session_id: string
  status: 'IN_PROGRESS' | 'FINALIZED'
  deadline: string
  responses: Array<ResponseState & { question_id: string }>
}

function cachedAttempt(attemptId: string): AttemptSnapshot | null {
  const value = sessionStorage.getItem(`campusquiz-attempt-${attemptId}`)
  if (!value) return null
  try {
    return JSON.parse(value) as AttemptSnapshot
  } catch {
    sessionStorage.removeItem(`campusquiz-attempt-${attemptId}`)
    return null
  }
}

export function AttemptPage() {
  const { attemptId = '' } = useParams()
  const navigate = useNavigate()
  const [attempt, setAttempt] = useState<AttemptSnapshot | null>(() =>
    cachedAttempt(attemptId),
  )
  const [responses, setResponses] = useState<Record<string, ResponseState>>({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null)
  const [saveMessage, setSaveMessage] = useState('All changes saved')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const saveTimer = useRef<number | undefined>(undefined)
  const submittedRef = useRef(false)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const state = await api<AttemptStateResponse>(`/attempts/${attemptId}`)
        if (!active) return
        const initialResponses: Record<string, ResponseState> = {}
        for (const response of state.responses) {
          initialResponses[response.question_id] = {
            selected_option_ids: response.selected_option_ids,
            is_marked_for_review: response.is_marked_for_review,
            client_version: response.client_version,
          }
        }
        setResponses(initialResponses)
        const cached = cachedAttempt(attemptId)
        if (cached?.questions?.length) {
          setAttempt(cached)
        } else {
          const started = await api<AttemptSnapshot>(
            `/attempts/sessions/${state.session_id}/start`,
            { method: 'POST' },
          )
          if (!active) return
          const snapshot = { ...started, session_id: state.session_id }
          setAttempt(snapshot)
          sessionStorage.setItem(`campusquiz-attempt-${attemptId}`, JSON.stringify(snapshot))
        }
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Unable to load this attempt')
        }
      }
    }
    void load()
    return () => {
      active = false
      window.clearTimeout(saveTimer.current)
    }
  }, [attemptId])

  const questions = attempt?.questions ?? []
  const question: AttemptQuestion | undefined = questions[currentIndex]
  const currentResponse = question
    ? responses[question.question_id] ?? {
        selected_option_ids: [],
        is_marked_for_review: false,
        client_version: 0,
      }
    : undefined

  const saveResponse = useCallback(
    async (questionId: string, value: ResponseState) => {
      if (submittedRef.current) return
      setSaveMessage('Saving…')
      try {
        const saved = await api<{
          result_status: string
          saved_version: number
        }>(`/attempts/${attemptId}/responses/${questionId}`, {
          method: 'PUT',
          body: jsonBody({
            selected_option_ids: value.selected_option_ids,
            is_marked_for_review: value.is_marked_for_review,
            client_version: value.client_version,
            client_submitted_at: new Date().toISOString(),
          }),
        })
        if (saved.result_status === 'STALE_REJECTED' || saved.result_status === 'VERSION_CONFLICT') {
          setSaveMessage(`Sync conflict at version ${saved.saved_version}; edit again to retry`)
        } else {
          setSaveMessage('All changes saved')
        }
      } catch (reason) {
        setSaveMessage('Not synced — check your connection')
        setError(reason instanceof Error ? reason.message : 'Response could not be saved')
      }
    },
    [attemptId],
  )

  function updateResponse(next: ResponseState) {
    if (!question) return
    const versioned = { ...next, client_version: (currentResponse?.client_version ?? 0) + 1 }
    setResponses((existing) => ({ ...existing, [question.question_id]: versioned }))
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(
      () => void saveResponse(question.question_id, versioned),
      300,
    )
  }

  function toggleOption(optionId: string) {
    if (!question || !currentResponse) return
    const chosen = currentResponse.selected_option_ids.includes(optionId)
    const selected =
      question.question_type === 'MULTIPLE_SELECT'
        ? chosen
          ? currentResponse.selected_option_ids.filter((id) => id !== optionId)
          : [...currentResponse.selected_option_ids, optionId]
        : chosen
          ? []
          : [optionId]
    updateResponse({ ...currentResponse, selected_option_ids: selected })
  }

  async function submitAttempt(submissionType: 'MANUAL' | 'AUTO_TIME_EXPIRED') {
    if (submittedRef.current) return
    submittedRef.current = true
    setSubmitting(true)
    try {
      const result = await api<AttemptResult>(`/attempts/${attemptId}/submit`, {
        method: 'POST',
        body: jsonBody({ submission_type: submissionType }),
      })
      navigate(`/student/results/${attemptId}`, { state: { result } })
    } catch (reason) {
      submittedRef.current = false
      setError(reason instanceof Error ? reason.message : 'Could not submit the attempt')
    } finally {
      setSubmitting(false)
    }
  }

  useEffect(() => {
    if (!attempt?.deadline) return
    const tick = () => {
      const seconds = Math.max(
        0,
        Math.ceil((new Date(attempt.deadline).getTime() - Date.now()) / 1000),
      )
      setRemainingSeconds(seconds)
      if (seconds === 0 && !submittedRef.current) {
        void submitAttempt('AUTO_TIME_EXPIRED')
      }
    }
    tick()
    const interval = window.setInterval(tick, 1000)
    return () => window.clearInterval(interval)
  }, [attempt?.deadline])

  const answeredCount = useMemo(
    () => Object.values(responses).filter((value) => value.selected_option_ids.length > 0).length,
    [responses],
  )

  if (error && !attempt) {
    return (
      <section className="panel">
        <p className="notice notice-error">{error}</p>
        <Link className="button button-quiet" to="/student">Return to dashboard</Link>
      </section>
    )
  }
  if (!attempt || !question || !currentResponse) {
    return <section className="panel muted">Loading your secure quiz…</section>
  }

  return (
    <div className="attempt-layout">
      <section className="attempt-main">
        <div className="attempt-heading">
          <div>
            <p className="eyebrow">Question {currentIndex + 1} of {questions.length}</p>
            <h1>Your quiz</h1>
          </div>
          <div className={`timer ${remainingSeconds !== null && remainingSeconds < 60 ? 'timer-low' : ''}`}>
            {remainingSeconds === null
              ? '—:—'
              : `${Math.floor(remainingSeconds / 60)
                  .toString()
                  .padStart(2, '0')}:${(remainingSeconds % 60).toString().padStart(2, '0')}`}
          </div>
        </div>
        <div className="question-panel">
          <div className="question-meta">
            <span>{question.question_type.replace('_', ' ')}</span>
            <span>{question.marks} marks</span>
          </div>
          <h2>{question.question_text}</h2>
          <p className="muted">
            {question.question_type === 'MULTIPLE_SELECT'
              ? 'Select all answers that apply.'
              : 'Choose one answer.'}
          </p>
          <div className="option-list">
            {question.options.map((option) => {
              const selected = currentResponse.selected_option_ids.includes(option.option_id)
              return (
                <button
                  type="button"
                  className={`answer-option ${selected ? 'answer-option-selected' : ''}`}
                  key={option.option_id}
                  onClick={() => toggleOption(option.option_id)}
                  aria-pressed={selected}
                >
                  <span className="option-marker">{String.fromCharCode(64 + option.display_order)}</span>
                  <span>{option.option_text}</span>
                  {selected && <span className="option-check">Selected</span>}
                </button>
              )
            })}
          </div>
          <div className="attempt-actions">
            <button
              className={`button ${currentResponse.is_marked_for_review ? 'button-warning' : 'button-quiet'}`}
              onClick={() =>
                updateResponse({
                  ...currentResponse,
                  is_marked_for_review: !currentResponse.is_marked_for_review,
                })
              }
            >
              {currentResponse.is_marked_for_review ? 'Marked for review' : 'Mark for review'}
            </button>
            <span className="autosave-status">{saveMessage}</span>
          </div>
        </div>
        <div className="question-navigation">
          <button
            className="button button-quiet"
            disabled={currentIndex === 0}
            onClick={() => setCurrentIndex((index) => index - 1)}
          >
            Previous
          </button>
          <button
            className="button button-primary"
            disabled={currentIndex === questions.length - 1}
            onClick={() => setCurrentIndex((index) => index + 1)}
          >
            Next question
          </button>
        </div>
        {error && <p className="notice notice-error">{error}</p>}
      </section>

      <aside className="attempt-sidebar">
        <div className="panel">
          <p className="eyebrow">Question palette</p>
          <p className="muted">{answeredCount} of {questions.length} answered</p>
          <div className="question-palette">
            {questions.map((item, index) => {
              const answer = responses[item.question_id]
              const answered = Boolean(answer?.selected_option_ids.length)
              return (
                <button
                  key={item.question_id}
                  className={[
                    'palette-item',
                    index === currentIndex ? 'palette-current' : '',
                    answered ? 'palette-answered' : '',
                    answer?.is_marked_for_review ? 'palette-review' : '',
                  ].join(' ')}
                  onClick={() => setCurrentIndex(index)}
                  aria-label={`Go to question ${index + 1}${answered ? ', answered' : ''}`}
                >
                  {index + 1}
                </button>
              )
            })}
          </div>
          <button
            className="button button-danger button-wide"
            disabled={submitting}
            onClick={() => {
              if (window.confirm('Submit your quiz now? You cannot change answers after submission.')) {
                void submitAttempt('MANUAL')
              }
            }}
          >
            {submitting ? 'Submitting…' : 'Submit quiz'}
          </button>
          <p className="helper-text">Your deadline is enforced by the server.</p>
        </div>
      </aside>
    </div>
  )
}
