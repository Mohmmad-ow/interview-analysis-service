"""
Mock analysis service for testing rate limiting
"""

import asyncio
import random
from typing import Optional

from fastapi import UploadFile
from app.models.analysis.request import InterviewAnalysisRequest
from app.models.analysis.response import AnalysisResult
from app.models.auth import UserContext
from app.core.logging import log, log_error, log_info
from app.services.whisper_service import whisper_service


class AnalysisService:
    """
    Mock service that simulates interview analysis
    """

    async def analyze_interview(
        self,
        request: InterviewAnalysisRequest,
        user: UserContext,
    ) -> AnalysisResult:
        """
        Analyze interview - handles both URLs and local files
        """
        log_info(
            "Starting analysis",
            user_id=user.user_id,
            tier=user.tier,
            audio_url=request.audio_url,
            language=request.language,
        )

        start_time = asyncio.get_event_loop().time()

        try:
            # Check if it's a URL or local file
            if request.audio_url.startswith(("http://", "https://")):
                # URL-based processing
                transcript, processing_time = (
                    await whisper_service.transcribe_audio_url(
                        request.audio_url, language=request.language
                    )
                )
            else:
                # Local file processing - use the correct method
                transcript, processing_time = (
                    await whisper_service.transcribe_local_file(request.audio_url)
                )

            # Generate analysis results (you'll replace this with real Gemini analysis later)
            analysis_result = await self._generate_analysis(
                transcript, request.job_description
            )

            return AnalysisResult(
                transcript=transcript,
                technical_score=analysis_result["technical_score"],
                communication_score=analysis_result["communication_score"],
                confidence_indicators=analysis_result["confidence_indicators"],
                key_insights=analysis_result["key_insights"],
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Analysis failed",
                user_id=user.user_id,
                error=str(e),
                processing_time=processing_time,
            )
            raise

    async def _generate_analysis(self, transcript: str, job_description: str) -> dict:
        """Generate analysis results - placeholder for real Gemini integration"""
        # For now, return mock data
        return {
            "technical_score": round(random.uniform(6.0, 9.5), 1),
            "communication_score": round(random.uniform(6.0, 9.5), 1),
            "confidence_indicators": {
                "voice_clarity": round(random.uniform(0.7, 0.95), 2),
                "response_speed": round(random.uniform(0.6, 0.9), 2),
                "content_relevance": round(random.uniform(0.8, 0.98), 2),
            },
            "key_insights": [
                "Candidate demonstrated strong technical knowledge",
                "Good communication skills but could improve clarity",
                "Shows confidence in problem-solving approaches",
            ],
        }

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

    async def analyze_interview_file(
        self, audio_path: str, job_description: str, language: str = "en"
    ) -> AnalysisResult:
        """Analyze interview from local file"""
        start_time = asyncio.get_event_loop().time()

        try:
            # Transcribe local file
            transcription_result = await whisper_service.transcribe_local_file(
                audio_path, "en"
            )
            transcript = transcription_result["text"]

            # Analyze with Gemini
            # gemini_analysis = await gemini_analyzer.analyze_interview_content(
            #     transcript=transcript,
            #     job_description=job_description,
            #     language=language,
            # )

            processing_time = asyncio.get_event_loop().time() - start_time

            return AnalysisResult(
                transcript=transcript,
                technical_score=6.4,
                communication_score=7.8,
                confidence_indicators={
                    "content_relevance": 8.9,
                    "response_quality": 6.7 / 10,
                },
                key_insights=[
                    "too much talk, too little insight",
                    "stuff...stuff......stuff",
                ],
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Local file analysis failed",
                error=str(e),
                processing_time=processing_time,
            )
            raise


# Global service instance
analysis_service = AnalysisService()
