"""
Mock analysis service for testing rate limiting
"""

import asyncio
import random
from app.models.analysis.request import InterviewAnalysisRequest
from app.models.analysis.response import AnalysisResult
from app.models.auth import UserContext


class AnalysisService:
    """
    Mock service that simulates interview analysis
    """

    async def analyze_interview(
        self, request: InterviewAnalysisRequest, user: UserContext
    ) -> AnalysisResult:
        """
        Simulate interview analysis processing
        """
        # Simulate processing time (1-5 seconds)
        processing_time = random.uniform(1.0, 5.0)
        await asyncio.sleep(processing_time)

        # Generate mock analysis results
        return AnalysisResult(
            transcript="This is a mock transcript of the interview...",
            technical_score=round(random.uniform(6.0, 9.5), 1),
            communication_score=round(random.uniform(6.0, 9.5), 1),
            confidence_indicators={
                "voice_clarity": round(random.uniform(0.7, 0.95), 2),
                "response_speed": round(random.uniform(0.6, 0.9), 2),
                "content_relevance": round(random.uniform(0.8, 0.98), 2),
            },
            key_insights=[
                "Candidate demonstrated strong technical knowledge",
                "Good communication skills but could improve clarity",
                "Shows confidence in problem-solving approaches",
            ],
            processing_time=processing_time,
        )

    async def queue_analysis_job(
        self, request: InterviewAnalysisRequest, user: UserContext
    ) -> str:
        """
        Simulate queuing an analysis job
        """
        # Generate a fake job ID
        import uuid

        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Simulate quick queueing
        await asyncio.sleep(0.1)

        return job_id


# Global service instance
analysis_service = AnalysisService()
