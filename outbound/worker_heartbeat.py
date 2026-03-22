# outbound/heartbeat.py
import asyncio
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _default_instance_id() -> str:
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"

@dataclass
class WorkerHealthState:
    rabbitmq_connected: bool = False
    in_flight: int = 0
    recent_errors: int = 0
    last_progress_ts: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def set_connected(self, v: bool):
        async with self._lock:
            self.rabbitmq_connected = v

    async def on_msg_start(self):
        async with self._lock:
            self.in_flight += 1
            self.last_progress_ts = time.time()

    async def on_msg_ok(self):
        async with self._lock:
            self.last_progress_ts = time.time()
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
                "in_flight": self.in_flight,
                "recent_errors": self.recent_errors,
                "last_progress_ts": self.last_progress_ts,
                **self.extra,
            }

def _compute_status(
    snap: Dict[str, Any],
    *,
    max_errors: int = 10,
    max_stuck_s: int = 120,
) -> str:
    now = time.time()

    if not snap.get("rabbitmq_connected"):
        return "UNHEALTHY"

    if int(snap.get("recent_errors") or 0) >= max_errors:
        return "UNHEALTHY"

    in_flight = int(snap.get("in_flight") or 0)
    if in_flight > 0:
        last = snap.get("last_progress_ts")
        if last and (now - last) >= max_stuck_s:
            return "UNHEALTHY"

    return "HEALTHY"

async def heartbeat_loop(
    *,
    redis,  # your RedisClient
    state: WorkerHealthState,
    service_name: str,
    instance_id: Optional[str] = None,
    interval_s: int = 5,
    ttl_s: int = 15,
    max_errors: int = 10,
    max_stuck_s: int = 120,
    metadata: Optional[Dict[str, Any]] = None,
):
    instance_id = instance_id or _default_instance_id()
    metadata = metadata or {}

    await redis.register_instance(service_name, instance_id)

    start = time.time()
    while True:
        try:
            snap = await state.snapshot()
            status = _compute_status(snap, max_errors=max_errors, max_stuck_s=max_stuck_s)
            activity = "BUSY" if int(snap.get("in_flight") or 0) > 0 else "IDLE"

            now = time.time()
            in_flight = int(snap.get("in_flight") or 0)
            last = snap.get("last_progress_ts")
            stuck_s = (now - last) if (in_flight > 0 and last) else None

            payload = {
                "service": service_name,
                "instance_id": instance_id,
                "timestamp": _utc_now_iso(),
                "uptime_seconds": int(now - start),
                "status": status,
                "activity": activity,
                "checks": {
                    "rabbitmq_connected": bool(snap.get("rabbitmq_connected")),
                    "in_flight": in_flight,
                    "recent_errors": int(snap.get("recent_errors") or 0),
                    "stuck_s": stuck_s,
                },
                "metadata": metadata,
            }

            await redis.publish_heartbeat(service_name, instance_id, payload, ttl_s)

        except Exception as e:
            logger.warning(
                "Heartbeat publish failed: service=%s instance=%s err=%s",
                service_name, instance_id, e
            )

        await asyncio.sleep(interval_s)
