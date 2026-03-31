import redis.asyncio as redis
import os
import logging
from typing import Dict
import json


log = logging.getLogger(__name__)

class RedisClient:
    def __init__(self, url: str):
        self.url = url
        self._client = None

    async def get_client(self):
        """Get or create Redis client"""
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True
            )
            log.info(f"Redis client connected to {self.url}")
        return self._client

    # ========== SPAN DATA STORAGE (for large fields) ==========

    async def store_span_data(self, key: str, data: dict, ttl: int = 3600) -> bool:
        """
        Store large span fields (input_data/output_data) temporarily.
        Used when span fields exceed size threshold to avoid bloating message queue.

        Args:
            key: Redis key (e.g., "span_data:{span_id}:input")
            data: Dictionary to store
            ttl: Time-to-live in seconds (default 1 hour)
        """
        try:
            client = await self.get_client()
            await client.setex(key, ttl, json.dumps(data))
            log.info(f"Stored span data: {key} ({len(json.dumps(data))} bytes)")
            return True
        except Exception as e:
            log.error(f"Failed to store span data {key}: {e}")
            return False

    async def get_span_data(self, key: str) -> dict | None:
        """
        Retrieve large span fields stored in Redis.
        Worker calls this to hydrate span data before processing.

        Args:
            key: Redis key (e.g., "span_data:{span_id}:input")

        Returns:
            Dictionary if found, None otherwise
        """
        try:
            client = await self.get_client()
            data_json = await client.get(key)
            if data_json:
                log.debug(f"Retrieved span data: {key}")
                return json.loads(data_json)
            else:
                log.warning(f"Span data not found or expired: {key}")
                return None
        except Exception as e:
            log.error(f"Failed to retrieve span data {key}: {e}")
            return None

    # ========== SERVICE HEARTBEAT & REGISTRATION ==========

    async def register_instance(self, service_name: str, instance_id: str) -> bool:
        """Register service instance in Redis set"""
        try:
            client = await self.get_client()
            instances_key = f"service:{service_name}:instances"
            await client.sadd(instances_key, instance_id)
            return True
        except Exception as e:
            log.error(f"Failed to register instance {instance_id} for {service_name}: {e}")
            return False

    async def deregister_instance(self, service_name: str, instance_id: str) -> bool:
        """Deregister service instance from Redis set"""
        try:
            client = await self.get_client()
            instances_key = f"service:{service_name}:instances"
            await client.srem(instances_key, instance_id)
            return True
        except Exception as e:
            log.error(f"Failed to deregister instance {instance_id} for {service_name}: {e}")
            return False

    async def publish_heartbeat(self, service_name: str, instance_id: str, payload: Dict, ttl: int) -> bool:
        """Publish heartbeat payload with TTL"""
        try:
            client = await self.get_client()
            heartbeat_key = f"service:{service_name}:instance:{instance_id}:heartbeat"
            await client.set(heartbeat_key, json.dumps(payload), ex=ttl)
            return True
        except Exception as e:
            log.warning(f"Failed to publish heartbeat for {service_name} instance {instance_id}: {e}")
            return False

    async def close(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            log.info("Redis client closed")
