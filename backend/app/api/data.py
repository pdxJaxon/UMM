"""Public metadata for the last completed full data refresh."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/status")
def data_status() -> dict[str, str | None]:
    """Report only an explicitly recorded full-refresh date."""
    return {
        "updated_on": settings.data_updated_on.isoformat() if settings.data_updated_on else None,
    }
