import asyncio
import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_instance_id() -> str:
    # container hostname is a great default
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"


class HeartbeatEmitter:
    """
    Periodically publishes a heartbeat to Redis.

    Multi-instance support:
      - Adds instance_id to `service:{name}:instances` set
      - Writes heartbeat JSON to `service:{name}:instance:{id}:heartbeat` with TTL
    """

    def __init__(
        self,
        redis_client,
        service_name: str,
        instance_id: Optional[str] = None,
        interval_s: int = 5,
        ttl_s: int = 15,
        metadata: Optional[dict] = None,
    ):
        self.redis = redis_client
        self.service_name = service_name
        self.instance_id = instance_id or _default_instance_id()
        self.interval_s = interval_s
        self.ttl_s = ttl_s
        self.metadata = metadata or {}

        self._task: Optional[asyncio.Task] = None
        self._start_time = time.time()
        self._stop_event = asyncio.Event()


    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name=f"heartbeat:{self.service_name}:{self.instance_id}")
        logger.info("Heartbeat started: service=%s instance=%s", self.service_name, self.instance_id)

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("Heartbeat stopped: service=%s instance=%s", self.service_name, self.instance_id)

    async def _run(self) -> None:
        await self.redis.register_instance(
            self.service_name, self.instance_id
        )

        while not self._stop_event.is_set():
            try:
                uptime = int(time.time() - self._start_time)
                payload = {
                    "service": self.service_name,
                    "instance_id": self.instance_id,
                    "timestamp": _utc_now_iso(),
                    "uptime_seconds": uptime,
                    "metadata": self.metadata,
                }

                # Write heartbeat with TTL
                await self.redis.publish_heartbeat(
                    self.service_name,
                    self.instance_id,
                    payload,
                    self.ttl_s
                )

            except Exception as e:
                # DO NOT crash intake if Redis is temporarily down
                logger.warning("Heartbeat publish failed: service=%s instance=%s err=%s", self.service_name, self.instance_id, e)

            await asyncio.sleep(self.interval_s)