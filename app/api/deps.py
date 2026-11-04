from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.config import Settings
from app.core.auth_cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE
from app.core.security import decode_token
from app.schemas.auth import AuthenticatedUser
from app.services import auth_service

bearer_scheme = HTTPBearer(auto_error=False)


def get_database_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_access_token_payload(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    else:
        token = request.cookies.get(ACCESS_COOKIE)
        if token is None:
            raise auth_service.authentication_error()
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            verify_csrf_request(request)
    try:
        return decode_token(
            token,
            expected_type="access",
            settings=settings,
        )
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise auth_service.authentication_error() from exc


def verify_csrf_request(request: Request) -> None:
    if ACCESS_COOKIE not in request.cookies and REFRESH_COOKIE not in request.cookies:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if (
        cookie_token is None
        or header_token is None
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token is missing or invalid",
        )


async def get_database_connection(request: Request) -> AsyncIterator[AsyncConnection]:
    engine = get_database_engine(request)
    async with engine.connect() as connection:
        yield connection


async def get_current_actor(
    payload: Annotated[dict[str, object], Depends(get_access_token_payload)],
    connection: Annotated[AsyncConnection, Depends(get_database_connection)],
) -> AuthenticatedUser:
    return await auth_service.authenticate_payload(connection, payload)


def require_roles(*allowed_roles: str) -> Callable[..., Awaitable[AuthenticatedUser]]:
    async def role_dependency(
        actor: Annotated[AuthenticatedUser, Depends(get_current_actor)],
    ) -> AuthenticatedUser:
        if not set(actor.roles).intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return actor

    return role_dependency
