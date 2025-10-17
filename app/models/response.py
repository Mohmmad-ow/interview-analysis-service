from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime


class AsyncAnalysisResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the analysis job")
    status: str = Field(
        ...,
        pattern="^(queued|processing|completed|failed)$",
        description="Current status of the analysis job",
    )
    estimated_wait: Optional[int] = Field(
        default=None, description="Estimated wait time in seconds"
    )
    status_url: str = Field(..., description="URL to check job status")

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job_123456",
                "status": "queued",
                "estimated_wait": 45,
                "status_url": "/v1/analysis/job_123456/status",
            }
        }


class AnalysisResult(BaseModel):
    transcript: str = Field(..., description="Full interview transcription")
    technical_score: float = Field(
        ..., ge=0, le=10, description="Technical skills score (0-10)"
    )
    communication_score: float = Field(
        ..., ge=0, le=10, description="Communication skills score (0-10)"
    )
    confidence_indicators: Dict[str, float] = Field(
        ..., description="Confidence metrics for different aspects"
    )
    key_insights: List[str] = Field(
        ..., description="Key observations and recommendations"
    )
    processing_time: float = Field(..., description="Total processing time in seconds")


class QuestionAnalysis(BaseModel):
    question_text: str = Field(..., description="The question that was asked")
    answer_transcript: str = Field(..., description="Transcription of the answer")
    technical_score: float = Field(..., ge=0, le=10)
    communication_score: float = Field(..., ge=0, le=10)
    confidence_level: str = Field(
        ..., pattern="^(high|medium|low)$", description="Overall confidence assessment"
    )


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Detailed error message")
    timestamp: datetime = Field(default_factory=datetime.now)


class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: datetime
    dependencies: Dict[str, bool]
