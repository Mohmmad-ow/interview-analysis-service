from sqlite3.dbapi2 import Timestamp
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging import log_error, log_info
from app.core.middleware import LoggingMiddleware, CorrelationMiddleware


from app.core.exceptions import CORSLoggingMiddleware, rate_limit_exception_handler
from app.models import InterviewAnalysisRequest
from app.api import router as api_router
from app.services.rate_limiter import RateLimitExceeded
from .config import settings


app = FastAPI(
    description="Document Analysis Service API",
    version="1.0.0",
    title=settings.PROJECT_NAME,
    docs_url="/docs" if settings.DEBUG else None,  # Hide docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
)


app.add_middleware(CorrelationMiddleware)
app.add_middleware(LoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)


app.add_middleware(CORSLoggingMiddleware)
app.include_router(prefix=settings.API_V1_STR, router=api_router)


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint"""
    return {"message": "Welcome to the Document Analysis Service API"}


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": str(Timestamp.now())}
