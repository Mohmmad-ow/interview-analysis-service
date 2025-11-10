import time
from fastapi import APIRouter, File, UploadFile, status, Depends, HTTPException
from app.database.error_logger import error_logger
from app.database.audit_logger import audit_logger
from app.models.analysis.request import AsyncProcessQueuedJobs
from app.services.GeminiAnalysis import gemini_service
from app.models import InterviewAnalysisRequest, AnalysisResult, AsyncAnalysisResponse
from app.services import whisper_service
from app.services.auth import auth_service
from app.services.rate_limiter import rate_limiter, RateLimitExceeded
from app.services.analysis import AnalysisService, analysis_service
from app.models.auth import UserContext, UserTier
from app.api.dependencies import (
    get_analysis_service,
    get_current_user,
    require_premium,
    require_admin,
)
from app.core.logging import log

# Create router instance
router = APIRouter()


@router.post("/create-token")
async def create_token_endpoint(user_data: UserContext):
    """Endpoint for creating token"""

    token = auth_service.create_access_token(user_data)
    return {"token": token}


@router.get("/validate-token")
async def validate_token_endpoint(token: str):
    """Endpoint for validating token"""

    user_context = auth_service.verify_token(token)
    return {"user": user_context}


@router.post(
    "/analyze/async",
    response_model=AsyncAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Analyze interview asynchronously",
    description="Queue interview analysis for background processing.",
)
async def analyze_interview_async(
    request: InterviewAnalysisRequest,
    current_user: UserContext = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),  # ✅ Add this
):
    """
    Asynchronous interview analysis with rate limiting
    """
    log.info(
        f"Received async analysis request for user: {current_user.user_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
    )
    try:
        # Check rate limit
        await rate_limiter.check_rate_limit(
            user_id=current_user.user_id,
            user_tier=current_user.tier,
            endpoint="analyze_async",
        )

        # Queue the job
        job_id = await analysis_service.queue_analysis_job(request, current_user)

        log.info(
            f"Queued async analysis job for user: {current_user.user_id}",
            user_id=current_user.user_id,
            tier=current_user.tier,
            job_id=job_id,
        )

        return AsyncAnalysisResponse(
            job_id=job_id, status="queued", status_url=f"/v1/analysis/{job_id}/status"
        )

    except RateLimitExceeded as e:
        raise e
    except Exception as e:
        log.error(f"Failed to queue analysis job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue analysis job",
        )


@router.get(
    "/rate-limit",
    summary="Get current rate limit usage",
    description="Check your current rate limit usage and remaining requests.",
)
async def get_rate_limit_info(
    current_user: UserContext = Depends(get_current_user),
    endpoint: str = "analyze",  # Optional query parameter
):
    """
    Get current rate limit information for the authenticated user
    """

    log.info(
        f"Fetching rate limit info for user: {current_user.user_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
    )
    info = await rate_limiter.get_user_limits_info(
        user_id=current_user.user_id, user_tier=current_user.tier, endpoint=endpoint
    )

    return info


@router.get(
    "/admin/rate-limit/{user_id}",
    summary="Admin: Get user rate limit info",
    description="Admin endpoint to check any user's rate limit usage.",
)
async def admin_get_rate_limit_info(
    user_id: str,
    endpoint: str = "analyze",
    current_user: UserContext = Depends(require_admin),  # Admin only
):
    """
    Admin endpoint to check rate limits for any user
    """
    # For admin view, you might want to use a standard tier
    # or look up the user's actual tier from your main platform
    info = await rate_limiter.get_user_limits_info(
        user_id=user_id,
        user_tier=UserTier.STANDARD,  # Or look up real tier
        endpoint=endpoint,
    )

    return info


@router.get("/analyze")
async def analyze_endpoint(
    request: InterviewAnalysisRequest,
    current_user: UserContext = Depends(get_current_user),  # ← INJECTED HERE
    analysis_service: AnalysisService = Depends(
        get_analysis_service
    ),  # ← INJECTED HERE
):
    """Endpoint for analysis"""
    return {"message": "Analysis endpoint"}


@router.post(
    "/analyze",
    response_model=AnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Analyze interview synchronously",
    description="""
    Process interview audio and return analysis results immediately.
    
    **Use Cases:**
    - Short interviews (under 2 minutes)
    - Real-time analysis needs
    - When you need immediate results
    
    **Limitations:**
    - Longer audio may timeout
    - No webhook support
    """,
    response_description="Complete analysis results including scores and insights",
)
async def analyze_interview(
    request: InterviewAnalysisRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Synchronous interview analysis endpoint"""
    request.audio_url = request.audio_url.replace("\\\\", "\\")
    log.info(
        f"Received async analysis request for user: {current_user.user_id}",
        user_id=current_user.user_id,
        tier=current_user.tier,
    )
    try:
        # Check rate limit
        await rate_limiter.check_rate_limit(
            user_id=current_user.user_id,
            user_tier=current_user.tier,
            endpoint="analyze_async",
        )

        result = await analysis_service.analyze_interview(request, current_user)
        await audit_logger.log_action(
            user_id=current_user.user_id,
            action="analysis_completed",
            resource=request.audio_url,
            metadata={"job_description_length": str(len(request.job_description))},
        )

        return result

    except Exception as e:
        # Capture error with context
        await error_logger.capture_exception(
            user_id=current_user.user_id,
            request_data=request.model_dump(),
            custom_message="Interview analysis failed",
        )
        raise HTTPException(status_code=500, detail="Analysis failed")


@router.post(
    "/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process endpoint",
    description="Endpoint for processing",
)
async def process_endpoint(
    queued_jobs_request: AsyncProcessQueuedJobs,
    current_user: UserContext = Depends(get_current_user),
):
    """Endpoint for processing"""
    try:
        result = await analysis_service.process_queued_jobs(queued_jobs_request)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process queued jobs",
        )
