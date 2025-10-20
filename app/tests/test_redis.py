import pytest
import asyncio
from app.services.rate_limiter import rate_limiter, RateLimitExceeded
from app.models.auth import UserTier


@pytest.mark.asyncio
async def test_basic_rate_limiting():
    """Test basic rate limiting functionality"""
    print("🧪 Testing basic rate limiting...")

    user_id = "test_user_basic"
    user_tier = UserTier.STANDARD

    # First 5 requests should work
    for i in range(5):
        result = await rate_limiter.check_rate_limit(
            user_id, user_tier, "test_endpoint"
        )
        assert result == True, f"Request {i+1} should be allowed"
        print(f"  ✅ Request {i+1}: Allowed")

    # 6th request should be blocked
    try:
        await rate_limiter.check_rate_limit(user_id, user_tier, "test_endpoint")
        assert False, "6th request should have been rate limited"
    except RateLimitExceeded as e:
        print(f"  ✅ Request 6: Correctly blocked - {e}")
        assert True


@pytest.mark.asyncio
async def test_different_users_dont_interfere():
    """Test that different users have separate limits"""
    print("🧪 Testing user separation...")

    user1 = "test_user_1"
    user2 = "test_user_2"
    user_tier = UserTier.STANDARD

    # Use up user1's limit
    for i in range(5):
        await rate_limiter.check_rate_limit(user1, user_tier, "test_endpoint")

    # User1 should be blocked
    try:
        await rate_limiter.check_rate_limit(user1, user_tier, "test_endpoint")
        assert False, "User1 should be rate limited"
    except RateLimitExceeded:
        print("  ✅ User1 correctly blocked")

    # User2 should still be allowed
    result = await rate_limiter.check_rate_limit(user2, user_tier, "test_endpoint")
    assert result == True, "User2 should be allowed (separate counter)"
    print("  ✅ User2 allowed (separate counter)")


@pytest.mark.asyncio
async def test_premium_higher_limits():
    """Test that premium users have higher limits"""
    print("🧪 Testing premium tier limits...")

    premium_user = "test_premium_user"
    user_tier = UserTier.PREMIUM

    # Premium users should get more requests
    for i in range(20):
        result = await rate_limiter.check_rate_limit(
            premium_user, user_tier, "test_endpoint"
        )
        assert result == True, f"Premium request {i+1} should be allowed"

    print("  ✅ Premium user allowed 20 requests")

    # 21st request should be blocked
    try:
        await rate_limiter.check_rate_limit(premium_user, user_tier, "test_endpoint")
        assert False, "Premium user should be blocked after 20 requests"
    except RateLimitExceeded:
        print("  ✅ Premium user correctly blocked after 20 requests")
