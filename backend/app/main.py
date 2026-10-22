"""Main FastAPI application module."""

import truststore

# Trust the OS certificate store so outbound HTTPS (e.g. the LLM provider) works behind
# TLS-inspecting corporate proxies whose root CA is not in certifi's bundle.
truststore.inject_into_ssl()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.auth import router as auth_router
from app.api.colleges import router as colleges_router
from app.api.drafts import router as drafts_router
from app.api.data import router as data_router
from app.api.teams import router as teams_router
from app.core.config import settings

app = FastAPI(title="UMockMe API")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply browser security headers to every API response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.environment in {"production", "prod"}:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(colleges_router)
app.include_router(drafts_router)
app.include_router(data_router)
app.include_router(teams_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Return the current health status of the API."""
    return {"status": "ok"}
