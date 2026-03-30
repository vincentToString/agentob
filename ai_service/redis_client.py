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
    
    async def get_trace(self, trace_id: str) -> Optional[Dict]:
        """Retrieve trace content"""
        try:
            client = await self.get_client()
            trace_content = await client.get(f"trace:{trace_id}")
            if trace_content:
                log.info(f"Retrieved trace {trace_id}")
            else:
                log.warning(f"Trace {trace_id} not found or expired")
            return json.loads(trace_content)
        except Exception as e:
            log.error(f"Failed to retrieve trace {trace_id}: {e}")
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