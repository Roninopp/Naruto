# naruto_bot/cache.py
import redis.asyncio as redis
import pickle
import logging
import asyncio
from .config import config

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Manages the connection and operations with the Redis cache.
    Uses asyncio for non-blocking operations.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implements the Singleton pattern."""
        if cls._instance is None:
            cls._instance = super(CacheManager, cls).__new__(cls)
            cls._instance.redis_client = None
        return cls._instance

    async def initialize(self):
        """Initializes the asynchronous Redis connection pool."""
        if self.redis_client is None:
            try:
                logger.info(f"Connecting to Redis at {config.REDIS_URL}...")
                self.redis_client = redis.from_url(
                    config.REDIS_URL,
                    decode_responses=False
                )
                await self.redis_client.ping()
                logger.info("Redis connection successful.")
            except Exception as e:
                logger.critical(f"Failed to initialize Redis connection: {e}")
                self.redis_client = None
                raise

    async def _get_client(self):
        """Ensures the client is initialized before use."""
        if self.redis_client is None:
            await self.initialize()
        if self.redis_client is None:
            raise ConnectionError("Redis client is not initialized.")
        return self.redis_client

    def _get_key(self, prefix: str, key: str) -> str:
        """Generates a namespaced key."""
        return f"naruto_bot:{prefix}:{key}"

    async def set_data(self, prefix: str, key: str, value: any, ttl: int = None):
        """Serializes (pickles) and caches data."""
        client = await self._get_client()
        full_key = self._get_key(prefix, str(key))
        serialized_value = pickle.dumps(value)
        try:
            await client.set(full_key, serialized_value, ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set cache for key {full_key}: {e}")

    async def get_data(self, prefix: str, key: str) -> any:
        """Retrieves and deserializes (unpickles) data from cache."""
        client = await self._get_client()
        full_key = self._get_key(prefix, str(key))
        try:
            serialized_value = await client.get(full_key)
            if serialized_value:
                return pickle.loads(serialized_value)
        except Exception as e:
            logger.error(f"Failed to get cache for key {full_key}: {e}")
        return None

    async def delete_data(self, prefix: str, key: str):
        """Deletes data from cache by key."""
        client = await self._get_client()
        full_key = self._get_key(prefix, str(key))
        try:
            await client.delete(full_key)
        except Exception as e:
            logger.error(f"Failed to delete cache for key {full_key}: {e}")

    async def close(self):
        """Closes the Redis connection pool."""
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            logger.info("Redis connection closed.")

    # --- Battle Specific Helpers ---

    async def set_battle_lock(self, user_id: int, opponent_id: int):
        """Locks a user into a battle."""
        await self.set_data("battle_lock", str(user_id), opponent_id, ttl=config.BATTLE_CACHE_TTL)

    async def is_in_battle(self, user_id: int) -> bool:
        """Checks if a user is in a battle."""
        return await self.get_data("battle_lock", str(user_id)) is not None

    async def get_battle_opponent(self, user_id: int) -> int | None:
        """Gets the ID of the user's opponent."""
        return await self.get_data("battle_lock", str(user_id))

# --- Global Instance ---
cache_manager = CacheManager()

# --- Standalone Test Function ---
async def test_redis_connection() -> bool:
    """A standalone function to test the Redis connection on startup."""
    try:
        client = redis.from_url(config.REDIS_URL)
        await client.ping()
        await client.aclose()
        return True
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False
