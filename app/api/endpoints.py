import time
from fastapi import APIRouter, status, Depends, HTTPException


from app.models import InterviewAnalysisRequest, AnalysisResult, AsyncAnalysisResponse
from app.services.auth import auth_service
from app.services.rate_limiter import rate_limiter, RateLimitExceeded
from app.services.analysis_temp import analysis_service
from app.models.auth import UserContext, UserTier
from app.api.dependencies import get_current_user, require_premium, require_admin


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
):
    """
    Asynchronous interview analysis with rate limiting
    """
    try:
        # Check rate limit
        await rate_limiter.check_rate_limit(
            user_id=current_user.user_id,
            user_tier=current_user.tier,
            endpoint="analyze_async",
        )

        # Queue the job (you'll implement this later)
        job_id = await analysis_service.queue_analysis_job(request, current_user)

        return AsyncAnalysisResponse(
            job_id=job_id, status="queued", status_url=f"/v1/analysis/{job_id}/status"
        )

    except RateLimitExceeded as e:
        raise e
    except Exception as e:
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
    # Placeholder implementation
    return AnalysisResult(
        communication_score=9,
        technical_score=8,
        confidence_indicators={"filler_words": 5, "pauses": 3},
        key_insights=["Excellent problem-solving skills"],
        processing_time=2.5,
        transcript="Sample transcript of the interview.",
    )


@router.post("/process")
async def process_endpoint():
    """Endpoint for processing"""
    return {"message": "Process endpoint"}
