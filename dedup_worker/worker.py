"""Dedup Worker - Consumes spans from span_intake, deduplicates, publishes to span_processing"""
import asyncio
import json
import logging
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from .bloom_client import BloomBoxClient
from .config import Config

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)


class DedupWorker:
    """Worker that removes duplicate spans using BloomBox"""

    def __init__(self):
        self.config = Config
        self.connection = None
        self.channel = None
        self.bloom_client = BloomBoxClient(
            grpc_host=Config.BLOOMBOX_GRPC_HOST,
            grpc_port=Config.BLOOMBOX_GRPC_PORT,
            http_url=Config.BLOOMBOX_HTTP_URL
        )

        # Metrics
        self.total_consumed = 0
        self.total_duplicates = 0
        self.total_published = 0
        self.bloombox_unavailable_count = 0

    async def start(self):
        """Start the dedup worker"""
        log.info("🚀 Starting Dedup Worker...")

        # Connect to BloomBox (graceful degradation if unavailable)
        bloom_connected = await self.bloom_client.connect()
        if bloom_connected:
            log.info("✓ BloomBox connected - deduplication ENABLED")
        else:
            log.warning("⚠ BloomBox unavailable - deduplication DISABLED (pass-through mode)")

        # Connect to RabbitMQ
        self.connection = await connect_robust(self.config.RABBITMQ_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=self.config.PREFETCH_COUNT)

        log.info("✓ Connected to RabbitMQ")

        # Get span_intake queue
        span_intake_queue = await self.channel.get_queue("span_intake")

        # Get span_processing exchange for publishing
        self.span_processing_exchange = await self.channel.get_exchange("span_processing_exchange")

        log.info(f"✓ Consuming from span_intake queue (prefetch={self.config.PREFETCH_COUNT})")
        log.info("✓ Publishing to span_processing exchange")

        # Start consuming
        await span_intake_queue.consume(self.process_span)

        log.info("✅ Dedup Worker is running. Press Ctrl+C to stop.")

    async def process_span(self, message: AbstractIncomingMessage):
        """Process a single span message from span_intake queue"""
        async with message.process():
            try:
                span_data = json.loads(message.body.decode("utf-8"))
                span_id = span_data.get("span_id")
                run_id = span_data.get("run_id")

                self.total_consumed += 1

                log.debug(f"Processing span {span_id} (run: {run_id})")

                # Check for duplicate using BloomBox
                is_duplicate = False

                if self.bloom_client.is_available():
                    is_duplicate = await self.bloom_client.is_duplicate(span_id)

                    if is_duplicate:
                        self.total_duplicates += 1
                        log.info(f"⊗ Duplicate detected: {span_id} (run: {run_id}) - DROPPED")
                        return  # Drop duplicate

                else:
                    # BloomBox unavailable - pass through
                    self.bloombox_unavailable_count += 1
                    if self.bloombox_unavailable_count % 100 == 1:  # Log every 100th
                        log.warning(f"BloomBox unavailable - processing span {span_id} without dedup check")

                # Not a duplicate - mark as processed
                if self.bloom_client.is_available():
                    await self.bloom_client.mark_processed(span_id)

                # Publish to span_processing queue
                await self._publish_to_processing(span_data)

                self.total_published += 1

                # Log progress
                if self.total_consumed % 1000 == 0:
                    self._log_metrics()

            except json.JSONDecodeError as e:
                log.error(f"Invalid JSON in message: {e}")
            except Exception as e:
                log.error(f"Error processing span: {e}", exc_info=True)

    async def _publish_to_processing(self, span_data: dict):
        """Publish clean span to span_processing queue"""
        msg = Message(
            body=json.dumps(span_data).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={
                "run_id": span_data.get("run_id"),
                "agent": span_data.get("agent_name"),
                "project": span_data.get("project_id"),
                "span_type": span_data.get("span_type"),
                "is_final": span_data.get("is_final", False),
            },
        )

        await self.span_processing_exchange.publish(msg, routing_key="span")
        log.debug(f"✓ Published span {span_data.get('span_id')} to span_processing")

    def _log_metrics(self):
        """Log worker metrics"""
        dedup_rate = (self.total_duplicates / self.total_consumed * 100) if self.total_consumed > 0 else 0
        log.info(f"📊 Metrics: consumed={self.total_consumed}, "
                f"duplicates={self.total_duplicates} ({dedup_rate:.2f}%), "
                f"published={self.total_published}, "
                f"bloombox_unavailable={self.bloombox_unavailable_count}")

    async def stop(self):
        """Gracefully stop the worker"""
        log.info("Stopping Dedup Worker...")

        self._log_metrics()

        if self.bloom_client:
            await self.bloom_client.close()

        if self.channel:
            await self.channel.close()

        if self.connection:
            await self.connection.close()

        log.info("✓ Dedup Worker stopped")


async def main():
    """Main entry point"""
    worker = DedupWorker()

    try:
        await worker.start()
        # Keep running
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        log.info("Received shutdown signal")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
