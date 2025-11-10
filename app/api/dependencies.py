from enum import auto
from sre_constants import ANY
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, HTTPBearer
from app.models.auth.auth import UserContext, UserTier
from app.services.analysis import AnalysisService
from app.services.auth import auth_service
from sqlalchemy.orm import Session
from app.database.connection import db_manager
from app.database.repository import AnalysisRepository, AuditRepository

from fastapi import Depends, Request, HTTPException
from app.database.audit_logger import audit_traffic
from typing import Generator


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserContext:
    """Dependency that validates JWT and returns user context"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return auth_service.verify_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserContext]:
    if not credentials:
        return None
    try:
        return auth_service.verify_token(credentials.credentials)
    except HTTPException:
        return None


def require_tier(required_tier: UserTier):
    """Factory function to create tier-based dependencies"""

    async def tier_dependency(current_user: UserContext = Depends(get_current_user)):
        if not auth_service.validate_user_tier(current_user, required_tier):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_tier.value} tier or higher",
            )
        return current_user

    return tier_dependency


# Specific tier dependencies
require_premium = require_tier(UserTier.PREMIUM)
require_admin = require_tier(UserTier.ADMIN)


async def get_audited_user(
    request: Request, currentUser: UserContext = Depends(get_current_user)
) -> str:
    """
    Dependency that extracts user_id and sets up audit context
    """
    user_id = currentUser.user_id

    # Log the API access
    with audit_traffic(
        user_id=user_id,
        action=f"{request.method} {request.url.path}",
        resource=request.url.path,
    ):
        return user_id


def audit_dependency(action: str):
    """
    Factory function for creating audit dependencies for specific actions
    """

    async def _audit_wrapper(
        request: Request, user_id: str = Depends(get_audited_user)
    ):
        with audit_traffic(user_id=user_id, action=action, resource=request.url.path):
            return user_id

    return _audit_wrapper


def get_db_session() -> Session:
    """Get database session per request"""
    return db_manager.SessionLocal()


def get_analysis_repository(
    db: Session = Depends(get_db_session),
) -> AnalysisRepository:
    return AnalysisRepository(db)


def get_audit_repository(db: Session = Depends(get_db_session)) -> AuditRepository:
    return AuditRepository(db)


def get_analysis_service(
    analysis_repo: AnalysisRepository = Depends(get_analysis_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AnalysisService:
    return AnalysisService(analysis_repo, audit_repo)
