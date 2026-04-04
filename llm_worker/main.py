import asyncio
import json
import logging
import signal
from aio_pika import connect_robust, Message, DeliveryMode
from aio_pika.abc import AbstractIncomingMessage

from llm_worker.config import Config
from llm_worker.utils.db_operations import (
    fetch_run_data,
    update_run_summary,
    close_db_pool
)
from llm_worker.utils.summary_prompt import build_summary_prompt
from llm_worker.llm_client import generate_summary
from .utils.heartbeat import WorkerHealthState, heartbeat_loop
import os
import socket
from .utils.redis_client import RedisClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

redis_client = RedisClient(Config.REDIS_URL)

async def handle_message(message: AbstractIncomingMessage, channel):
    """Process LLM summary Request for a completed run
    
    Message format: {"run_id": "..."}
    """
    async with message.process(requeue=False):
        try:
            # Parse Data
            data = json.loads(message.body.decode("utf-8"))
            run_id = data.get("run_id")
            if not run_id:
                logger.error("No run_id in message")
                return

            # 1. fetch full trace from database
            run_data = await fetch_run_data(run_id)
            if not run_data:
                logger.error(f"Run {run_id} not found in database")
                return
            
            # 2. Build Prompt
            prompt = build_summary_prompt(
                run_data=run_data,
                spans=run_data["spans"],
                alerts=run_data["alerts"]
            )

            # 3. Call LLM
            try:
                summary = await generate_summary(prompt)
                logger.info(f"[OK] Generated summary for run {run_id} (length: {len(summary)} chars)")
            except Exception as e:
                logger.error(f"Failed to generate summary for {run_id}: {e}")
                summary = f"Summary generation failed: {str(e)[:100]}"
            
            # 4. Update database
            await update_run_summary(run_id, summary)
            
            # 5. Publish WebSocket event
            try:
                ws_exchange = await channel.get_exchange("websocket_events")
                ws_event = {
                    "type": "summary_updated",
                    "run_id": run_id,
                    "summary": summary
                }
                
                ws_msg = Message(
                    body=json.dumps(ws_event).encode("utf-8"),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    headers={
                        "event_type": "summary_updated",
                        "run_id": run_id
                    }
                )
                
                await ws_exchange.publish(ws_msg, routing_key="")
                logger.info(f"[OK] Published summary_updated event for {run_id}")
            
            except Exception as e:
                logger.warning(f"Failed to publish WebSocket event: {e}")
                # Don't fail - summary is already saved
            
            logger.info(f"[OK] Completed summary for run {run_id}")
        
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            raise                


def _default_instance_id() -> str:
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"

async def main():
    """Main Worker Loop"""
    logger.info("Starting LLM Summary Worker...")
    
    state = WorkerHealthState()
    instance_id = _default_instance_id()

    # Start Heartbeat
    hb_task = asyncio.create_task(
        heartbeat_loop(
            redis=redis_client,
            state=state,
            service_name="llm_worker",
            instance_id=instance_id,
            interval_s=20,
        ),
        name=f"heartbeat:llm_service:{instance_id}"
    )

    # Connect to RabbitMQ
    connection = await connect_robust(Config.RABBITMQ_URL)
    channel = await connection.channel()

    await state.set_connected(True)
    await channel.set_qos(prefetch_count=1)

    llm_queue = await channel.declare_queue("llm_summary", durable=True)
    stop_event = asyncio.Event()

    # setup consumer
    async def consumer(msg: AbstractIncomingMessage):
        await state.on_msg_start()
        try:
            await handle_message(msg, channel)
            await state.on_msg_ok()
        except Exception as e:
            logger.error(f"Message processing failed: {e}")
            await state.on_msg_error()
        finally:
            await state.on_msg_done()
    
    await llm_queue.consume(consumer)
    logger.info("[OK] Analyzer worker ready - consuming from trace_events queue")

    def _stop(*_):
        logger.info("Shutting down analyzer worker...")
        stop_event.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _stop)
        except NotImplementedError:
            pass
    
    await stop_event.wait()
    
    # Cleanup
    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass

    await redis_client.close()
    await connection.close()
    logger.info("[OK] Analyzer worker stopped")

if __name__ == "__main__":
    asyncio.run(main())


# async def fetch_rag_context(
#     files: list[dict], pr_title: str, pr_body: str = ""
# ) -> list[dict]:

#     if not Config.RAG_ENABLED:
#         logger.info("RAG is disabled, skipping context retrieval")
#         return []

#     try:
#         # Build query from PR context
#         languages = set(f.get("language", "").lower() for f in files if f.get("language"))
#         languages.discard("")
#         languages.discard("unknown")

#         # Check if any critical files
#         has_critical = any(f.get("is_critical", False) for f in files)

#         # Build contextual query
#         query_parts = [pr_title]
#         if pr_body:
#             query_parts.append(pr_body[:200])  # First 200 chars of description
#         if languages:
#             query_parts.append(f"languages: {', '.join(languages)}")
#         if has_critical:
#             query_parts.append("security critical")

#         query = " ".join(query_parts)

#         logger.info(f"RAG query: {query[:100]}... (languages: {languages})")

#         # Call RAG service
#         async with httpx.AsyncClient(timeout=Config.RAG_TIMEOUT) as client:
#             response = await client.post(
#                 f"{Config.RAG_SERVICE_URL}/api/v1/vector-index/query",
#                 json={"query": query, "top_k": Config.RAG_TOP_K},
#             )

#             if response.status_code == 200:
#                 data = response.json()
#                 chunks = data.get("chunks", [])
#                 logger.info(
#                     f"RAG retrieved {len(chunks)} chunks (top scores: "
#                     f"{[round(c.get('score', 0), 2) for c in chunks[:3]]})"
#                 )
#                 return chunks
#             else:
#                 logger.warning(
#                     f"RAG service returned {response.status_code}: {response.text[:100]}"
#                 )
#                 return []

#     except httpx.TimeoutException:
#         logger.warning(f"RAG service timeout after {Config.RAG_TIMEOUT}s")
#         return []
#     except Exception as e:
#         logger.error(f"RAG service error: {e}")
#         return []

# def build_rag_context_block(rag_chunks: list[dict]) -> str:
#     if not rag_chunks:
#         return "(no additional context available)"

#     blocks = []
#     for idx, chunk in enumerate(rag_chunks, 1):
#         content = chunk.get("content", "").strip()
#         score = chunk.get("score", 0.0)
#         doc_title = chunk.get("document_title", "")

#         if content:
#             header = f"[{idx}] Relevance: {score:.2f}"
#             if doc_title:
#                 header += f" | Source: {doc_title}"

#             blocks.append(f"{header}\n{content}")

#     return "\n\n".join(blocks) if blocks else "(no additional context available)"

