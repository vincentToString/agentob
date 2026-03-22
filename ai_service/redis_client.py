import redis.asyncio as redis
import os
import logging
import json
from typing import Optional, Dict

log = logging.getLogger(__name__)

class RedisClient:
    def __init__(self, url: str):
        self.url = url
        self._client = None
    
    async def get_client(self):
        """Get or create Redis client"""
        if self._client is None:
            self._client = await redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True
            )
            log.info(f"Redis client connected to {self.url}")
        return self._client
    
    # async def store_diff(self, diff_id: str, diff_content: str, ttl: int = 3600) -> bool:
    #     """Store diff content with TTL (default 1 hour)"""
    #     try:
    #         client = await self.get_client()
    #         await client.setex(f"diff:{diff_id}", ttl, diff_content)
    #         log.info(f"Stored diff {diff_id} with TTL {ttl}s")
    #         return True
    #     except Exception as e:
    #         log.error(f"Failed to store diff {diff_id}: {e}")
    #         return False
    
    async def get_diff(self, diff_id: str) -> Optional[Dict]:
        """Retrieve diff content"""
        try:
            client = await self.get_client()
            diff_content = await client.get(f"diff:{diff_id}")
            if diff_content:
                log.info(f"Retrieved diff {diff_id}")
            else:
                log.warning(f"Diff {diff_id} not found or expired")
            return json.loads(diff_content)
        except Exception as e:
            log.error(f"Failed to retrieve diff {diff_id}: {e}")
            return None
    
    async def delete_diff(self, diff_id: str) -> bool:
        """Delete diff content"""
        try:
            client = await self.get_client()
            await client.delete(f"diff:{diff_id}")
            log.info(f"Deleted diff {diff_id}")
            return True
        except Exception as e:
            log.error(f"Failed to delete diff {diff_id}: {e}")
            return False
    
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