from collections.abc import Mapping
from collections.abc import Awaitable, Callable
import secrets
from typing import Any, TypeVar
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.core.hmac_tickets import create_actor_ticket
from app.schemas.auth import AuthenticatedUser
from app.schemas.lifecycle import QuizSessionCreate
from app.services import authoring_service
from app.services.procedure_errors import translate_procedure_error

_SESSION_SELECT = """
    SELECT id, college_id, quiz_id, faculty_user_id, class_id, session_code,
           session_mode, status, start_window_time, end_window_time,
           actual_started_at, actual_ended_at, duration_minutes,
           negative_marking_enabled, negative_penalty, result_visibility,
           results_released_at, created_at, updated_at
    FROM quiz_sessions
"""
_SESSION_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_SESSION_PROCEDURES = {
    "activate": "sp_activate_quiz_session",
    "pause": "sp_pause_quiz_session",
    "resume": "sp_resume_quiz_session",
    "complete": "sp_complete_quiz_session",
    "cancel": "sp_cancel_quiz_session",
}
Result = TypeVar("Result")


def _is_admin(actor: AuthenticatedUser) -> bool:
    return "ADMIN" in actor.roles


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Quiz or session not found")


async def _commit_mutation(
    connection: AsyncConnection,
    operation: Callable[[], Awaitable[Result]],
) -> Result:
    try:
        result = await operation()
        await connection.commit()
        return result
    except IntegrityError as exc:
        await connection.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The change conflicts with existing quiz or session records",
        ) from exc
    except DBAPIError as exc:
        await connection.rollback()
        translated = translate_procedure_error(exc)
        if translated is not None:
            raise translated from exc
        raise
    except HTTPException:
        await connection.rollback()
        raise


async def _require_faculty_subject_assignment(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    *,
    faculty_user_id: UUID,
    subject_id: UUID,
    class_id: UUID,
) -> None:
    result = await connection.execute(
        text(
            """
            SELECT 1
            FROM classes AS c
            JOIN faculty_assignments AS fa
              ON fa.college_id = c.college_id
             AND fa.class_id = c.id
             AND fa.academic_year_id = c.academic_year_id
            JOIN users AS u
              ON u.id = fa.faculty_user_id
             AND u.college_id = fa.college_id
            WHERE c.college_id = :college_id
              AND c.id = :class_id
              AND fa.faculty_user_id = :faculty_user_id
              AND fa.subject_id = :subject_id
              AND fa.is_active = TRUE
              AND u.is_active = TRUE
              AND EXISTS (
                  SELECT 1
                  FROM user_roles AS ur
                  WHERE ur.college_id = fa.college_id
                    AND ur.user_id = fa.faculty_user_id
                    AND ur.role_code = 'FACULTY'
              )
            LIMIT 1
            """
        ),
        {
            "college_id": actor.college_id,
            "class_id": class_id,
            "faculty_user_id": faculty_user_id,
            "subject_id": subject_id,
        },
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=403,
            detail="The quiz faculty member is not actively assigned to this subject and class",
        )


async def publish_quiz(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    quiz_id: UUID,
    settings: Settings,
) -> Mapping[str, Any]:
    quiz = await authoring_service.get_quiz(connection, actor, quiz_id)
    if not _is_admin(actor):
        assignment = await connection.execute(
            text(
                """
                SELECT 1
                FROM faculty_assignments
                WHERE college_id = :college_id
                  AND faculty_user_id = :actor_id
                  AND subject_id = :subject_id
                  AND is_active = TRUE
                LIMIT 1
                """
            ),
            {
                "college_id": actor.college_id,
                "actor_id": actor.id,
                "subject_id": quiz["subject_id"],
            },
        )
        if assignment.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=403,
                detail="No active faculty assignment for this subject",
            )

    signature = create_actor_ticket(
        user_id=str(actor.id),
        token_version=actor.token_version,
        role="ANY",
        settings=settings,
    )

    async def operation() -> Mapping[str, Any]:
        result = await connection.execute(
            text(
                """
                SELECT quiz_id, status, total_marks
                FROM sp_publish_quiz(:quiz_id, :actor_id, :auth_signature)
                """
            ),
            {
                "quiz_id": quiz_id,
                "actor_id": actor.id,
                "auth_signature": signature,
            },
        )
        return result.mappings().one()

    return await _commit_mutation(connection, operation)


def _new_session_code() -> str:
    return "".join(secrets.choice(_SESSION_CODE_ALPHABET) for _ in range(8))


