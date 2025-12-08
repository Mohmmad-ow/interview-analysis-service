import time
from fastapi import APIRouter, File, UploadFile, status, Depends, HTTPException, Form
from typing import Optional, List
import json

from fastapi.params import Query

from app.database.error_logger import error_logger
from app.database.audit_logger import audit_logger
from app.models.analysis.request import (
    AsyncProcessQueuedJobs,
    DocumentAnalysisRequest,
    DocumentBatchAnalysisRequest,
)
from app.models.job.status import (
    DocumentJobsResultRequest,
    DocumentJobsResultResponse,
    JobStatusResponse,
    JobsResultRequest,
    JobsStatusResponse,
    RequestJobsStatus,
)
from app.services.analysis import document_analysis_service
from app.models.analysis.response import (
    DocumentAnalysisResult,
    DocumentBatchAnalysisResult,
)
from app.services.auth import auth_service
from app.services.process_queue import JobProcessor
from app.services.rate_limiter import rate_limiter, RateLimitExceeded
from app.models.auth import UserContext, UserTier
from app.api.dependencies import (
    get_analysis_service,
    get_current_user,
    require_premium,
    require_admin,
)
from app.services.process_queue import job_processor
from app.database.repository import analysis_repository, audit_repository
from app.core.logging import log, log_error

# Create router instance
router = APIRouter(prefix="/documents", tags=["Document Analysis"])


@router.post("/create-token", summary="Create document analysis token")
def create_document_token(current_user: UserContext):
    """Create a token for document analysis"""
    try:
        token = auth_service.create_access_token(current_user)
        return {"token": token}
    except Exception as e:
        log.error(f"Failed to create document analysis token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document analysis token",
        )


@router.get("/check-token", summary="Check document analysis token validity")
async def check_document_token(
    current_user: UserContext = Depends(get_current_user),
):
    """Check if the document analysis token is valid"""
    return {"valid": True, "user_id": current_user.user_id, "tier": current_user.tier}


