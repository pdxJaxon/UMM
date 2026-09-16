"""Main FastAPI application module."""

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.drafts import router as drafts_router

app = FastAPI(title="UMockMe API")


app.include_router(auth_router)
app.include_router(drafts_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return the current health status of the API."""
    return {"status": "ok"}
