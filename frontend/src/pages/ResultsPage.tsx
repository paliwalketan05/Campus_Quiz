import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../lib/api'
import type { AttemptResult } from '../types'

export function ResultsPage() {
  const { attemptId = '' } = useParams()
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    api<AttemptResult>(`/attempts/${attemptId}/results`)
      .then((value) => {
        if (active) setResult(value)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Could not load results')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [attemptId])

  if (loading) return <section className="panel muted">Loading results…</section>
  if (error) return <section className="panel notice notice-error">{error}</section>
  if (!result) return null
  if (!result.is_results_released) {
    return (
      <section className="panel results-pending">
        <span className="pending-icon">⌛</span>
        <p className="eyebrow">Attempt submitted</p>
        <h1>Your results are not released yet</h1>
        <p className="muted">
          Your teacher controls when the score and answer review become available.
        </p>
        <Link className="button button-quiet" to="/student">Back to dashboard</Link>
      </section>
    )
  }

  return (
    <div className="page-stack">
      <section className="hero-panel results-hero">
        <div>
          <p className="eyebrow">Results released</p>
          <h1>Quiz review</h1>
          <p className="muted">Your score and question-by-question review are ready.</p>
        </div>
        <div className="score-display">
          <strong>{result.total_score ?? '—'}</strong>
          <span>total score</span>
        </div>
      </section>
      {(result.question_breakdown ?? []).map((question) => (
        <article className="panel result-question" key={question.question_id}>
          <div className="result-question-heading">
            <div>
              <p className="eyebrow">Question {question.sequence_order}</p>
              <h2>{question.question_text}</h2>
            </div>
            <span className={question.is_correct ? 'result-mark result-correct' : 'result-mark'}>
              {question.awarded_marks} / {question.marks}
            </span>
          </div>
          <div className="result-options">
            {question.options.map((option) => (
              <div
                key={option.option_id}
                className={`result-option ${option.is_correct ? 'result-option-correct' : ''} ${
                  question.selected_option_ids.includes(option.option_id) ? 'result-option-selected' : ''
                }`}
              >
                <span>{option.option_text}</span>
                <span>
                  {option.is_correct ? 'Correct answer' : ''}
                  {question.selected_option_ids.includes(option.option_id) ? ' · Your choice' : ''}
                </span>
              </div>
            ))}
          </div>
          {question.explanation && (
            <p className="explanation"><strong>Explanation:</strong> {question.explanation}</p>
          )}
        </article>
      ))}
      <Link className="button button-quiet" to="/student">Back to dashboard</Link>
    </div>
  )
}
