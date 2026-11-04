from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (
    get_current_actor,
    get_database_connection,
    get_settings,
    verify_csrf_request,
)
from app.core.auth_cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.core.config import Settings
from app.schemas.auth import (
    AuthenticatedUser,
    AuthSessionResponse,
    LoginRequest,
    RefreshRequest,
    UserProfile,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseConnection = Annotated[AsyncConnection, Depends(get_database_connection)]


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    request: LoginRequest,
    connection: DatabaseConnection,
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> AuthSessionResponse:
    tokens = await auth_service.login(connection, request, settings)
    return set_auth_cookies(response, tokens, settings)


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh(
    connection: DatabaseConnection,
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    http_request: Request,
    request: RefreshRequest | None = None,
) -> AuthSessionResponse:
    refresh_token = http_request.cookies.get(REFRESH_COOKIE)
    if refresh_token is not None:
        verify_csrf_request(http_request)
    else:
        refresh_token = (
            request.refresh_token.get_secret_value()
            if request is not None and request.refresh_token is not None
            else None
        )
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A refresh token is required",
        )
    token_response = await auth_service.refresh(
        connection,
        refresh_token,
        settings,
    )
    return set_auth_cookies(response, token_response, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    connection: DatabaseConnection,
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    http_request: Request,
    request: RefreshRequest | None = None,
) -> Response:
    refresh_token = http_request.cookies.get(REFRESH_COOKIE)
    if refresh_token is not None:
        verify_csrf_request(http_request)
    else:
        refresh_token = (
            request.refresh_token.get_secret_value()
            if request is not None and request.refresh_token is not None
            else None
        )
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A refresh token is required",
        )
    await auth_service.revoke_tokens(
        connection,
        refresh_token,
        settings,
    )
    clear_auth_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserProfile)
async def current_user(
    user: Annotated[AuthenticatedUser, Depends(get_current_actor)],
) -> UserProfile:
    return auth_service.public_user(user)