@router.post(
    "/analyze",
    response_model=DocumentAnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze document synchronously",
    description="""
    Process a resume/document and return analysis results immediately.
    
    **Supported Formats:**
    - PDF files (.pdf)
    - Word documents (.docx, .doc)
    - Images (.jpg, .jpeg, .png, .tiff)
    
    **Use Cases:**
    - Quick resume screening
    - Real-time candidate matching
    - When you need immediate results
    
    **Note:** For large files, consider using async endpoint
    """,
    response_description="Complete document analysis results including extracted data and scores",
)
async def analyze_document_sync(
    request: DocumentAnalysisRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Synchronous document analysis endpoint"""
    log.info(
        f"Received sync document analysis request for user: {current_user.user_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
    )
    try:
        # Check rate limit
        await rate_limiter.check_rate_limit(
            user_id=current_user.user_id,
            user_tier=current_user.tier,
            endpoint="analyze_document_sync",
        )

        result = await document_analysis_service.analyze_document(request, current_user)
        await audit_logger.log_action(
            user_id=current_user.user_id,
            action="document_analysis_completed",
            resource=request.file_url,
            metadata={
                "file_type": request.file_type.value,
                "job_description_length": len(request.job_description),
            },
        )

        return result

    except RateLimitExceeded as e:
        raise e
    except Exception as e:
        # Capture error with context
        await error_logger.capture_exception(
            user_id=current_user.user_id,
            request_data=request.model_dump(),
            custom_message="Document analysis failed",
        )
        raise HTTPException(
            status_code=500, detail=f"Document analysis failed: {str(e)}"
        )


@router.post(
    "/analyze/async",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Analyze document asynchronously",
    description="Queue document analysis for background processing.",
)
async def analyze_document_async(
    request: DocumentAnalysisRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """
    Asynchronous document analysis with rate limiting
    """
    log.info(
        f"Received async document analysis request for user: {current_user.user_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
    )
    try:
        # Check rate limit
        await rate_limiter.check_rate_limit(
            user_id=current_user.user_id,
            user_tier=current_user.tier,
            endpoint="analyze_document_async",
        )

        # Queue the job
        job_id = await document_analysis_service.queue_analysis_job(
            request, current_user
        )

        log.info(
            f"Queued async document analysis job for user: {current_user.user_id}",
            user_id=current_user.user_id,
            tier=current_user.tier,
            job_id=job_id,
        )

        return {
            "job_id": job_id,
            "status": "queued",
            "status_url": f"/v1/documents/job/status/{job_id}",
            "result_url": f"/v1/documents/jobs/result/{job_id}",
        }

    except RateLimitExceeded as e:
        raise e
    except Exception as e:
        log.error(f"Failed to queue document analysis job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue document analysis job",
        )


@router.post(
    "/analyze/batch",
    response_model=DocumentBatchAnalysisResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch analyze multiple documents",
    description="Analyze multiple documents/resumes in batch.",
)
async def analyze_documents_batch(
    request: DocumentBatchAnalysisRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """
    Batch document analysis endpoint
    """
    log.info(
        f"Received batch document analysis request for user: {current_user.user_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
        document_count=len(request.documents),
    )
    try:
        # Check rate limit (multiply by document count)
        for _ in range(len(request.documents)):
            await rate_limiter.check_rate_limit(
                user_id=current_user.user_id,
                user_tier=current_user.tier,
                endpoint="analyze_document_batch",
            )

        # Process documents sequentially (can be optimized later)
        analyses = []
        for doc_request in request.documents:
            result = await document_analysis_service.analyze_document(
                doc_request, current_user
            )
            analyses.append(result)

        # Calculate summary statistics
        avg_score = (
            sum(a.overall_score for a in analyses) / len(analyses) if analyses else 0
        )
        top_score = max(a.overall_score for a in analyses) if analyses else 0

        # Skills gap analysis
        all_skills_matched = []
        for analysis in analyses:
            if analysis.skills_match.required_skills_matched:
                all_skills_matched.extend(analysis.skills_match.required_skills_matched)

        from collections import Counter

        skill_frequency = Counter(all_skills_matched)

        batch_result = DocumentBatchAnalysisResult(
            job_posting_id=request.job_posting_id,
            analyses=analyses,
            total_processed=len(analyses),
            processing_summary={
                "average_score": round(avg_score, 2),
                "top_candidate_score": top_score,
                "skills_gap_analysis": dict(skill_frequency),
                "candidates_above_threshold": sum(
                    1 for a in analyses if a.overall_score >= 70
                ),
            },
        )

        await audit_logger.log_action(
            user_id=current_user.user_id,
            action="batch_document_analysis_completed",
            resource=f"batch_{len(analyses)}_documents",
            metadata={
                "document_count": len(analyses),
                "average_score": avg_score,
                "job_posting_id": request.job_posting_id,
            },
        )

        return batch_result

    except RateLimitExceeded as e:
        raise e
    except Exception as e:
        await error_logger.capture_exception(
            user_id=current_user.user_id,
            request_data=request.model_dump(),
            custom_message="Batch document analysis failed",
        )
        raise HTTPException(
            status_code=500, detail=f"Batch document analysis failed: {str(e)}"
        )


@router.post(
    "/upload",
    summary="Upload and analyze document",
    description="Upload a document file and analyze it immediately.",
)
async def upload_and_analyze_document(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    required_skills: str = Form(default="[]"),
    preferred_skills: str = Form(default="[]"),
    language: str = Form(default="en"),
    callback_url: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user),
):
    """
    Upload document file and analyze it
    """
    try:
        # Parse skills lists
        req_skills = json.loads(required_skills)
        pref_skills = json.loads(preferred_skills)

        # Determine file type from extension
        file_extension = (
            file.filename.split(".")[-1].lower() if "." in file.filename else ""  # type: ignore
        )
        from app.models.analysis.request import FileType

        if file_extension == "pdf":
            file_type = FileType.PDF
        elif file_extension in ["docx", "doc"]:
            file_type = FileType.DOCX
        elif file_extension in ["jpg", "jpeg", "png", "tiff"]:
            file_type = FileType.IMAGE
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}. Supported: pdf, docx, doc, jpg, jpeg, png, tiff",
            )

        # Save file temporarily
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{file_extension}"
        ) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        try:
            # Create request
            request = DocumentAnalysisRequest(
                file_url=temp_path,
                job_description=job_description,
                required_skills=req_skills,
                preferred_skills=pref_skills,
                file_type=file_type,
                language=language,
                callback_url=callback_url,
            )

            # Analyze the document
            result = await document_analysis_service.analyze_document(
                request, current_user
            )

            return result

        finally:
            # Clean up temp file
            os.unlink(temp_path)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400, detail="Invalid skills format. Use JSON array format."
        )
    except Exception as e:
        await error_logger.capture_exception(
            user_id=current_user.user_id,
            request_data={
                "filename": file.filename,
                "job_description_length": len(job_description),
            },
            custom_message="Document upload and analysis failed",
        )
        raise HTTPException(
            status_code=500, detail=f"Upload and analysis failed: {str(e)}"
        )


@router.get(
    "/job/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get document job status",
    description="Get status of a specific document analysis job.",
)
async def get_document_job_status(
    job_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get status of a specific document analysis job"""
    try:
        return await analysis_repository.get_document_job_status(job_id)
    except Exception as e:
        log.error(f"Failed to get document job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document job status",
        )


@router.get(
    "/jobs/result/{job_id}",
    response_model=DocumentAnalysisResult,
    summary="Get document analysis result",
    description="Get analysis result for a completed document analysis job.",
)
async def get_document_job_result(
    job_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get analysis result for a completed document analysis job"""
    log.info(
        f"Fetching document job result for job_id: {job_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
    )
    try:
        job_result = await document_analysis_service.get_document_analysis_result(
            job_id
        )
        if job_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document analysis result not found or not completed",
            )
        return job_result
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error when fetching document analysis result",
        )


# app/api/routers/documents.py


@router.post(
    "/jobs/result",
    response_model=DocumentJobsResultResponse,
    summary="Get document analysis results with filtering",
    description="Retrieve document analysis results with filtering, sorting, and pagination.",
)
async def get_document_jobs_result(
    request: DocumentJobsResultRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Get multiple document analysis results with filtering"""
    log.info(
        f"Fetching document jobs result with filters for user: {current_user.user_id}",
        user_id=current_user.user_id,
        filters=request.dict(exclude_none=True),
    )
    try:
        return await document_analysis_service.get_document_jobs_result(
            request, current_user
        )
    except Exception as e:
        log_error(f"Failed to get document jobs result: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document jobs result",
        )


@router.get(
    "/search",
    summary="Search document analyses",
    description="Search document analyses by candidate name, email, or content.",
)
async def search_document_analyses(
    search_term: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserContext = Depends(get_current_user),
):
    """Search document analyses with various filters"""
    try:
        results, total_count = await analysis_repository.search_document_analyses(
            search_term=search_term,
            min_score=min_score,
            max_score=max_score,
            file_type=file_type,
            user_id=current_user.user_id if current_user.tier != "admin" else None,
            limit=limit,
            offset=offset,
        )

        return {
            "results": results,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count,
        }

    except Exception as e:
        log_error(f"Failed to search document analyses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search document analyses",
        )


@router.post(
    "/process/queued-jobs",
    summary="Process queued document analysis jobs",
    description="Start background processing of queued document analysis jobs",
)
async def process_queued_document_jobs(
    request: AsyncProcessQueuedJobs,
    current_user: UserContext = Depends(require_admin),  # Admin only
):
    """Trigger processing of queued document analysis jobs"""
    try:
        # Start job processing
        result = await job_processor.process_queued_jobs(request)

        return {
            "message": "Document job processing started",
            "batch_id": result["batch_id"],
            "jobs_processed": result["processed_jobs"],
            "total_queued": result["total_queued"],
            "results": result["results"],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start document job processing: {str(e)}"
        )


@router.get(
    "/user/analyses",
    summary="Get user's document analyses",
    description="Retrieve document analysis history for the authenticated user.",
)
async def get_user_document_analyses(
    limit: int = 50,
    offset: int = 0,
    current_user: UserContext = Depends(get_current_user),
):
    """Get user's document analysis history"""
    try:
        analyses = await analysis_repository.get_user_document_analyses(
            user_id=current_user.user_id
        )

        return {
            "analyses": [analysis.to_dict() for analysis in analyses],
            "total": len(analyses),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        log.error(f"Failed to get user document analyses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user document analyses",
        )


@router.get(
    "/stats",
    summary="Get document analysis statistics",
    description="Get statistics about document analyses (admin only).",
)
async def get_document_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserContext = Depends(require_admin),
):
    """Get document analysis statistics (admin only)"""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func

        # Parse dates
        start = (
            datetime.fromisoformat(start_date)
            if start_date
            else datetime.utcnow() - timedelta(days=30)
        )
        end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()

        from app.database.models import DocumentAnalysisDB

        # Get stats from database
        session = analysis_repository.session

        total_analyses = session.query(func.count(DocumentAnalysisDB.id)).scalar() or 0
        completed_analyses = (
            session.query(func.count(DocumentAnalysisDB.id))
            .filter(DocumentAnalysisDB.status == "completed")
            .scalar()
            or 0
        )

        avg_score = (
            session.query(func.avg(DocumentAnalysisDB.overall_score))
            .filter(
                DocumentAnalysisDB.status == "completed",
                DocumentAnalysisDB.overall_score.isnot(None),
            )
            .scalar()
            or 0
        )

        file_type_dist = (
            session.query(
                DocumentAnalysisDB.file_type, func.count(DocumentAnalysisDB.id)
            )
            .group_by(DocumentAnalysisDB.file_type)
            .all()
        )

        recent_analyses = (
            session.query(DocumentAnalysisDB)
            .filter(
                DocumentAnalysisDB.created_at >= start,
                DocumentAnalysisDB.created_at <= end,
            )
            .order_by(DocumentAnalysisDB.created_at.desc())
            .limit(100)
            .all()
        )

        return {
            "total_analyses": total_analyses,
            "completed_analyses": completed_analyses,
            "success_rate": round(
                (
                    (completed_analyses / total_analyses * 100)
                    if total_analyses > 0
                    else 0
                ),
                2,
            ),
            "average_score": round(float(avg_score), 2),
            "file_type_distribution": dict(file_type_dist),  # type: ignore
            "recent_analyses_count": len(recent_analyses),
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        }

    except Exception as e:
        log.error(f"Failed to get document stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document statistics",
        )