async def create_session(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    payload: QuizSessionCreate,
) -> Mapping[str, Any]:
    quiz = await authoring_service.get_quiz(connection, actor, payload.quiz_id)
    if quiz["status"] != "PUBLISHED":
        raise HTTPException(status_code=409, detail="Only published quizzes can be scheduled")
    await _require_faculty_subject_assignment(
        connection,
        actor,
        faculty_user_id=quiz["faculty_user_id"],
        subject_id=quiz["subject_id"],
        class_id=payload.class_id,
    )

    values = {
        "quiz_id": payload.quiz_id,
        "class_id": payload.class_id,
        "session_mode": payload.session_mode,
        "start_window_time": payload.start_window_time,
        "end_window_time": payload.end_window_time,
        "duration_minutes": (
            payload.duration_minutes
            if payload.duration_minutes is not None
            else quiz["default_duration_minutes"]
        ),
        "negative_marking_enabled": payload.negative_marking_enabled,
        "negative_penalty": payload.negative_penalty,
        "result_visibility": (
            payload.result_visibility
            if payload.result_visibility is not None
            else quiz["default_result_visibility"]
        ),
        "session_code": _new_session_code(),
    }

    async def operation() -> Mapping[str, Any]:
        result = await connection.execute(
            text(
                """
                INSERT INTO quiz_sessions (
                    college_id, quiz_id, faculty_user_id, class_id, session_code,
                    session_mode, start_window_time, end_window_time, duration_minutes,
                    negative_marking_enabled, negative_penalty, result_visibility
                ) VALUES (
                    :college_id, :quiz_id, :faculty_user_id, :class_id, :session_code,
                    :session_mode, :start_window_time, :end_window_time, :duration_minutes,
                    :negative_marking_enabled, :negative_penalty, :result_visibility
                )
                RETURNING id
                """
            ),
            {
                **values,
                "college_id": actor.college_id,
                "faculty_user_id": quiz["faculty_user_id"],
            },
        )
        session_id = result.scalar_one()
        return await _get_session(connection, actor, session_id)

    return await _commit_mutation(connection, operation)


async def _get_session(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    session_id: UUID,
) -> Mapping[str, Any]:
    owner_filter = "" if _is_admin(actor) else "AND faculty_user_id = :actor_id"
    parameters: dict[str, object] = {
        "college_id": actor.college_id,
        "session_id": session_id,
    }
    if not _is_admin(actor):
        parameters["actor_id"] = actor.id
    result = await connection.execute(
        text(
            _SESSION_SELECT
            + f"""
            WHERE college_id = :college_id
              AND id = :session_id
              {owner_filter}
            """
        ),
        parameters,
    )
    session = result.mappings().one_or_none()
    if session is None:
        raise _not_found()
    return session


async def get_session(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    session_id: UUID,
) -> Mapping[str, Any]:
    return await _get_session(connection, actor, session_id)


async def list_sessions(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    *,
    limit: int,
    offset: int,
) -> list[Mapping[str, Any]]:
    owner_filter = "" if _is_admin(actor) else "AND faculty_user_id = :actor_id"
    parameters: dict[str, object] = {
        "college_id": actor.college_id,
        "limit": limit,
        "offset": offset,
    }
    if not _is_admin(actor):
        parameters["actor_id"] = actor.id
    result = await connection.execute(
        text(
            _SESSION_SELECT
            + f"""
            WHERE college_id = :college_id
              {owner_filter}
            ORDER BY created_at DESC, id
            LIMIT :limit OFFSET :offset
            """
        ),
        parameters,
    )
    return list(result.mappings().all())


async def transition_session(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    session_id: UUID,
    action: str,
    settings: Settings,
) -> Mapping[str, Any]:
    procedure = _SESSION_PROCEDURES[action]
    await _get_session(connection, actor, session_id)
    signature = create_actor_ticket(
        user_id=str(actor.id),
        token_version=actor.token_version,
        role="ANY",
        settings=settings,
    )

    async def operation() -> Mapping[str, Any]:
        await connection.execute(
            text(f"SELECT {procedure}(:session_id, :actor_id, :auth_signature)"),
            {
                "session_id": session_id,
                "actor_id": actor.id,
                "auth_signature": signature,
            },
        )
        return await _get_session(connection, actor, session_id)

    return await _commit_mutation(connection, operation)


async def release_session_results(
    connection: AsyncConnection,
    actor: AuthenticatedUser,
    session_id: UUID,
    settings: Settings,
) -> Mapping[str, Any]:
    await _get_session(connection, actor, session_id)
    signature = create_actor_ticket(
        user_id=str(actor.id),
        token_version=actor.token_version,
        role="ANY",
        settings=settings,
    )

    async def operation() -> Mapping[str, Any]:
        await connection.execute(
            text(
                """
                SELECT sp_release_session_results(
                    :session_id, :actor_id, :auth_signature
                )
                """
            ),
            {
                "session_id": session_id,
                "actor_id": actor.id,
                "auth_signature": signature,
            },
        )
        return await _get_session(connection, actor, session_id)

    return await _commit_mutation(connection, operation)
