import secrets

from fastapi import Response

from app.core.config import Settings
from app.schemas.auth import AuthSessionResponse, TokenResponse

ACCESS_COOKIE = "campusquiz_access"
REFRESH_COOKIE = "campusquiz_refresh"
CSRF_COOKIE = "campusquiz_csrf"
CSRF_HEADER = "X-CSRF-Token"
_API_COOKIE_PATH = "/api/v1"
_AUTH_COOKIE_PATH = "/api/v1/auth"


def set_auth_cookies(
    response: Response,
    token_response: TokenResponse,
    settings: Settings,
) -> AuthSessionResponse:
    csrf_token = secrets.token_urlsafe(32)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.set_cookie(
        ACCESS_COOKIE,
        token_response.access_token,
        max_age=token_response.expires_in,
        httponly=True,
        path=_API_COOKIE_PATH,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        token_response.refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        path=_AUTH_COOKIE_PATH,
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=False,
        path="/",
        **common,
    )
    return AuthSessionResponse(
        expires_in=token_response.expires_in,
        csrf_token=csrf_token,
        user=token_response.user,
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.delete_cookie(ACCESS_COOKIE, path=_API_COOKIE_PATH, **common)
    response.delete_cookie(REFRESH_COOKIE, path=_AUTH_COOKIE_PATH, **common)
    response.delete_cookie(CSRF_COOKIE, path="/", **common)
