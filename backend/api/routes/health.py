"""Health-check route: lets anyone confirm the backend is running."""

from fastapi import APIRouter

from backend.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict:
    """Return a simple status message."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }
