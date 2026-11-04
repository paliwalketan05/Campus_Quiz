from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.core.hmac_tickets import create_actor_ticket
from app.schemas.auth import AuthenticatedUser
from app.schemas.execution import AttemptResponseWrite, SessionCodeRequest
from app.services.procedure_errors import translate_procedure_error


def _ticket(actor: AuthenticatedUser, settings: Settings, *, role: str = "ANY") -> str:
    return create_actor_ticket(
        user_id=str(actor.id),
        token_version=actor.token_version,
        role=role,
        settings=settings,
    )


async def _call_procedure(
    connection: AsyncConnection,
    statement: str,
    parameters: Mapping[str, object],
    *,
    commit: bool = False,
) -> Mapping[str, Any]:
    try:
        result = await connection.execute(text(statement), parameters)
        row = result.mappings().one()
        if commit:
            await connection.commit()
        return row
    except DBAPIError as exc:
        await connection.rollback()
        translated = translate_procedure_error(exc)
        if translated is not None:
            raise translated from exc
        raise


async def list_student_sessions(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    *,
    limit: int,
    offset: int,
) -> list[Mapping[str, Any]]:
    result = await connection.execute(
        text(
            """
            SELECT qs.id, qs.quiz_id, qs.session_code, qs.session_mode, qs.status,
                   qs.start_window_time, qs.end_window_time, qs.duration_minutes,
                   q.title AS quiz_title, q.instructions, q.total_marks
            FROM quiz_sessions AS qs
            JOIN quizzes AS q
              ON q.id = qs.quiz_id
             AND q.college_id = qs.college_id
            JOIN classes AS c
              ON c.id = qs.class_id
             AND c.college_id = qs.college_id
            JOIN student_enrollments AS se
              ON se.class_id = qs.class_id
             AND se.academic_year_id = c.academic_year_id
             AND se.college_id = qs.college_id
            WHERE qs.college_id = :college_id
              AND se.student_user_id = :student_id
              AND se.is_active = TRUE
              AND qs.status = 'ACTIVE'
              AND CURRENT_TIMESTAMP BETWEEN qs.start_window_time AND qs.end_window_time
            ORDER BY qs.start_window_time, qs.id
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "college_id": actor.college_id,
            "student_id": actor.id,
            "limit": limit,
            "offset": offset,
        },
    )
    return list(result.mappings().all())


async def lookup_session(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    payload: SessionCodeRequest,
) -> Mapping[str, Any]:
    result = await connection.execute(
        text(
            """
            SELECT qs.id, qs.quiz_id, qs.session_code, qs.session_mode, qs.status,
                   qs.start_window_time, qs.end_window_time, qs.duration_minutes,
                   q.title AS quiz_title, q.instructions, q.total_marks
            FROM quiz_sessions AS qs
            JOIN quizzes AS q
              ON q.id = qs.quiz_id
             AND q.college_id = qs.college_id
            JOIN classes AS c
              ON c.id = qs.class_id
             AND c.college_id = qs.college_id
            WHERE qs.college_id = :college_id
              AND qs.session_code = :session_code
              AND qs.status = 'ACTIVE'
              AND CURRENT_TIMESTAMP BETWEEN qs.start_window_time AND qs.end_window_time
              AND EXISTS (
                  SELECT 1
                  FROM student_enrollments AS se
                  WHERE se.college_id = qs.college_id
                    AND se.student_user_id = :student_id
                    AND se.class_id = qs.class_id
                    AND se.academic_year_id = c.academic_year_id
                    AND se.is_active = TRUE
              )
            """
        ),
        {
            "college_id": actor.college_id,
            "student_id": actor.id,
            "session_code": payload.session_code,
        },
    )
    session = result.mappings().one_or_none()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="No active session with that code is available to this student",
        )
    return session


async def start_attempt(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    session_id: UUID,
    settings: Settings,
) -> Mapping[str, Any]:
    row = await _call_procedure(
        connection,
        """
        SELECT attempt_id, status, deadline, duration_minutes, snapshot_questions
        FROM sp_start_quiz_attempt(:session_id, :actor_id, :auth_signature)
        """,
        {
            "session_id": session_id,
            "actor_id": actor.id,
            "auth_signature": _ticket(actor, settings, role="STUDENT"),
        },
        commit=True,
    )
    return {
        "attempt_id": row["attempt_id"],
        "status": row["status"],
        "deadline": row["deadline"],
        "duration_minutes": row["duration_minutes"],
        "questions": row["snapshot_questions"] or [],
    }


async def _require_owned_attempt(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    attempt_id: UUID,
) -> Mapping[str, Any]:
    result = await connection.execute(
        text(
            """
            SELECT id, session_id, student_user_id, status, deadline,
                   submitted_at, finalized_at
            FROM quiz_attempts
            WHERE id = :attempt_id
              AND college_id = :college_id
              AND student_user_id = :student_id
            """
        ),
        {
            "attempt_id": attempt_id,
            "college_id": actor.college_id,
            "student_id": actor.id,
        },
    )
    attempt = result.mappings().one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt


async def get_attempt_state(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    attempt_id: UUID,
) -> Mapping[str, Any]:
    attempt = await _require_owned_attempt(connection, actor, attempt_id)
    responses_result = await connection.execute(
        text(
            """
            SELECT question_id, selected_option_ids, is_marked_for_review,
                   client_version, client_submitted_at, server_received_at
            FROM student_responses
            WHERE attempt_id = :attempt_id
            ORDER BY question_id
            """
        ),
        {"attempt_id": attempt_id},
    )
    responses = []
    for row in responses_result.mappings().all():
        response = dict(row)
        response["selected_option_ids"] = response["selected_option_ids"] or []
        responses.append(response)
    return {
        "attempt_id": attempt["id"],
        "session_id": attempt["session_id"],
        "status": attempt["status"],
        "deadline": attempt["deadline"],
        "submitted_at": attempt["submitted_at"],
        "finalized_at": attempt["finalized_at"],
        "responses": responses,
    }


async def save_response(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    attempt_id: UUID,
    question_id: UUID,
    payload: AttemptResponseWrite,
    settings: Settings,
) -> Mapping[str, Any]:
    await _require_owned_attempt(connection, actor, attempt_id)
    return await _call_procedure(
        connection,
        """
        SELECT result_status, saved_version
        FROM sp_save_student_response(
            :attempt_id,
            :question_id,
            CAST(:selected_option_ids AS UUID[]),
            :is_marked_for_review,
            :client_version,
            :client_submitted_at,
            :actor_id,
            :auth_signature
        )
        """,
        {
            "attempt_id": attempt_id,
            "question_id": question_id,
            "selected_option_ids": payload.selected_option_ids,
            "is_marked_for_review": payload.is_marked_for_review,
            "client_version": payload.client_version,
            "client_submitted_at": payload.client_submitted_at,
            "actor_id": actor.id,
            "auth_signature": _ticket(actor, settings, role="STUDENT"),
        },
        commit=True,
    )


async def finalize_attempt(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    attempt_id: UUID,
    submission_type: str,
    settings: Settings,
) -> Mapping[str, Any]:
    attempt = await _require_owned_attempt(connection, actor, attempt_id)
    if submission_type == "AUTO_TIME_EXPIRED":
        deadline_result = await connection.execute(
            text("SELECT :deadline < CURRENT_TIMESTAMP"),
            {"deadline": attempt["deadline"]},
        )
        if not deadline_result.scalar_one():
            raise HTTPException(
                status_code=409,
                detail="The attempt deadline has not expired",
            )
    ticket_role = "STUDENT" if submission_type == "MANUAL" else "ANY"
    return await _call_procedure(
        connection,
        """
        SELECT final_status, total_score, finalized_at
        FROM sp_finalize_attempt(
            :attempt_id, :submission_type, :actor_id, :auth_signature
        )
        """,
        {
            "attempt_id": attempt_id,
            "submission_type": submission_type,
            "actor_id": actor.id,
            "auth_signature": _ticket(actor, settings, role=ticket_role),
        },
        commit=True,
    )


async def get_attempt_results(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    attempt_id: UUID,
    settings: Settings,
) -> Mapping[str, Any]:
    access_result = await connection.execute(
        text(
            """
            SELECT a.student_user_id, a.college_id, s.faculty_user_id
            FROM quiz_attempts AS a
            JOIN quiz_sessions AS s
              ON s.id = a.session_id
             AND s.college_id = a.college_id
            WHERE a.id = :attempt_id
              AND a.college_id = :college_id
            """
        ),
        {"attempt_id": attempt_id, "college_id": actor.college_id},
    )
    attempt = access_result.mappings().one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if actor.id != attempt["student_user_id"] and actor.id != attempt["faculty_user_id"] and "ADMIN" not in actor.roles:
        raise HTTPException(status_code=404, detail="Attempt not found")

    return await _call_procedure(
        connection,
        """
        SELECT attempt_id, status, is_results_released, total_score, question_breakdown
        FROM sp_get_student_attempt_results(:attempt_id, :actor_id, :auth_signature)
        """,
        {
            "attempt_id": attempt_id,
            "actor_id": actor.id,
            "auth_signature": _ticket(actor, settings),
        },
    )


async def session_analytics(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    session_id: UUID,
    settings: Settings,
) -> Mapping[str, Any]:
    owner_filter = "" if "ADMIN" in actor.roles else "AND s.faculty_user_id = :actor_id"
    parameters: dict[str, object] = {
        "session_id": session_id,
        "college_id": actor.college_id,
    }
    if "ADMIN" not in actor.roles:
        parameters["actor_id"] = actor.id
    session_result = await connection.execute(
        text(
            f"""
            SELECT s.id, s.status
            FROM quiz_sessions AS s
            WHERE s.id = :session_id
              AND s.college_id = :college_id
              {owner_filter}
            """
        ),
        parameters,
    )
    session = session_result.mappings().one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    attempts_result = await connection.execute(
        text(
            """
            SELECT a.id AS attempt_id, a.student_user_id, u.first_name, u.last_name,
                   a.status, a.deadline, a.submitted_at, a.finalized_at, a.total_score
            FROM quiz_attempts AS a
            JOIN users AS u
              ON u.id = a.student_user_id
             AND u.college_id = a.college_id
            WHERE a.college_id = :college_id
              AND a.session_id = :session_id
            ORDER BY u.last_name, u.first_name, a.id
            """
        ),
        {"college_id": actor.college_id, "session_id": session_id},
    )
    attempts = [dict(row) for row in attempts_result.mappings().all()]
    finalized = [row for row in attempts if row["status"] == "FINALIZED"]
    scores = [row["total_score"] for row in finalized if row["total_score"] is not None]

    performance: dict[UUID, dict[str, Any]] = {}
    ticket = _ticket(actor, settings)
    for attempt in finalized:
        result = await connection.execute(
            text(
                """
                SELECT question_breakdown
                FROM sp_get_student_attempt_results(
                    :attempt_id, :actor_id, :auth_signature
                )
                """
            ),
            {
                "attempt_id": attempt["attempt_id"],
                "actor_id": actor.id,
                "auth_signature": ticket,
            },
        )
        breakdown = result.scalar_one_or_none() or []
        for question in breakdown:
            question_id = UUID(str(question["question_id"]))
            aggregate = performance.setdefault(
                question_id,
                {
                    "question_id": question_id,
                    "sequence_order": question["sequence_order"],
                    "question_text": question["question_text"],
                    "response_count": 0,
                    "correct_count": 0,
                    "awarded_marks_sum": Decimal("0"),
                },
            )
            if question["selected_option_ids"]:
                aggregate["response_count"] += 1
            if question["is_correct"]:
                aggregate["correct_count"] += 1
            aggregate["awarded_marks_sum"] += Decimal(str(question["awarded_marks"]))

    question_performance = []
    for aggregate in sorted(performance.values(), key=lambda row: row["sequence_order"]):
        question_performance.append(
            {
                "question_id": aggregate["question_id"],
                "sequence_order": aggregate["sequence_order"],
                "question_text": aggregate["question_text"],
                "response_count": aggregate["response_count"],
                "correct_count": aggregate["correct_count"],
                "average_awarded_marks": (
                    aggregate["awarded_marks_sum"] / len(finalized)
                    if finalized
                    else Decimal("0")
                ),
            }
        )

    return {
        "session_id": session["id"],
        "status": session["status"],
        "total_attempts": len(attempts),
        "in_progress_attempts": sum(row["status"] == "IN_PROGRESS" for row in attempts),
        "finalized_attempts": len(finalized),
        "average_score": sum(scores, Decimal("0")) / len(scores) if scores else None,
        "highest_score": max(scores) if scores else None,
        "lowest_score": min(scores) if scores else None,
        "attempts": attempts,
        "question_performance": question_performance,
    }
