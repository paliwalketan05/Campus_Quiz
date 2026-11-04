from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.authoring import AuthoringModel


class SessionCodeRequest(AuthoringModel):
    session_code: Annotated[str, Field(min_length=6, max_length=10)]

    @field_validator("session_code")
    @classmethod
    def normalize_session_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalnum():
            raise ValueError("Session code must contain only letters and numbers")
        return normalized


class StudentSessionRead(AuthoringModel):
    id: UUID
    quiz_id: UUID
    session_code: str
    session_mode: Literal["STUDENT_PACED", "TEACHER_CONTROLLED"]
    status: Literal["SCHEDULED", "ACTIVE"]
    start_window_time: datetime
    end_window_time: datetime
    duration_minutes: int
    quiz_title: str
    instructions: str | None
    total_marks: Decimal


class AttemptOptionRead(AuthoringModel):
    option_id: UUID
    option_text: str
    display_order: int


class AttemptQuestionRead(AuthoringModel):
    question_id: UUID
    sequence_order: int
    question_type: Literal["MCQ", "TRUE_FALSE", "MULTIPLE_SELECT"]
    question_text: str
    marks: Decimal
    negative_penalty: Decimal
    options: list[AttemptOptionRead]


class AttemptStartRead(AuthoringModel):
    attempt_id: UUID
    status: Literal["IN_PROGRESS", "FINALIZED"]
    deadline: datetime
    duration_minutes: int
    questions: list[AttemptQuestionRead]


class AttemptResponseWrite(AuthoringModel):
    selected_option_ids: Annotated[list[UUID], Field(max_length=100)] = Field(
        default_factory=list
    )
    is_marked_for_review: bool = False
    client_version: int = Field(ge=1, le=2_147_483_647)
    client_submitted_at: datetime | None = None

    @field_validator("client_submitted_at")
    @classmethod
    def require_timestamp_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("client_submitted_at must include a timezone")
        return value


class AttemptResponseRead(AuthoringModel):
    result_status: Literal[
        "ACCEPTED",
        "IDEMPOTENT_RETRY",
        "VERSION_CONFLICT",
        "STALE_REJECTED",
    ]
    saved_version: int


class AttemptResponseState(AuthoringModel):
    question_id: UUID
    selected_option_ids: list[UUID]
    is_marked_for_review: bool
    client_version: int
    client_submitted_at: datetime | None
    server_received_at: datetime


class AttemptStateRead(AuthoringModel):
    attempt_id: UUID
    session_id: UUID
    status: Literal["IN_PROGRESS", "FINALIZED"]
    deadline: datetime
    submitted_at: datetime | None
    finalized_at: datetime | None
    responses: list[AttemptResponseState]


class AttemptFinalizeRequest(AuthoringModel):
    submission_type: Literal["MANUAL", "AUTO_TIME_EXPIRED"] = "MANUAL"


class AttemptFinalizeRead(AuthoringModel):
    final_status: Literal["FINALIZED"]
    total_score: Decimal
    finalized_at: datetime


class ResultQuestionRead(AuthoringModel):
    question_id: UUID
    sequence_order: int
    question_text: str
    question_type: Literal["MCQ", "TRUE_FALSE", "MULTIPLE_SELECT"]
    marks: Decimal
    awarded_marks: Decimal
    is_correct: bool
    selected_option_ids: list[UUID]
    explanation: str | None
    options: list[dict[str, object]]


class AttemptResultsRead(AuthoringModel):
    attempt_id: UUID
    status: Literal["IN_PROGRESS", "FINALIZED"]
    is_results_released: bool
    total_score: Decimal | None
    question_breakdown: list[ResultQuestionRead] | None


class SessionAttemptSummary(AuthoringModel):
    attempt_id: UUID
    student_user_id: UUID
    first_name: str
    last_name: str
    status: Literal["IN_PROGRESS", "FINALIZED"]
    deadline: datetime
    submitted_at: datetime | None
    finalized_at: datetime | None
    total_score: Decimal | None


class QuestionPerformance(AuthoringModel):
    question_id: UUID
    sequence_order: int
    question_text: str
    response_count: int
    correct_count: int
    average_awarded_marks: Decimal


class SessionAnalyticsRead(AuthoringModel):
    session_id: UUID
    status: str
    total_attempts: int
    in_progress_attempts: int
    finalized_attempts: int
    average_score: Decimal | None
    highest_score: Decimal | None
    lowest_score: Decimal | None
    attempts: list[SessionAttemptSummary]
    question_performance: list[QuestionPerformance]
