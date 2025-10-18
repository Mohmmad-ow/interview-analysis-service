from enum import auto
from sre_constants import ANY
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, HTTPBearer
from app.models.auth.auth import UserContext, UserTier
from app.services.auth import auth_service


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
