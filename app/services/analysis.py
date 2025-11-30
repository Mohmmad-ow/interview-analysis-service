"""
Document analysis service - adapted from interview analysis
"""

import asyncio
import uuid
from typing import Dict, List, Optional

from fastapi import UploadFile
from app.database.models import AuditLog
from app.models.audit.request import AuditAction, AuditLog as AuditLogModel
from app.database.repository import (
    AnalysisRepository,
    AuditRepository,
    analysis_repository,
    audit_repository,
)
from app.models.analysis.request import (
    AsyncProcessQueuedJobs,
    DocumentAnalysisRequest,
    QueuedJobType,
)
from app.models.analysis.response import (
    DocumentAnalysisResult,
    StructuredResumeData,
    ScoreBreakdown,
    SkillsMatch,
)
from app.models.auth import UserContext
from app.core.logging import log, log_error, log_info
from app.services.document_parser import document_parser
from app.services.GeminiAnalysis import gemini_service
from app.services.process_queue import job_processor


class DocumentAnalysisService:
    """
    Service for document analysis - adapted from interview analysis
    """

    def __init__(self, analysis_repo: AnalysisRepository, audit_repo: AuditRepository):
        self.analysis_repo = analysis_repo
        self.audit_repo = audit_repo
        self.gemini_service = gemini_service
        self.document_parser = document_parser

    async def analyze_document(
        self,
        request: DocumentAnalysisRequest,
        user: UserContext,
    ) -> DocumentAnalysisResult:
        """
        Analyze document - handles PDF, Word, and image files
        """
        log_info(
            "Starting document analysis",
            user_id=user.user_id,
            tier=user.tier,
            file_url=request.file_url,
            language=request.language,
        )

        start_time = asyncio.get_event_loop().time()

        try:
            # Generate a unique job ID
            job_id = f"doc_job_{uuid.uuid4().hex[:12]}"

            audit_log = AuditLogModel(
                user_id=user.user_id,
                action=AuditAction.ANALYSIS_STARTED,
                resource_pattern=request.file_url,
                metadata={
                    "job_id": job_id,
                    "job_description_length": len(request.job_description),
                    "file_type": request.file_type.value,  # Use .value for Enum
                    "language": request.language,
                },
            )
            auditRes = await self.audit_repo.log_audit_event(audit_log)

            # Check if it's a URL or local file
            if request.file_url.startswith(("http://", "https://")):
                # URL-based processing - download and parse
                extracted_text, processing_time = (
                    await self.document_parser.parse_from_url(
                        request.file_url,
                        file_type=request.file_type.value,
                        language=request.language,
                    )
                )
            else:
                # Local file processing
                extracted_text, processing_time = (
                    await self.document_parser.parse_local_file(
                        request.file_url, file_type=request.file_type.value
                    )
                )

            # Generate analysis results using Gemini
            analysis_result = await self.gemini_service.analyze_document(
                extracted_text=extracted_text,
                job_description=request.job_description,
                required_skills=request.required_skills,
                preferred_skills=request.preferred_skills,
            )

            # Convert the analysis result to proper Pydantic models
            structured_data = StructuredResumeData(**analysis_result["structured_data"])
            score_breakdown = ScoreBreakdown(**analysis_result["score_breakdown"])
            skills_match = SkillsMatch(**analysis_result["skills_match"])

            # Create result object
            result = DocumentAnalysisResult(
                extracted_text=extracted_text,
                structured_data=structured_data,
                overall_score=analysis_result["overall_score"],
                score_breakdown=score_breakdown,
                skills_match=skills_match,
                key_insights=analysis_result["key_insights"],
                processing_time=processing_time,
                confidence_scores=analysis_result.get("confidence_scores", {}),
            )

            # Save to database with completed status
            await self.analysis_repo.save_document_analysis_result(
                job_id=job_id,
                user_id=user.user_id,
                file_url=request.file_url,
                file_type=request.file_type.value,
                job_description=request.job_description,
                callback_url=request.callback_url,
                required_skills=request.required_skills,
                preferred_skills=request.preferred_skills,
                analysis_result=result,
                status="completed",
            )

            audit_id = auditRes.id
            await self.audit_repo.update_job_status(
                int(audit_id), AuditAction.ANALYSIS_COMPLETED  # type: ignore
            )

            log.info(
                f"Successfully processed document job {job_id} for user {user.user_id}"
            )
            return result

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Document analysis failed",
                user_id=user.user_id,
                error=str(e),
                processing_time=processing_time,
            )
            raise

    async def queue_analysis_job(
        self,
        request: DocumentAnalysisRequest,
        user: UserContext,
    ) -> str:
        """
        Queue a document analysis job
        """
        job_id = f"doc_job_{uuid.uuid4().hex[:12]}"

        try:
            # 1. Create audit log
            audit_log = AuditLogModel(
                user_id=user.user_id,
                action=AuditAction.JOB_CREATED,
                resource_pattern=request.file_url,
                metadata={
                    "job_id": job_id,
                    "job_description_length": len(request.job_description),
                    "file_type": request.file_type.value,
                    "language": request.language,
                },
            )
            await self.audit_repo.log_audit_event(audit_log)

            # 2. Create a minimal analysis result with queued status
            # We don't create a full DocumentAnalysisResult here since it will be populated during processing
            # Instead, we'll save minimal data and update later

            # 3. Save to database with queued status
            await self.analysis_repo.save_document_analysis_result(
                job_id=job_id,
                user_id=user.user_id,
                file_url=request.file_url,
                file_type=request.file_type.value,
                job_description=request.job_description,
                callback_url=request.callback_url,
                required_skills=request.required_skills,
                preferred_skills=request.preferred_skills,
                analysis_result=DocumentAnalysisResult(
                    confidence_scores={},
                    extracted_text="",
                    key_insights=[],
                    structured_data=StructuredResumeData(
                        email=None,
                        name=None,
                        phone=None,
                        education=[],
                        work_experience=[],
                        skills=[],
                        certifications=[],
                        languages=[],
                        summary=None,
                    ),
                    overall_score=0,
                    score_breakdown=ScoreBreakdown(
                        education_score=0,
                        experience_score=0,
                        overall_fit=0,
                        skills_score=0,
                    ),
                    skills_match=SkillsMatch(
                        missing_preferred_skills=[],
                        missing_required_skills=[],
                        preferred_skills_matched=[],
                        required_skills_matched=[],
                        skill_match_percentage=0,
                    ),
                    processing_time=0,
                ),  # Will be populated during processing
                status="queued",
            )

            log.info(
                f"Successfully queued document job {job_id} for user {user.user_id}"
            )
            return job_id

        except Exception as e:
            log.error(f"Failed to queue document job {job_id}: {e}")
            raise

    async def analyze_document_file(
        self,
        file_path: str,
        job_description: str,
        required_skills: List[str],
        preferred_skills: Optional[List[str]] = None,
        file_type: str = "pdf",
    ) -> DocumentAnalysisResult:
        """Analyze document from local file"""
        start_time = asyncio.get_event_loop().time()

        try:
            # Parse local file
            extracted_text, processing_time = (
                await self.document_parser.parse_local_file(file_path, file_type)
            )

            # Generate analysis using Gemini
            analysis_result = await self.gemini_service.analyze_document(
                extracted_text=extracted_text,
                job_description=job_description,
                required_skills=required_skills,
                preferred_skills=preferred_skills or [],
            )

            # Convert to proper Pydantic models
            structured_data = StructuredResumeData(**analysis_result["structured_data"])
            score_breakdown = ScoreBreakdown(**analysis_result["score_breakdown"])
            skills_match = SkillsMatch(**analysis_result["skills_match"])

            return DocumentAnalysisResult(
                extracted_text=extracted_text,
                structured_data=structured_data,
                overall_score=analysis_result["overall_score"],
                score_breakdown=score_breakdown,
                skills_match=skills_match,
                key_insights=analysis_result["key_insights"],
                processing_time=processing_time,
                confidence_scores=analysis_result.get("confidence_scores", {}),
            )

        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            log_error(
                "Local file document analysis failed",
                error=str(e),
                processing_time=processing_time,
            )
            raise

    async def process_queued_document_jobs(self, max_jobs: int = 10) -> Dict:
        """
        Process queued document analysis jobs
        """
        try:
            queued_jobs = await self.analysis_repo.get_all_queued_document_jobs()
            processed_count = 0
            results = []

            for job in queued_jobs[:max_jobs]:
                try:
                    # Update status to processing
                    await self.analysis_repo.update_document_job_status(
                        job.job_id, "processing"
                    )

                    # Analyze the document
                    result = await self.analyze_document_file(
                        file_path=job.file_url,
                        job_description=job.job_description,
                        required_skills=job.required_skills or [],
                        preferred_skills=job.preferred_skills or [],
                        file_type=job.file_type,
                    )

                    # Save the result
                    await self.analysis_repo.update_document_analysis_status(
                        job_id=job.job_id, status="completed", analysis_result=result
                    )

                    processed_count += 1
                    results.append(
                        {
                            "job_id": job.job_id,
                            "status": "completed",
                            "overall_score": result.overall_score,
                        }
                    )

                except Exception as e:
                    log_error(
                        f"Failed to process queued document job {job.job_id}: {e}"
                    )
                    await self.analysis_repo.update_document_job_status(
                        job_id=job.job_id, status="failed", error_message=str(e)
                    )
                    results.append(
                        {"job_id": job.job_id, "status": "failed", "error": str(e)}
                    )

            return {
                "processed_count": processed_count,
                "total_queued": len(queued_jobs),
                "results": results,
            }

        except Exception as e:
            log_error(f"Failed to process queued document jobs: {e}")
            raise

    async def get_document_analysis_result(
        self, job_id: str
    ) -> Optional[DocumentAnalysisResult]:
        """Get document analysis result by job ID"""
        try:
            return await self.analysis_repo.get_document_job_result(job_id)
        except Exception as e:
            log_error(f"Failed to get document analysis result for {job_id}: {e}")
            return None

    async def get_document_job_status(self, job_id: str) -> Optional[Dict]:
        raise NotImplementedError

        try:
            return await self.analysis_repo.get_document_job_status(job_id)
        except Exception as e:
            log_error(f"Failed to get document job status for {job_id}: {e}")
            return None


# Global service instance
document_analysis_service = DocumentAnalysisService(
    analysis_repository, audit_repository
)
