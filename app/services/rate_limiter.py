from typing import Dict

import redis
from app.core.redis import redis_manager
from app.models.auth import UserTier
from app.config import settings


class RateLimitExceeded(Exception):
    """Custom exception for rate limit violations"""

    def __init__(self, retry_after: int, limit: int, window: str):
        self.retry_after = retry_after
        self.limit = limit
        self.window = window
        super().__init__(f"Rate limit exceeded. {limit} requests per {window}")


class RateLimitService:
    """
    Business logic for rate limiting - this is a SERVICE
    It uses the Redis infrastructure to implement business rules
    """

    # Tier limits defined in business logic
    TIER_LIMITS: Dict[UserTier, Dict[str, int]] = {
        UserTier.STANDARD: {
            "minute": settings.STANDARD_RATE_LIMIT_MINUTE,
            "hour": settings.STANDARD_RATE_LIMIT_HOUR,
        },
        UserTier.PREMIUM: {
            "minute": settings.PREMIUM_RATE_LIMIT_MINUTE,
            "hour": settings.PREMIUM_RATE_LIMIT_HOUR,
        },
        UserTier.ADMIN: {
            "minute": settings.ADMIN_RATE_LIMIT_MINUTE,
            "hour": settings.ADMIN_RATE_LIMIT_HOUR,
        },
    }

    async def check_rate_limit(
        self, user_id: str, user_tier: UserTier, endpoint: str = "default"
    ) -> bool:
        """
        Check if user is within their rate limits

        Args:
            user_id: The user's unique identifier
            user_tier: User's subscription tier
            endpoint: Which API endpoint they're accessing

        Returns:
            bool: True if request is allowed, False if rate limited
        """

        # If Redis is down, allow all requests (fail open)
        if not redis_manager.is_connected():
            return False

        redis_client = redis_manager.client
        limits = self.TIER_LIMITS[user_tier]

        # Check minute limit
        minute_key = f"rate_limit:{user_id}:{endpoint}:minute"
        if not await self._check_window(redis_client, minute_key, limits["minute"], 60):
            return False

        # Check hour limit
        hour_key = f"rate_limit:{user_id}:{endpoint}:hour"
        if not await self._check_window(redis_client, hour_key, limits["hour"], 3600):
            return False

        return True

    async def _check_window(
        self, redis_client, key: str, limit: int, window_seconds: int
    ) -> bool:
        """
        Check a specific time window limit
        """
        try:
            # Get current count
            current_count = redis_client.get(key)

            if current_count is None:
                # First request in this window - set count to 1 with expiration
                redis_client.setex(key, window_seconds, "1")
                return True

            current_count = int(current_count)

            if current_count >= limit:
                # Over limit - check how long until window resets
                ttl = redis_client.ttl(key)
                raise RateLimitExceeded(
                    retry_after=ttl if ttl > 0 else window_seconds,
                    limit=limit,
                    window=f"{window_seconds} seconds",
                )

            # Increment counter (maintains existing TTL)
            redis_client.incr(key)
            return True

        except redis.RedisError as e:
            # If Redis has issues, allow the request (fail open)
            print(f"Redis error in rate limiting: {e}")
            return True

    async def get_user_limits_info(
        self, user_tier: UserTier, user_id: str, endpoint: str = "default"
    ) -> Dict:
        """
        Get current rate limit information
        """
        if not redis_manager.is_connected():
            return {"error": "redis unavailable", "rate_limiting": "disabled"}

        redis_client = redis_manager.client
        if not redis_client:
            return {"error": "redis unavailable", "rate_limiting": "disabled"}
        limits = self.TIER_LIMITS[user_tier]

        def _to_int(raw):
            if raw is None:
                return 0
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0

        minute_key = f"rate_limit:{user_id}:{endpoint}:minute"
        hour_key = f"rate_limit:{user_id}:{endpoint}:hour"
        minute_count = _to_int(redis_client.get(minute_key))
        hour_count = _to_int(redis_client.get(hour_key))

        minute_ttl = _to_int(redis_client.ttl(minute_key))
        hour_ttl = _to_int(redis_client.ttl(hour_key))

        return {
            "user_id": user_id,
            "tier": user_tier.value,
            "endpoint": endpoint,
            "limits": limits,
            "usage": {"minute": minute_count, "hour": hour_count},
            "remaining": {
                "minute": max(0, limits["minute"] - minute_count),
                "hour": max(0, limits["hour"] - hour_count),
            },
            "reset_in": {
                "minute": minute_ttl if minute_ttl > 0 else 60,
                "hour": hour_ttl if hour_ttl > 0 else 3600,
            },
        }


# Global service instance
rate_limiter = RateLimitService()
