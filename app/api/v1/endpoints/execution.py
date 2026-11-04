from collections.abc import Mapping
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (
    get_current_actor,
    get_database_connection,
    get_settings,
    require_roles,
)
from app.core.config import Settings
from app.schemas.auth import AuthenticatedUser
from app.schemas.execution import (
    AttemptFinalizeRead,
    AttemptFinalizeRequest,
    AttemptResponseRead,
    AttemptResponseWrite,
    AttemptResultsRead,
    AttemptStartRead,
    AttemptStateRead,
    SessionAnalyticsRead,
    SessionCodeRequest,
    StudentSessionRead,
)
from app.services import execution_service

DatabaseConnection = Annotated[AsyncConnection, Depends(get_database_connection)]
Actor = Annotated[AuthenticatedUser, Depends(get_current_actor)]
ApplicationSettings = Annotated[Settings, Depends(get_settings)]

student_router = APIRouter(
    prefix="/student",
    tags=["student quiz discovery"],
    dependencies=[Depends(require_roles("STUDENT"))],
)
attempt_router = APIRouter(
    prefix="/attempts",
    tags=["quiz attempts"],
    dependencies=[Depends(require_roles("STUDENT"))],
)
results_router = APIRouter(tags=["quiz results"])
analytics_router = APIRouter(
    tags=["session analytics"],
    dependencies=[Depends(require_roles("FACULTY", "ADMIN"))],
)


@student_router.get("/sessions", response_model=list[StudentSessionRead])
async def list_available_sessions(
    connection: DatabaseConnection,
    actor: Actor,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Mapping[str, Any]]:
    return await execution_service.list_student_sessions(
        connection,
        actor,
        limit=limit,
        offset=offset,
    )


@student_router.post("/sessions/join", response_model=StudentSessionRead)
async def lookup_session_code(
    request: SessionCodeRequest,
    connection: DatabaseConnection,
    actor: Actor,
) -> Mapping[str, Any]:
    return await execution_service.lookup_session(connection, actor, request)


@attempt_router.post(
    "/sessions/{session_id}/start",
    response_model=AttemptStartRead,
    status_code=status.HTTP_201_CREATED,
)
async def start_attempt(
    session_id: UUID,
    connection: DatabaseConnection,
    actor: Actor,
    settings: ApplicationSettings,
) -> Mapping[str, Any]:
    return await execution_service.start_attempt(
        connection,
        actor,
        session_id,
        settings,
    )


@attempt_router.get("/{attempt_id}", response_model=AttemptStateRead)
async def read_attempt(
    attempt_id: UUID,
    connection: DatabaseConnection,
    actor: Actor,
) -> Mapping[str, Any]:
    return await execution_service.get_attempt_state(connection, actor, attempt_id)


@attempt_router.put(
    "/{attempt_id}/responses/{question_id}",
    response_model=AttemptResponseRead,
)
async def save_attempt_response(
    attempt_id: UUID,
    question_id: UUID,
    request: AttemptResponseWrite,
    connection: DatabaseConnection,
    actor: Actor,
    settings: ApplicationSettings,
) -> Mapping[str, Any]:
    return await execution_service.save_response(
        connection,
        actor,
        attempt_id,
        question_id,
        request,
        settings,
    )


@attempt_router.post("/{attempt_id}/submit", response_model=AttemptFinalizeRead)
async def finalize_attempt(
    attempt_id: UUID,
    request: AttemptFinalizeRequest,
    connection: DatabaseConnection,
    actor: Actor,
    settings: ApplicationSettings,
) -> Mapping[str, Any]:
    return await execution_service.finalize_attempt(
        connection,
        actor,
        attempt_id,
        request.submission_type,
        settings,
    )


@results_router.get(
    "/attempts/{attempt_id}/results",
    response_model=AttemptResultsRead,
)
async def read_attempt_results(
    attempt_id: UUID,
    connection: DatabaseConnection,
    actor: Actor,
    settings: ApplicationSettings,
) -> Mapping[str, Any]:
    return await execution_service.get_attempt_results(
        connection,
        actor,
        attempt_id,
        settings,
    )


@analytics_router.get(
    "/sessions/{session_id}/analytics",
    response_model=SessionAnalyticsRead,
)
async def read_session_analytics(
    session_id: UUID,
    connection: DatabaseConnection,
    actor: Actor,
    settings: ApplicationSettings,
) -> Mapping[str, Any]:
    return await execution_service.session_analytics(
        connection,
        actor,
        session_id,
        settings,
    )
