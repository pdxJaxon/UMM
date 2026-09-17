"""Main FastAPI application module."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.colleges import router as colleges_router
from app.api.drafts import router as drafts_router
from app.api.teams import router as teams_router

app = FastAPI(title="UMockMe API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(colleges_router)
app.include_router(drafts_router)
app.include_router(teams_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return the current health status of the API."""
    return {"status": "ok"}
