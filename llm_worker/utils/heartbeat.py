import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import asyncio
from datetime import datetime, timezone
import os
from .redis_client import RedisClient
import logging

logger = logging.getLogger(__name__)

@dataclass
class WorkerHealthState:
    rabbitmq_connected: bool = False
    recent_errors: int = 0
    in_flight: int = 0
    last_progress_ts: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def set_connected(self, v: bool):
        async with self._lock:
            self.rabbitmq_connected = v

    async def on_msg_start(self):
        async with self._lock:
            self.in_flight += 1
            if self.last_progress_ts is None:
                self.last_progress_ts = time.time()

    async def on_msg_ok(self):
        now = time.time()
        async with self._lock:
            self.last_progress_ts = now
            if self.recent_errors > 0:
                self.recent_errors -= 1

    async def on_msg_error(self):
        async with self._lock:
            self.recent_errors += 1
            self.last_progress_ts = time.time()

    async def on_msg_done(self):
        async with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.last_progress_ts = time.time()

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return {
                "rabbitmq_connected": self.rabbitmq_connected,
                "recent_errors": self.recent_errors,
                "in_flight": self.in_flight,
                "last_progress_ts": self.last_progress_ts,
                **self.extra,
            }

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _compute_status(snap: Dict[str, Any], *, max_errors=10, max_stuck_s=300) -> str:
    now = time.time()
    connected = bool(snap.get("rabbitmq_connected"))
    recent_errors = int(snap.get("recent_errors") or 0)


    in_flight = int(snap.get("in_flight") or 0)
    last_progress_ts = snap.get("last_progress_ts")
    stuck_s = (now - last_progress_ts) if (in_flight > 0 and last_progress_ts) else None

    if not connected:
        return "UNHEALTHY"
    if recent_errors >= max_errors:
        return "UNHEALTHY"
    if stuck_s is not None and stuck_s >= max_stuck_s:
        return "UNHEALTHY"
    return "HEALTHY"

def _compute_activity(snap: Dict[str, Any]) -> str:
    in_flight = int(snap.get("in_flight") or 0)
    return "BUSY" if in_flight > 0 else "IDLE"

async def heartbeat_loop(
    *,
    redis: RedisClient,
    state: WorkerHealthState,
    service_name: str,
    instance_id: str,
    interval_s: int = 5,
    ttl_s: int = 15,
    max_errors: int = 10,
    max_stuck_s: int = 300,
):
    # register once
    await redis.register_instance(service_name, instance_id)

    start = time.time()
    while True:
        try:
            snap = await state.snapshot()
            status = _compute_status(
                snap, max_errors=max_errors, max_stuck_s=max_stuck_s
            )

            now = time.time()
            last_msg_ts = snap.get("last_msg_ts")
            last_msg_age_s = (now - last_msg_ts) if last_msg_ts else None

            payload = {
                "service": service_name,
                "instance_id": instance_id,
                "timestamp": _utc_now_iso(),
                "uptime_seconds": int(now - start),
                "status": status,
                "activity": _compute_activity(snap),
                "checks": {
                    "rabbitmq_connected": bool(snap.get("rabbitmq_connected")),
                    "recent_errors": int(snap.get("recent_errors") or 0),
                    "in_flight": int(snap.get("in_flight") or 0),
                    "last_msg_age_s": last_msg_age_s,
                },
                "metadata": {
                    "queue": "pr_review",
                    # add anything else you want here
                },
            }

            await redis.publish_heartbeat(service_name, instance_id, payload, ttl_s)

        except Exception as e:
            # do NOT crash the worker
            logger.warning("Heartbeat publish failed: service=%s instance=%s err=%s", service_name, instance_id, e)

        await asyncio.sleep(interval_s)