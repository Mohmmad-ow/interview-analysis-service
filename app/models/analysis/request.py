from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict


class InterviewAnalysisRequest(BaseModel):
    audio_url: str = Field(
        ..., description="URL for the job interview recording (audio file)"
    )
    job_description: str = Field(..., description="Job description for context")
    questions: Optional[List[str]] = Field(
        default=None, description="Specific questions asked in the interview"
    )
    language: str = Field(
        default="en",
        description="Language for the interview to transcript",
        pattern="^(en|ar)$",
    )
    callback_url: Optional[str] = Field(
        description="Webhook URL for async processing completion", default=None
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "audio_url": "https://example.com/interview.mp3",
                    "job_description": "Senior Python Developer with FastAPI experience...",
                    "questions": [
                        "What is your experience with microservices?",
                        "How do you handle errors?",
                    ],
                    "language": "en",
                    "callback_url": "https://api.myapp.com/webhooks/interview-complete",
                }
            ]
        }
    }
