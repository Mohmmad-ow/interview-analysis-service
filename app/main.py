from os import times
from sqlite3.dbapi2 import Timestamp
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


from app.models import InterviewAnalysisRequest, AsyncAnalysisResponse, AnalysisResult
from app.api import router as api_router
from .config import settings


app = FastAPI(
    description="Interview Analysis Service API",
    version="1.0.0",
    title=settings.PROJECT_NAME,
    docs_url="/docs" if settings.DEBUG else None,  # Hide docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prefix=settings.API_V1_STR, router=api_router)


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint"""
    return {"message": "Welcome to the Interview Analysis Service API"}


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2023-10-01T12:00:00Z"}
