"""BloomBox gRPC Client with graceful degradation"""
import grpc
import logging
import requests
from typing import Optional
import time

log = logging.getLogger(__name__)


class BloomBoxClient:
    """gRPC client for BloomBox with health checking and graceful degradation"""

    def __init__(self, grpc_host: str, grpc_port: int, http_url: str):
        self.grpc_address = f"{grpc_host}:{grpc_port}"
        self.http_url = http_url
        self.channel: Optional[grpc.Channel] = None
        self.stub = None
        self._is_healthy = False
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds

        log.info(f"BloomBox client configured: gRPC={self.grpc_address}, HTTP={http_url}")

    def _check_health(self) -> bool:
        """Check if BloomBox is healthy via HTTP health endpoint"""
        now = time.time()

        # Cache health status for interval to avoid excessive checks
        if now - self._last_health_check < self._health_check_interval:
            return self._is_healthy

        try:
            response = requests.get(f"{self.http_url}/health", timeout=2)
            self._is_healthy = response.status_code == 200
            self._last_health_check = now

            if self._is_healthy:
                log.debug("BloomBox health check: OK")
            else:
                log.warning(f"BloomBox health check failed: HTTP {response.status_code}")

            return self._is_healthy

        except Exception as e:
            self._is_healthy = False
            self._last_health_check = now
            log.warning(f"BloomBox health check failed: {e}")
            return False

    async def connect(self) -> bool:
        """Establish gRPC connection and initialize filter"""
        try:
            # Dynamic import to avoid startup failure if grpc-tools not installed
            from dedup_worker.bloom_pb2_grpc import BloomServiceStub
            from dedup_worker.bloom_pb2 import CreateFilterRequest

            # Check HTTP health first
            if not self._check_health():
                log.warning("BloomBox not healthy - will operate in pass-through mode")
                return False

            # Establish gRPC connection
            self.channel = grpc.aio.insecure_channel(self.grpc_address)
            self.stub = BloomServiceStub(self.channel)

            # Initialize bloom filter
            response = await self.stub.CreateFilter(CreateFilterRequest(
                filter_type="standard",
                expected_items=1000000,  # 1M spans
                false_pos_rate=0.01      # 1% FP rate
            ))

            log.info(f"✓ BloomBox connected and filter initialized: {response.message}")
            self._is_healthy = True
            return True

        except ImportError as e:
            log.error(f"gRPC proto files not generated: {e}")
            log.error("Run: python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. dedup_worker/bloom.proto")
            return False

        except Exception as e:
            log.warning(f"Failed to connect to BloomBox: {e}")
            log.warning("Operating in pass-through mode (no deduplication)")
            self._is_healthy = False
            return False

    async def is_duplicate(self, span_id: str) -> bool:
        """
        Check if span_id is a duplicate.
        Returns False if BloomBox is unavailable (graceful degradation).
        """
        if not self._is_healthy or not self.stub:
            return False  # Pass through if BloomBox down

        try:
            from dedup_worker.bloom_pb2 import CheckRequest

            response = await self.stub.Check(CheckRequest(
                data=span_id.encode('utf-8')
            ))

            return response.found

        except Exception as e:
            log.error(f"BloomBox check failed for span {span_id}: {e}")
            # Mark unhealthy and pass through
            self._is_healthy = False
            return False

    async def mark_processed(self, span_id: str) -> bool:
        """
        Add span_id to bloom filter.
        Returns False if BloomBox is unavailable.
        """
        if not self._is_healthy or not self.stub:
            return False

        try:
            from dedup_worker.bloom_pb2 import AddRequest

            response = await self.stub.Add(AddRequest(
                data=span_id.encode('utf-8')
            ))

            return response.success

        except Exception as e:
            log.error(f"BloomBox add failed for span {span_id}: {e}")
            self._is_healthy = False
            return False

    async def close(self):
        """Close gRPC connection"""
        if self.channel:
            await self.channel.close()
            log.info("BloomBox gRPC connection closed")

    def is_available(self) -> bool:
        """Check if BloomBox is currently available"""
        return self._is_healthy
