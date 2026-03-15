"""
Mock analysis service for testing rate limiting
"""

import asyncio
import random
from sys import audit
from typing import List, Optional

from numpy import number
from app.database.models import AnalysisResultDB, AuditLog
from app.models import analysis
from app.models.audit.request import AuditAction, AuditLog as AuditLogModel
from app.database.repository import (
    AnalysisRepository,
    AuditRepository,
    analysis_repository,
    audit_repository,
)
from fastapi import UploadFile
from app.models.analysis.request import (
    AsyncProcessQueuedJobs,
    InterviewAnalysisRequest,
    QueuedJobType,
)
from app.models.analysis.response import AnalysisResult
from app.models.auth import UserContext
from app.core.logging import log, log_error, log_info
from app.services.webhook_service import webhook_service
from app.services.whisper_service import whisper_service
from app.services.GeminiAnalysis import gemini_service
from app.services.process_queue import job_processor


class AnalysisService:
    """
    Mock service that simulates interview analysis
    """

    def __init__(self, analysis_repo: AnalysisRepository, audit_repo: AuditRepository):
        self.analysis_repo = analysis_repo
        self.audit_repo = audit_repo

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

        interview_id = request.interview_id

        start_time = asyncio.get_event_loop().time()

        try:

            # generate a unique job ID
            import uuid

            log_info(
                "Starting analysis", interview_id=interview_id, user_id=user.user_id
            )

            audit_log = AuditLogModel(
                user_id=user.user_id,
                action=AuditAction.ANALYSIS_STARTED,
                resource_pattern=request.audio_url,
                metadata={
                    "job_id": interview_id,
                    "job_description_length": len(request.job_description),
                    "has_questions": bool(request.questions),
                    "language": request.language,
                },
            )
            auditRes = await self.audit_repo.log_audit_event(audit_log)

            # 2. Create a minimal analysis result with queued status

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

            analysis_result = await gemini_service.analyze_interview(
                transcript, request.job_description, request.questions
            )
            # Store the original request data for later processing

            result = AnalysisResult(
                transcript=transcript,
                technical_score=analysis_result["technical_score"],
                communication_score=analysis_result["communication_score"],
                confidence_indicators=analysis_result["confidence_indicators"],
                key_insights=analysis_result["key_insights"],
                processing_time=processing_time,
            )

            # 3. Save to database with queued status
            await self.analysis_repo.save_analysis_result(
                job_id=interview_id,
                user_id=user.user_id,
                audio_url=request.audio_url,
                analysis_result=result,
                status="completed",  # ✅ Important: mark as Completed
                callback_url=request.callback_url,
                job_description=request.job_description,
                questions=request.questions,
            )
            audit_id = auditRes.id

            await self.audit_repo.update_job_status(
                int(audit_id), AuditAction.ANALYSIS_COMPLETED  # type: ignore
            )

            if request.callback_url:
                await webhook_service.send_webhook(
                    callback_url=request.callback_url,
                    job_id=interview_id,
                    status="completed",
                    result=result,
                    user_id=user.user_id,
                )

            log.info(
                f"Successfully processed job {interview_id} for user {user.user_id}"
            )
            return result

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Analysis failed",
                user_id=user.user_id,
                error=str(e),
                processing_time=processing_time,
            )
            log_error("Analysis failed", interview_id=interview_id, error=str(e))
            if request.callback_url:
                await webhook_service.send_webhook(
                    callback_url=request.callback_url,
                    job_id=interview_id,
                    result={},
                    status="failed",
                    error=str(e),
                    user_id=user.user_id,
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
        Queue an analysis job with proper data storage
        """
        import uuid

        interview_id = request.interview_id

        try:
            # 1. Create audit log
            audit_log = AuditLogModel(
                user_id=user.user_id,
                action=AuditAction.JOB_CREATED,
                resource_pattern=request.audio_url,
                metadata={
                    "job_id": interview_id,
                    "job_description_length": len(request.job_description),
                    "has_questions": bool(request.questions),
                    "language": request.language,
                },
            )
            await self.audit_repo.log_audit_event(audit_log)

            # 2. Create a minimal analysis result with queued status
            # Store the original request data for later processing
            queued_result = AnalysisResult(
                transcript="",  # Will be filled during processing
                technical_score=0.0,
                communication_score=0.0,
                confidence_indicators={},
                key_insights=[],
                processing_time=0.0,
            )

            # 3. Save to database with queued status
            await self.analysis_repo.save_analysis_result(
                job_id=interview_id,
                user_id=user.user_id,
                audio_url=request.audio_url,
                analysis_result=queued_result,
                status="queued",  # ✅ Important: mark as queued
                callback_url=request.callback_url,
                job_description=request.job_description,
                questions=request.questions,
            )

            log.info(f"Successfully queued job {interview_id} for user {user.user_id}")
            return interview_id

        except Exception as e:
            log.error(f"Failed to queue job {interview_id}: {e}")
            raise

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
            transcript = transcription_result["text"]  # type: ignore

            processing_time = asyncio.get_event_loop().time() - start_time
            analysis_result = await gemini_service.analyze_interview(
                transcript=transcript, job_description=job_description, questions=None
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
                "Local file analysis failed",
                error=str(e),
                processing_time=processing_time,
            )
            raise

    async def process_queued_jobs(self, queued_jobs_request: AsyncProcessQueuedJobs):
        """Process queued analysis jobs using the job processor"""
        result = await job_processor.process_queued_jobs(queued_jobs_request)
        return result


# Global service instance
analysis_service = AnalysisService(analysis_repository, audit_repository)
