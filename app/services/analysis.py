"""
Document analysis service - adapted from interview analysis
"""

import asyncio
import re
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
from app.models.job.status import DocumentJobsResultRequest, DocumentJobsResultResponse
from app.services.document_parser import document_parser
from app.services.GeminiAnalysis import gemini_service
from app.services.webhook_service import document_webhook_service

class DocumentAnalysisService:
    """
    Service for document analysis - adapted from interview analysis
    """

    def __init__(self, analysis_repo: AnalysisRepository, audit_repo: AuditRepository):
        self.analysis_repo = analysis_repo
        self.audit_repo = audit_repo
        self.gemini_service = gemini_service
        self.document_parser = document_parser
    
    def strip_to_volume(self,path: str):
        """
        Removes all leading path components up to and including the volume marker.
        
        The volume marker is expected to be a folder name like 'v1', 'v2', ... 'v100'.
        
        Args:
            path (str): Original file path (e.g., r"C:\Games\Storage\v1\...\file.pdf")
        
        Returns:
            str: Path starting from the volume marker (e.g., "v1\...\file.pdf")
        """
        parts = path.split('\\')
        for i, part in enumerate(parts):
            if re.fullmatch(r'v\d+', part):          # matches exactly 'v' followed by digits
                return '\\'.join(parts[i:])
        return path   # fallback (or you could raise an exception)

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
                log.info("Starting to analyze local file.")
                extracted_text, processing_time = (
                    await self.document_parser.parse_local_file(
                        request.file_url, file_type=request.file_type.value
                    )
                )

            log.info("Starting to Analyze Extracted text via Gemini.")
            # Generate analysis results using Gemini
            analysis_result = await self.gemini_service.analyze_document(
                extracted_text=extracted_text,
                job_description=request.job_description,
                required_skills=request.required_skills,
                preferred_skills=request.preferred_skills,
            )
            # print the analysis results
            log_info("Analysis results: {analysis_result}", analysis_result=analysis_result)
            print(analysis_result["question_for_interview"])
            # Convert the analysis result to proper Pydantic models
            structured_data = StructuredResumeData(**analysis_result["structured_data"])
            score_breakdown = ScoreBreakdown(**analysis_result["score_breakdown"])
            skills_match = SkillsMatch(**analysis_result["skills_match"])
            questions_for_interview = analysis_result.get("question_for_interview", [])

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
                question_for_interview=questions_for_interview,
                resume_url=self.strip_to_volume(request.file_url)
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
                questions_for_interview=questions_for_interview,
                status="completed",
                go_job_posting_id=request.go_job_posting_id # type: ignore
            )
            
            if request.callback_url:
                log.info(f"Sending webhook for job {job_id} to {request.callback_url}")
                await document_webhook_service.send_webhook(
                    callback_url=request.callback_url,
                    job_id=job_id,
                    status="completed",
                    go_job_posting_id=request.go_job_posting_id, # type: ignore
                    result=result,
                )

            audit_id = auditRes.id
            await self.audit_repo.update_job_status(
                int(audit_id),  # type: ignore
                AuditAction.ANALYSIS_COMPLETED,  # type: ignore
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
                go_job_posting_id=request.go_job_posting_id, # type: ignore
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
                        str(job.job_id), "processing"
                    )

                    # Analyze the document
                    result = await self.analyze_document_file(
                        file_path=str(job.file_url),
                        job_description=job.job_description,
                        required_skills=job.required_skills or [],
                        preferred_skills=job.preferred_skills or [],
                        file_type=str(job.file_type),
                    )

                    # Save the result
                    await self.analysis_repo.update_document_analysis_status(
                        job_id=str(job.job_id),
                        status="completed",
                        analysis_result=result,
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
                        id=str(job.job_id), status="failed"
                    )
                    results.append(
                        {"job_id": str(job.job_id), "status": "failed", "error": str(e)}
                    )

            return {
                "processed_count": processed_count,
                "total_queued": len(queued_jobs),
                "results": results,
            }

        except Exception as e:
            log_error(f"Failed to process queued document jobs: {e}")
            raise

    # In app/services/document_analysis.py

    async def get_document_analysis_result(
        self, job_id: str
    ) -> Optional[DocumentAnalysisResult]:
        """Get document analysis result by job ID with all related data"""
        try:
            # This now returns a fully parsed DocumentAnalysisResult
            return await self.analysis_repo.get_document_job_result(job_id)
        except Exception as e:
            log_error(f"Failed to get document analysis result for {job_id}: {e}")
            return None

    async def get_document_jobs_result(
        self, request: DocumentJobsResultRequest, user: Optional[UserContext] = None
    ) -> DocumentJobsResultResponse:
        """Get multiple document analysis results with filtering"""
        try:
            # If user is provided, filter by user_id unless admin
            # if user and user.tier != "admin":
            #     request.user_id = user.user_id

            return await self.analysis_repo.get_document_jobs_result(request)

        except Exception as e:
            log_error(f"Failed to get document jobs result: {e}")
            raise


# Global service instance
document_analysis_service = DocumentAnalysisService(
    analysis_repository, audit_repository
)
