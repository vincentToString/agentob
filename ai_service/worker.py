import asyncio
from aio_pika.abc import AbstractIncomingMessage
import aio_pika
from aio_pika import Message, DeliveryMode
import os
import json
import logging
import signal
import httpx
from ai_service.models import AnalysisResult
from ai_service.config import Config
from ai_service.redis_client import RedisClient
from ai_service.trace_analyzer import (
    build_span_tree,
    detect_anomalies,
    compute_baseline_deviation,
    estimate_span_costs,
)
from ai_service.db_operations import (
    get_baseline,
    update_baseline,
    store_trace_to_db,
)
from .heartbeat import WorkerHealthState, heartbeat_loop
import socket

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

redis_client = RedisClient(Config.REDIS_URL)

async def process_trace(trace_data: dict) -> AnalysisResult:
    """
    Core processing pipeline for an agent trace.
    
    1. Parse spans
    2. Build span tree (parent→child relationships)
    3. Compute costs
    4. Detect anomalies (rules)
    5. Fetch baseline and compute deviation
    6. Generate LLM summary
    7. Store to PostgreSQL
    8. Update baseline
    9. Return result for alert publishing
    """
    run_id = trace_data["run_id"]
    agent_name = trace_data["agent_name"]
    project_id = trace_data.get("project_id", "default")
    spans_raw = trace_data.get("spans", [])
    
    if not spans_raw:
        logger.warning(f"Trace {run_id} has no spans")
        spans_raw = []
    
    # Convert Pydantic models to dicts if needed
    spans = [s if isinstance(s, dict) else s.model_dump() for s in spans_raw]
    
    # --- 1. COST ATTRIBUTION ---
    total_cost = estimate_span_costs(spans)
    
    total_tokens_in = sum(s.get("tokens_input", 0) for s in spans)
    total_tokens_out = sum(s.get("tokens_output", 0) for s in spans)
    total_duration = max((s.get("duration_ms", 0) for s in spans), default=0)
    
    # --- 2. BUILD SPAN TREE ---
    span_tree, depth_map = build_span_tree(spans)
    
    # --- 3. RULE-BASED ANOMALY DETECTION ---
    anomalies = detect_anomalies(spans, total_cost)
    
    # --- 4. BASELINE DEVIATION ---
    baseline = await get_baseline(project_id, agent_name)
    baseline_deviation_score = compute_baseline_deviation(
        total_cost, total_duration, len(spans), baseline or {}
    )
    
    # Add baseline deviation as anomaly if significant
    if baseline_deviation_score > 5.0:
        from ai_service.models import Anomaly
        anomalies.append(Anomaly(
            anomaly_type="baseline_deviation",
            severity="warning" if baseline_deviation_score < 8 else "critical",
            title=f"Unusual behavior detected (deviation score: {baseline_deviation_score})",
            description=f"This run deviates significantly from baseline. Cost: ${total_cost:.4f} (baseline: ${baseline.get('avg_cost_usd', 0):.4f}), Duration: {total_duration}ms (p95: {baseline.get('p95_duration_ms', 0)}ms)",
            score=baseline_deviation_score,
        ))
    
    # Mark anomalous spans
    anomaly_span_ids = {a.span_id for a in anomalies if a.span_id}
    for span in spans:
        if span["span_id"] in anomaly_span_ids:
            span["is_anomalous"] = True
            matching = next((a for a in anomalies if a.span_id == span["span_id"]), None)
            if matching:
                span["anomaly_type"] = matching.anomaly_type
                span["anomaly_description"] = matching.description
    
    # Rebuild tree with anomaly flags
    span_tree, depth_map = build_span_tree(spans)
    
    # --- 5. LLM SUMMARY (optional, can be simple for demo) ---
    llm_summary = generate_simple_summary(
        agent_name, len(spans), total_cost, total_duration, anomalies
    )
    
    # --- 6. STORE TO DATABASE ---
    await store_trace_to_db(
        trace_data=trace_data,
        spans=spans,
        depth_map=depth_map,
        span_tree=span_tree,
        total_cost=total_cost,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        total_duration=total_duration,
        anomalies=anomalies,
        llm_summary=llm_summary,
        baseline_deviation_score=baseline_deviation_score,
    )
    
    # --- 7. UPDATE BASELINE ---
    await update_baseline(project_id, agent_name, total_cost, total_duration, len(spans))
    
    return AnalysisResult(
        run_id=run_id,
        agent_name=agent_name,
        total_spans=len(spans),
        total_cost_usd=total_cost,
        total_duration_ms=total_duration,
        total_tokens_input=total_tokens_in,
        total_tokens_output=total_tokens_out,
        anomalies=anomalies,
        span_tree=span_tree,
        llm_summary=llm_summary,
        baseline_deviation_score=baseline_deviation_score,
    )

