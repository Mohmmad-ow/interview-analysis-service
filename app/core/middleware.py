import time
import traceback
from fastapi import Request
from pydantic import InstanceOf
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import log


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all HTTP requests and responses
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log request
        log.info(
            "Request started",
            method=request.method,
            url=str(request.url),
            client_ip=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)

            # Log response
            process_time = time.time() - start_time
            log.info(
                "Request completed",
                method=request.method,
                url=str(request.url),
                status_code=response.status_code,
                process_time=process_time,
            )

            # Add process time to headers
            response.headers["X-Process-Time"] = str(process_time)
            return response

        except Exception as e:
            process_time = time.time() - start_time
            if log:
                log.error(
                    "Request failed",
                    method=request.method,
                    url=str(request.url),
                    process_time=process_time,
                    error=str(e),
                    stack_trace=traceback.format_exc(),
                )
            else:
                print(f"Request failed: {request.method} {request.url} {str(e)}")
            raise


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Add correlation IDs for request tracing
    """

    async def dispatch(self, request: Request, call_next):
        import uuid

        # Generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        # Add to request state for use in logs
        request.state.correlation_id = correlation_id

        # Bind correlation ID to all logs in this request
        if hasattr(log, "contextualize") and callable(getattr(log, "contextualize")):
            with log.contextualize(correlation_id=correlation_id):  # type: ignore
                response = await call_next(request)
                response.headers["X-Correlation-ID"] = correlation_id
                return response
        else:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
