export type Role = 'ADMIN' | 'FACULTY' | 'STUDENT'

export interface UserProfile {
  id: string
  college_id: string
  email: string
  first_name: string
  last_name: string
  roles: Role[]
  must_change_password: boolean
}

export interface StudentSession {
  id: string
  quiz_id: string
  session_code: string
  session_mode: 'STUDENT_PACED' | 'TEACHER_CONTROLLED'
  status: 'SCHEDULED' | 'ACTIVE'
  start_window_time: string
  end_window_time: string
  duration_minutes: number
  quiz_title: string
  instructions: string | null
  total_marks: string
}

export interface AttemptQuestion {
  question_id: string
  sequence_order: number
  question_type: 'MCQ' | 'TRUE_FALSE' | 'MULTIPLE_SELECT'
  question_text: string
  marks: string
  negative_penalty: string
  options: Array<{
    option_id: string
    option_text: string
    display_order: number
  }>
}

export interface Attempt {
  attempt_id: string
  status: 'IN_PROGRESS' | 'FINALIZED'
  deadline: string
  duration_minutes: number
  questions: AttemptQuestion[]
}

export interface AttemptResult {
  attempt_id: string
  status: 'IN_PROGRESS' | 'FINALIZED'
  is_results_released: boolean
  total_score: string | null
  question_breakdown: Array<{
    question_id: string
    sequence_order: number
    question_text: string
    question_type: string
    marks: string
    awarded_marks: string
    is_correct: boolean
    selected_option_ids: string[]
    explanation: string | null
    options: Array<{
      option_id: string
      option_text: string
      is_correct: boolean
      display_order: number
    }>
  }> | null
}

export interface Quiz {
  id: string
  title: string
  subject_id: string
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  default_duration_minutes: number
  questions: Array<{
    question_id: string
    sequence_order: number
    marks_override: string | null
  }>
}

export interface QuizSession {
  id: string
  quiz_id: string
  class_id: string
  session_code: string
  status: 'SCHEDULED' | 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'CANCELLED'
  start_window_time: string
  end_window_time: string
  duration_minutes: number
  results_released_at: string | null
  result_visibility: 'IMMEDIATELY' | 'AFTER_SESSION_ENDS' | 'UPON_FACULTY_RELEASE'
}

export interface SessionAnalytics {
  total_attempts: number
  in_progress_attempts: number
  finalized_attempts: number
  average_score: string | null
  highest_score: string | null
  lowest_score: string | null
  attempts: Array<{
    attempt_id: string
    first_name: string
    last_name: string
    status: 'IN_PROGRESS' | 'FINALIZED'
    total_score: string | null
  }>
  question_performance: Array<{
    question_id: string
    sequence_order: number
    question_text: string
    response_count: number
    correct_count: number
    average_awarded_marks: string
  }>
}
