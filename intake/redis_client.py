import redis.asyncio as redis
import os
import logging
from typing import Dict
import json


log = logging.getLogger(__name__)

class RedisClient:
    def __init__(self, url: str):
        self.url=url
        self._client = None
    
    async def get_client(self):
        """Get or create new redis client"""
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True
            )
            log.info(f"Redis client connected to {self.url}")
        return self._client
    
    async def store_diff(self, diff_id: str, diff_content: str, ttl: int = 3600) -> bool:
        """Store diff content with TTL(default 1 hour)"""
        try:
            client = await self.get_client()
            await client.setex(f"diff:{diff_id}", ttl, diff_content)
            log.info(f"Stored diff {diff_id}")
            return True
        except Exception as e:
            log.error(f"Failed to store diff {diff_id}: {e}")
            return False
    
    async def store_rate(self, cache_key: str, scores: Dict[str, float], ttl: int = 6 * 60 * 60) -> bool:
        """Store PR's language priorities scores"""
        try:
            client = await self.get_client()
            await client.setex(cache_key, ttl, json.dumps(scores))
            return True
        except Exception as e:
            log.error(f"Failed to store language scores for {cache_key}: {e}")
            return False
        
    async def get_score(self, cache_key: str) -> Dict[str, float] | None:
        """Retrieve PR's language scores"""
        try:
            client = await self.get_client()
            scores_json = await client.get(cache_key)
            scores: Dict[str, float] = json.loads(scores_json)
            if scores_json:
                log.info(f"Retrieved language scores for {cache_key}")
            else:
                log.warning(f"Language scores for {cache_key} not found or expired")
            return scores
        except Exception as e:
            log.error(f"Failed to retrieve language scores for {cache_key}: {e}")
            return None
        
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
        