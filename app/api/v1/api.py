from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.endpoints.administration import router as administration_router
from app.api.v1.endpoints.authoring import router as authoring_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.lifecycle import router as lifecycle_router
from app.api.v1.endpoints.execution import (
    analytics_router as analytics_router,
    attempt_router as attempt_router,
    results_router as results_router,
    student_router as student_router,
)

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(administration_router)
api_router.include_router(authoring_router)
api_router.include_router(lifecycle_router)
api_router.include_router(student_router)
api_router.include_router(attempt_router)
api_router.include_router(results_router)
api_router.include_router(analytics_router)
