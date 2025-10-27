# naruto_bot/cache.py
import redis
import pickle
import logging
from .config import config

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Manages the Redis cache for player data, battle states, and rate limiting.
    """
    def __init__(self):
        try:
            # Using decode_responses=False to store pickled objects
            self.redis = redis.StrictRedis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=0,
                decode_responses=False
            )
            self.redis.ping()
            logger.info(f"Successfully connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")
        except redis.exceptions.ConnectionError as e:
            logger.critical(f"Failed to connect to Redis: {e}. Caching will be disabled.")
            self.redis = None

    def _get_key(self, key_type: str, key_id: any) -> str:
        """Helper to create standardized cache keys."""
        return f"naruto_bot:{key_type}:{key_id}"

    def set_data(self, key_type: str, key_id: any, data: any, ttl: int = None):
        """
        Serializes and stores data (like a Player object) in the cache.
        """
        if not self.redis:
            return
        
        key = self._get_key(key_type, key_id)
        try:
            serialized_data = pickle.dumps(data)
            self.redis.set(key, serialized_data, ex=ttl)
            logger.debug(f"Cached data for key: {key}")
        except (pickle.PickleError, redis.exceptions.RedisError) as e:
            logger.error(f"Failed to cache data for key {key}: {e}")

    def get_data(self, key_type: str, key_id: any) -> any:
        """
        Retrieves and deserializes data from the cache.
        """
        if not self.redis:
            return None
            
        key = self._get_key(key_type, key_id)
        try:
            serialized_data = self.redis.get(key)
            if serialized_data:
                logger.debug(f"Cache hit for key: {key}")
                return pickle.loads(serialized_data)
            else:
                logger.debug(f"Cache miss for key: {key}")
                return None
        except (pickle.PickleError, redis.exceptions.RedisError) as e:
            logger.error(f"Failed to retrieve/deserialize data for key {key}: {e}")
            return None
    
    def delete_data(self, key_type: str, key_id: any):
        """Deletes data from the cache."""
        if not self.redis:
            return
            
        key = self._get_key(key_type, key_id)
        try:
            self.redis.delete(key)
            logger.debug(f"Deleted cache for key: {key}")
        except redis.exceptions.RedisError as e:
            logger.error(f"Failed to delete cache for key {key}: {e}")

    # --- Battle/State Management ---

    def is_in_battle(self, user_id: int) -> bool:
        """Checks if a user is currently in a battle."""
        return self.get_data("battle_lock", user_id) is not None

    def set_battle_lock(self, user_id: int, opponent_id: int):
        """Locks a user into a battle state."""
        self.set_data("battle_lock", user_id, opponent_id, ttl=config.BATTLE_TIMEOUT_SECONDS)

    def remove_battle_lock(self, user_id: int):
        """Removes a user's battle lock."""
        self.delete_data("battle_lock", user_id)

    def get_battle_opponent(self, user_id: int) -> int | None:
        """Gets the ID of the user's battle opponent."""
        return self.get_data("battle_lock", user_id)

# Create a single cache manager instance to be imported by other files
cache_manager = CacheManager()