def generate_simple_summary(
    agent_name: str,
    span_count: int,
    total_cost: float,
    total_duration: int,
    anomalies: list,
) -> str:
    """
    Generate a simple text summary without calling LLM.
    For demo purposes, this is fast and deterministic.
    In production, you could call LLM for richer summaries.
    """
    summary_parts = [
        f"Agent '{agent_name}' completed execution with {span_count} steps",
        f"in {total_duration}ms, costing ${total_cost:.4f}."
    ]
    
    if anomalies:
        critical = [a for a in anomalies if a.severity == "critical"]
        warnings = [a for a in anomalies if a.severity == "warning"]
        
        if critical:
            summary_parts.append(f"🔴 {len(critical)} critical issue(s) detected.")
        if warnings:
            summary_parts.append(f"⚠️  {len(warnings)} warning(s) raised.")
    else:
        summary_parts.append("✅ No anomalies detected.")
    
    return " ".join(summary_parts)

async def handle_message(message: AbstractIncomingMessage, channel):
    """Handle incoming trace message from RabbitMQ"""
    async with message.process(requeue=False):
        event_dict = json.loads(message.body.decode("utf-8"))

        trace_id = event_dict.get("trace_id")

        if not trace_id:
            logger.error("No trace_id in message")
            return

        # Fetch trace from Redis
        trace_data = await redis_client.get_diff(trace_id)
        if not trace_data:
            logger.error(f"Trace {trace_id} not found in Redis")
            return

        logger.info(f"Processing trace {trace_id}")

        # Process trace
        result = await process_trace(trace_data)

        # If anomalies found, publish to alert exchange
        if result.anomalies:
            out_exchange = await channel.get_exchange("alert_exchange")
            msg = Message(
                body=json.dumps(result.model_dump()).encode("utf-8"),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await out_exchange.publish(msg, routing_key="")
            logger.info(f"Published {len(result.anomalies)} alerts for trace {trace_id}")

        logger.info(
            f"✓ Processed trace {trace_id}: {result.total_spans} spans, "
            f"${result.total_cost_usd:.4f}, {len(result.anomalies)} anomalies, "
            f"deviation score: {result.baseline_deviation_score}"
        )




async def fetch_rag_context(
    files: list[dict], pr_title: str, pr_body: str = ""
) -> list[dict]:

    if not Config.RAG_ENABLED:
        logger.info("RAG is disabled, skipping context retrieval")
        return []

    try:
        # Build query from PR context
        languages = set(f.get("language", "").lower() for f in files if f.get("language"))
        languages.discard("")
        languages.discard("unknown")

        # Check if any critical files
        has_critical = any(f.get("is_critical", False) for f in files)

        # Build contextual query
        query_parts = [pr_title]
        if pr_body:
            query_parts.append(pr_body[:200])  # First 200 chars of description
        if languages:
            query_parts.append(f"languages: {', '.join(languages)}")
        if has_critical:
            query_parts.append("security critical")

        query = " ".join(query_parts)

        logger.info(f"RAG query: {query[:100]}... (languages: {languages})")

        # Call RAG service
        async with httpx.AsyncClient(timeout=Config.RAG_TIMEOUT) as client:
            response = await client.post(
                f"{Config.RAG_SERVICE_URL}/api/v1/vector-index/query",
                json={"query": query, "top_k": Config.RAG_TOP_K},
            )

            if response.status_code == 200:
                data = response.json()
                chunks = data.get("chunks", [])
                logger.info(
                    f"RAG retrieved {len(chunks)} chunks (top scores: "
                    f"{[round(c.get('score', 0), 2) for c in chunks[:3]]})"
                )
                return chunks
            else:
                logger.warning(
                    f"RAG service returned {response.status_code}: {response.text[:100]}"
                )
                return []

    except httpx.TimeoutException:
        logger.warning(f"RAG service timeout after {Config.RAG_TIMEOUT}s")
        return []
    except Exception as e:
        logger.error(f"RAG service error: {e}")
        return []


def load_prompt_template(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"Prompt file not found: {path.resolve()}")


def render_prompt(
    prompt_template: str,
    event: PullRequestData,
    files: list[dict],
    snippets: list[dict],
    rag_context: list[dict] = None,
) -> str:
    rag_context = rag_context or []
    return (
        prompt_template.replace("{{repo_name}}", event.repo_name)
        .replace("{{pr_number}}", str(event.pr_number))
        .replace("{{pr_title}}", event.pr_title)
        .replace("{{pr_author}}", event.pr_author)
        .replace("{{pr_body}}", (event.pr_body or "")[:1000])
        .replace("{{files_table}}", build_files_table(files))
        .replace("{{snippets}}", build_snippets_block(snippets))
        .replace("{{rag_context}}", build_rag_context_block(rag_context))
    )




# Legacy OpenRouter helper
def call_openrouter(
    prompt_text: str, model: str, base_url: str, api_key: str, timeout_s: int
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pr-demo.local",
        "X-Title": "AI PR Reviewer Demo",
    }

    body = {
        "model": model,
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a precise code review assistant. Return ONLY JSON.",
            },
            {"role": "user", "content": prompt_text},
        ],
    }

    with httpx.Client(timeout=timeout_s, base_url=base_url) as client:
        response = client.post("/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)




def build_files_table(files: list[dict]) -> str:
    return (
        "\n".join(
            f'{file_info["filename"]} +{file_info["additions"]}/-{file_info["deletions"]}'
            for file_info in files
        )
        or "(no files parsed)"
    )


def build_snippets_block(snippets: list[dict]) -> str:
    if not snippets:
        return "(no change snippets)"

    blocks = []
    for snippet in snippets:
        parts = [f"--- file: {snippet['filename']}"]

        added_text = snippet.get("added_text") or ""
        removed_text = snippet.get("removed_text") or ""

        if added_text:
            parts.append("\n".join("+" + line for line in added_text.splitlines()))
        if removed_text:
            parts.append("\n".join("-" + line for line in removed_text.splitlines()))

        blocks.append("\n".join(parts))

    return "\n".join(blocks)


def build_rag_context_block(rag_chunks: list[dict]) -> str:
    if not rag_chunks:
        return "(no additional context available)"

    blocks = []
    for idx, chunk in enumerate(rag_chunks, 1):
        content = chunk.get("content", "").strip()
        score = chunk.get("score", 0.0)
        doc_title = chunk.get("document_title", "")

        if content:
            header = f"[{idx}] Relevance: {score:.2f}"
            if doc_title:
                header += f" | Source: {doc_title}"

            blocks.append(f"{header}\n{content}")

    return "\n\n".join(blocks) if blocks else "(no additional context available)"

def _default_instance_id() -> str:
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"


async def main():
    """Main worker loop"""
    state = WorkerHealthState()
    instance_id = _default_instance_id()

    # Start heartbeat
    hb_task = asyncio.create_task(
        heartbeat_loop(
            redis=redis_client,
            state=state,
            service_name="analyzer",
            instance_id=instance_id,
            interval_s=10,
        ),
        name=f"heartbeat:analyzer:{instance_id}",
    )

    # Connect to RabbitMQ
    conn = await aio_pika.connect_robust(Config.RABBITMQ_URL)
    channel = await conn.channel()
    await state.set_connected(True)

    await channel.set_qos(prefetch_count=1)

    # Consume from trace_events queue
    trace_queue = await channel.declare_queue("trace_events", durable=True)

    stop_event = asyncio.Event()

    async def consumer(msg: AbstractIncomingMessage):
        await state.on_msg_start()
        try:
            await handle_message(msg, channel)
            await state.on_msg_ok()
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            await state.on_msg_error()
        finally:
            await state.on_msg_done()

    await trace_queue.consume(consumer)
    logger.info("✓ Analyzer worker ready - consuming from trace_events queue")


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
    await conn.close()
    logger.info("✓ Analyzer worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
