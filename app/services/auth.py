import datetime
from fastapi import HTTPException, status
import jwt
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from app.models.auth.auth import UserContext, UserTier
from app.config import settings


class AuthService:
    """
    Authentication service for the microservice

    *we utilize a shared secret-key to encrypt and decrypt data
    """

    def __init__(self):
        self.algorithm = settings.ALGORITHM
        self.secret_key = settings.SECRET_KEY
        self.expire_date = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    def create_access_token(self, user_data: UserContext) -> str:
        """
        Create JWT access token from user context.


        Args:
            user_data (UserContext): The user context data to encode in the token.
        Returns:
            str: Encoded JWT token.

        Note:
            this will tokens will likely be generated from the main platform with the shared secrect-key
            but for testing reasons we expose an endpoint to create tokens here as well

        """
        # to_encode = user_data.copy()

        expire = datetime.now(timezone.utc) + timedelta(minutes=self.expire_date)
        to_encode = {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "iss": "main-platform",  # Who issued the token
            "aud": "interview-microservice",  # Who should accept it
            "type": "access_token",
            "user_id": user_data.user_id,
            "tier": user_data.tier.value,
            "email": user_data.email if user_data.email else None,
            "permissions": user_data.permissions if user_data.permissions else [],
        }
        # Remove any None values
        to_encode = {k: v for k, v in to_encode.items() if v is not None}

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        return encoded_jwt

    def verify_token(self, token: str) -> UserContext:
        """Verify JWT token and return user context"""
        
        print(f"DEBUG: Verifying with Secret: '{self.secret_key}' (Length: {len(self.secret_key)})")
        try:
            # Decode and verify all claims
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer="main-platform",
                audience="interview-microservice",
                options={"require": ["exp", "iat", "iss", "aud", "user_id", "tier"]},
            )

            # Validate required fields
            user_id = payload.get("user_id")
            tier = payload.get("tier")
            email = payload.get("email")

            if not user_id or not tier:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload",
                )

            # Validate tier enum value
            try:
                user_tier = UserTier(tier)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid user tier: {tier}",
                )

            return UserContext(
                user_id=user_id,
                tier=user_tier,
                email=email,
                permissions=payload.get("permissions", []),
            )

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
            )

    def validate_user_tier(self, user: UserContext, required_tier: UserTier) -> bool:
        """Check if user has required tier level"""
        tier_hierarchy = {UserTier.STANDARD: 1, UserTier.PREMIUM: 2, UserTier.ADMIN: 3}
        return tier_hierarchy[user.tier] >= tier_hierarchy[required_tier]


auth_service = AuthService()
