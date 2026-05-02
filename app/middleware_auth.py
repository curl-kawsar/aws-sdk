"""Optional API key gate for production."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key (or Authorization: Bearer) when API_KEYS is configured."""

    async def dispatch(self, request: Request, call_next):
        if not settings.API_KEYS:
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path == "/health":
            return await call_next(request)

        key = request.headers.get("x-api-key")
        if not key:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                key = auth[7:].strip() or None

        if key and key in settings.API_KEYS:
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key. Send X-API-Key header."},
        )
