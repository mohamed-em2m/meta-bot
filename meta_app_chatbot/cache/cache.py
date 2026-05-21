from diskcache import Cache
from typing import Any, Optional
from meta_app_chatbot.agent.utils import generate_cache_key
import json


class SimpleCache:
    def __init__(
        self, directory: str = "/tmp/mycache", size_limit: Optional[int] = None
    ):
        """
        :param directory: Path on disk where cache files are stored
        :param size_limit: Maximum cache size in bytes. If None, no size limit.
        """
        # Initialize Cache with optional size limit (in bytes) and LRU eviction
        cache_kwargs = {}
        if size_limit is not None:
            cache_kwargs["size_limit"] = size_limit
        self._cache = Cache(
            directory, eviction_policy="least-recently-used", **cache_kwargs
        )

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key. Returns None if key is missing.
        """
        return self._cache.get(key, default=None)

    def get_auto(self, key) -> Optional[Any]:
        """
        Retrieve a value by key. Returns None if key is missing.
        """
        key = generate_cache_key(f"{key}")

        return json.loads(self._cache.get(key, default=None))

    def set(self, key: str, value: Any) -> bool:
        """
        Set a value without expiry.
        Returns True if successfully stored.
        """
        self._cache.set(key, value)
        return True

    def set_auto(self, key, value: Any) -> bool:
        """
        Set a value without expiry.
        Returns True if successfully stored.
        """
        key = generate_cache_key(f"{key}")

        self._cache.set(key, json.dumps(value))
        return True

    def setex_auto(self, key, ttl: int, value: Any) -> bool:
        """
        Set a value with an expiration (in seconds), like Redis SETEX.
        :param ttl: Time-to-live in seconds
        """
        key = generate_cache_key(f"{key}")

        self._cache.set(key, json.dumps(value), expire=ttl)
        return True

    def setex(self, key: str, ttl: int, value: Any) -> bool:
        """
        Set a value with an expiration (in seconds), like Redis SETEX.
        :param ttl: Time-to-live in seconds
        """
        self._cache.set(key, value, expire=ttl)
        return True

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache (and not expired).
        :return: True if present, False otherwise.
        """
        return key in self._cache

    def exists_auto(self, key) -> bool:
        """
        Check if a key exists in the cache (and not expired).
        :return: True if present, False otherwise.
        """
        key = generate_cache_key(f"{key}")

        return key in self._cache

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache. Returns True if the key was removed.
        """
        return self._cache.pop(key, default=None) is not None

    def delete_auto(self, key) -> bool:
        """
        Delete a key from the cache. Returns True if the key was removed.
        """
        key = generate_cache_key(f"{key}")

        return self._cache.pop(key, default=None) is not None

    def clear(self) -> None:
        """Remove all items from the cache."""
        self._cache.clear()


# Connect to Redis
cache_register = SimpleCache(directory="/tmp/mycache", size_limit=100 * 1024 * 1024)
