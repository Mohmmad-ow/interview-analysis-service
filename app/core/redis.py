from app.config import settings
import redis
import logging


logger = logging.getLogger(__name__)


class RedisManager:
    """
    Manages Redis connections for rate limiting and caching.

    Attributes:

    """

    def __init__(self):
        self.client = None
        self._connect()

    def _connect(self):
        """Establishes a connection to the Redis server."""

        try:
            self.client = redis.Redis(
                host=settings.REDIS_URL,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,  # Get strings instead of bytes
                socket_connect_timeout=5,  # Timeout for connection
                socket_timeout=5,  # Timeout for operations
            )

            self.client.ping()  # Test the connection
            logger.info("✅ Redis connection established!")
        except redis.ConnectionError as e:
            logger.error(f"Error connecting to Redis: {e}")
            self.client = None

    def is_connected(self) -> bool:
        """Check if Redis is available"""
        try:
            if self.client:
                self.client.ping()
                return True
            return False
        except redis.ConnectionError:
            return False


# This ensures we reuse the same connection throughout the app
redis_manager = RedisManager()
