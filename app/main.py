from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.api import api_router
from app.core.config import Settings
from app.db.session import create_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configured_settings = settings or Settings()
        engine = create_database_engine(configured_settings)
        application.state.engine = engine
        application.state.settings = configured_settings
        try:
            yield
        finally:
            await engine.dispose()

    application = FastAPI(
        title="CampusQuiz API",
        version="1.0.0",
        lifespan=lifespan,
    )
    cors_origins = (
        settings.cors_origins
        if settings is not None
        else [
            origin.strip()
            for origin in os.environ.get(
                "CORS_ALLOWED_ORIGINS",
                "http://localhost:5173",
            ).split(",")
        ]
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
