from ast import ExceptHandler
from time import time
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.rate_limiter import RateLimitExceeded
from app.core.logging import log


class CORSLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        # Log all requests with Origin header
        if origin:
            log.info(f"CORS request from origin: {origin}")

        response = await call_next(request)

        # Log if origin was blocked
        if origin and not response.headers.get("access-control-allow-origin"):
            log.warning(f"CORS blocked origin: {origin}")

        return response


async def rate_limit_exception_handler(request: Request, exc: Exception):
    """
    Handle rate limit exceeded errors with proper HTTP response
    """

    if not isinstance(exc, RateLimitExceeded):
        # If it's some other exception, re-raise it
        raise exc
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": str(exc),
            "retry_after": exc.retry_after,
            "limits": f"{exc.limit} requests per {exc.window}",
            "documentation_url": "https://docs.example.com/rate-limiting",
        },
        headers={
            "Retry-After": str(exc.retry_after),
            "X-RateLimit-Limit": str(exc.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + exc.retry_after),
        },
    )
