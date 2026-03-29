import asyncio
import aiohttp
import asyncpg
import redis.asyncio as aioredis
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import logging

from models import (
    ServiceInstance, ServiceStatus, QueueStats,
    ReviewHistoryItem, TokenEstimate, LatencyMetrics
)
import models
from config import config

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects metrics from various sources"""

    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.db_pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Initialize connections"""
        try:
            self.redis_client = await aioredis.from_url(
                config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")

        try:
            self.db_pool = await asyncpg.create_pool(
                config.database_url,
                min_size=2,
                max_size=10
            )
            logger.info("PostgreSQL connection pool created")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")

    async def close(self):
        """Close connections"""
        if self.redis_client:
            await self.redis_client.close()
        if self.db_pool:
            await self.db_pool.close()

    # ==========================================
    # SERVICE HEALTH METRICS
    # ==========================================

    async def get_service_instances(self) -> List[ServiceInstance]:
        """Get all service instances from Redis heartbeats (multi-instance aware)."""
        if not self.redis_client:
            return []

        instances: List[ServiceInstance] = []
        service_names = ["intake", "ai_service", "outbound"]

        for service in service_names:
            instances_key = f"service:{service}:instances"

            try:
                instance_ids = await self.redis_client.smembers(instances_key)
                instance_ids = {i.decode() if isinstance(i, (bytes, bytearray)) else i for i in instance_ids}

                if not instance_ids:
                    # No registered instances at all
                    instances.append(ServiceInstance(
                        service_name=service,
                        instance_id="none",
                        status=ServiceStatus.UNKNOWN,
                        last_heartbeat=None,
                        metadata={"note": "No instances registered"}
                    ))
                    continue

                for instance_id in instance_ids:
                    heartbeat_key = f"service:{service}:instance:{instance_id}:heartbeat"
                    try:
                        heartbeat_data = await self.redis_client.get(heartbeat_key)

                        if heartbeat_data:
                            data = json.loads(heartbeat_data)

                            # Tolerate missing timezone
                            ts = data.get("timestamp")
                            last = None
                            if ts:
                                try:
                                    last = datetime.fromisoformat(ts)
                                except Exception:
                                    last = None

                            instances.append(ServiceInstance(
                                service_name=service,
                                instance_id=data.get("instance_id", instance_id),
                                status=ServiceStatus.HEALTHY,
                                activity=data.get("activity"),
                                last_heartbeat=last,
                                uptime_seconds=data.get("uptime_seconds"),
                                metadata=data.get("metadata", {})
                            ))
                        else:
                            # Heartbeat key missing => probably dead/stopped.
                            instances.append(ServiceInstance(
                                service_name=service,
                                instance_id=instance_id,
                                status=ServiceStatus.DOWN,
                                last_heartbeat=None,
                                metadata={"note": "Heartbeat expired or missing"}
                            ))

                            try:
                                await self.redis_client.srem(instances_key, instance_id)
                            except Exception as prune_err:
                                logger.warning(
                                    "Failed to prune stale instance: service=%s instance=%s err=%s",
                                    service, instance_id, prune_err
                                )

                    except Exception as e:
                        logger.error(f"Error reading heartbeat for {service}/{instance_id}: {e}")
                        instances.append(ServiceInstance(
                            service_name=service,
                            instance_id=instance_id,
                            status=ServiceStatus.DOWN,
                            last_heartbeat=None,
                            metadata={"error": str(e)}
                        ))

            except Exception as e:
                logger.error(f"Error checking {service} instances: {e}")
                instances.append(ServiceInstance(
                    service_name=service,
                    instance_id="error",
                    status=ServiceStatus.DOWN,
                    last_heartbeat=None,
                    metadata={"error": str(e)}
                ))

        return instances

    # ==========================================
    # RABBITMQ QUEUE METRICS
    # ==========================================

    async def get_queue_stats(self) -> List[QueueStats]:
        """Get queue statistics from RabbitMQ Management API"""
        queues_to_monitor = ["trace_events", "alerts", "slack_msgs"]
        stats = []

        try:
            # Parse credentials from URL
            import base64
            from urllib.parse import urlparse
            parsed = urlparse(config.RABBITMQ_MANAGEMENT_URL)

            # Create Basic Auth header
            if parsed.username and parsed.password:
                credentials = f"{parsed.username}:{parsed.password}"
                auth_header = base64.b64encode(credentials.encode()).decode()
                headers = {"Authorization": f"Basic {auth_header}"}
            else:
                headers = {}

            # Build URL without credentials
            base_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 15672}"

            async with aiohttp.ClientSession() as session:
                url = f"{base_url}/api/queues"
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"RabbitMQ API error: {response.status}")
                        return stats

                    queues_data = await response.json()

                    for queue in queues_data:
                        queue_name = queue.get("name")
                        if queue_name in queues_to_monitor:
                            # Get avg processing time from Redis if available
                            avg_time = await self._get_avg_processing_time(queue_name)

                            stats.append(QueueStats(
                                queue_name=queue_name,
                                messages_ready=queue.get("messages_ready", 0),
                                messages_unacked=queue.get("messages_unacknowledged", 0),
                                messages_total=queue.get("messages", 0),
                                consumers=queue.get("consumers", 0),
                                avg_processing_time=avg_time
                            ))
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")

        return stats

    async def _get_avg_processing_time(self, queue_name: str) -> Optional[float]:
        """Get average processing time for queue from Redis"""
        if not self.redis_client:
            return None

        try:
            key = f"metrics:queue:{queue_name}:avg_processing_time"
            value = await self.redis_client.get(key)
            return float(value) if value else None
        except Exception:
            return None

    # ==========================================
    # REVIEW HISTORY (from DB)
    # ==========================================

    async def get_recent_reviews(self, limit: int = 50) -> List[ReviewHistoryItem]:
        """Get recent review history from database"""
        if not self.db_pool:
            return []

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        review_id,
                        repo_name,
                        pr_number,
                        pr_url,
                        status,
                        created_at,
                        completed_at,
                        EXTRACT(EPOCH FROM (completed_at - created_at)) as processing_time,
                        tokens_used,
                        estimated_cost,
                        error_message
                    FROM review_history
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)

                return [
                    ReviewHistoryItem(
                        review_id=row["review_id"],
                        repo_name=row["repo_name"],
                        pr_number=row["pr_number"],
                        pr_url=row["pr_url"],
                        status=row["status"],
                        created_at=row["created_at"],
                        completed_at=row["completed_at"],
                        processing_time=row["processing_time"],
                        tokens_used=row["tokens_used"],
                        estimated_cost=row["estimated_cost"],
                        error_message=row["error_message"]
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get review history: {e}")
            return []

    async def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics"""
        if not self.db_pool:
            return self._empty_stats()

        async with self.db_pool.acquire() as conn:
            # Today's stats
            today_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    AVG(duration_ms) as avg_duration,
                    SUM(total_cost_usd) as total_cost
                FROM agent_runs
                WHERE started_at >= CURRENT_DATE
            """)
            
            # Week's stats
            week_stats = await conn.fetchrow("""
                SELECT COUNT(*) as total
                FROM agent_runs
                WHERE started_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            
            total_today = today_stats["total"] or 0
            completed_today = today_stats["completed"] or 0
            
            return {
                "total_today": total_today,
                "total_week": week_stats["total"] or 0,
                "success_rate": (completed_today / total_today * 100) if total_today > 0 else 0.0,
                "avg_time": float(today_stats["avg_duration"] or 0) / 1000,  # Convert to seconds
                "total_cost": float(today_stats["total_cost"] or 0),
            }

    def _empty_stats(self) -> Dict[str, Any]:
        return {
            "total_reviews_today": 0,
            "total_reviews_week": 0,
            "success_rate_24h": 0.0,
            "avg_processing_time_24h": 0.0,
            "total_cost_today": 0.0
        }

    # ==========================================
    # TOKEN ESTIMATES
    # ==========================================

    async def get_token_estimates(self) -> List[TokenEstimate]:
        """Estimate tokens in queue based on historical averages"""
        queue_stats = await self.get_queue_stats()
        estimates = []

        # Average tokens per review (from historical data)
        avg_tokens = await self._get_avg_tokens_per_review()
        cost_per_1k_tokens = 0.003  # AWS Bedrock Claude Sonnet pricing

        for queue in queue_stats:
            total_messages = queue.messages_ready + queue.messages_unacked
            estimated_tokens = total_messages * avg_tokens
            estimated_cost = (estimated_tokens / 1000) * cost_per_1k_tokens

            estimates.append(TokenEstimate(
                queue_name=queue.queue_name,
                estimated_tokens_in_queue=estimated_tokens,
                estimated_cost_usd=round(estimated_cost, 4),
                avg_tokens_per_review=avg_tokens
            ))

        return estimates

    async def _get_avg_tokens_per_review(self) -> int:
        """Get average tokens per review from recent history"""
        if not self.db_pool:
            return 5000  # Default estimate

        try:
            async with self.db_pool.acquire() as conn:
                avg = await conn.fetchval("""
                    SELECT AVG(tokens_used)
                    FROM review_history
                    WHERE tokens_used IS NOT NULL
                    AND created_at >= NOW() - INTERVAL '7 days'
                """)
                return int(avg) if avg else 5000
        except Exception:
            return 5000

    # ==========================================
    # LATENCY METRICS
    # ==========================================

    async def get_latency_metrics(self) -> List[LatencyMetrics]:
        """Get latency percentiles from Redis (stored by services)"""
        if not self.redis_client:
            return []

        metrics = []
        services = ["intake", "ai_service", "outbound", "rag_service"]

        for service in services:
            try:
                key = f"metrics:latency:{service}"
                data = await self.redis_client.get(key)

                if data:
                    parsed = json.loads(data)
                    metrics.append(LatencyMetrics(
                        service=service,
                        p50_ms=parsed.get("p50", 0.0),
                        p95_ms=parsed.get("p95", 0.0),
                        p99_ms=parsed.get("p99", 0.0),
                        avg_ms=parsed.get("avg", 0.0),
                        sample_size=parsed.get("sample_size", 0)
                    ))
            except Exception as e:
                logger.error(f"Failed to get latency for {service}: {e}")

        return metrics

    async def get_recent_traces(self, limit: int = 20, project_id: Optional[str] = None) -> List[models.TraceListItem]:
        """Fetch recent traces from database"""
        if not self.db_pool:
            return []
        
        async with self.db_pool.acquire() as conn:
            if project_id:
                query = """
                    SELECT run_id, agent_name, agent_framework, status, 
                           total_spans, total_cost_usd, duration_ms, 
                           anomaly_count, baseline_deviation_score, llm_summary, started_at
                    FROM agent_runs 
                    WHERE project_id = $1
                    ORDER BY started_at DESC 
                    LIMIT $2
                """
                rows = await conn.fetch(query, project_id, limit)
            else:
                query = """
                    SELECT run_id, agent_name, agent_framework, status, 
                           total_spans, total_cost_usd, duration_ms, 
                           anomaly_count, baseline_deviation_score, llm_summary, started_at
                    FROM agent_runs 
                    ORDER BY started_at DESC 
                    LIMIT $1
                """
                rows = await conn.fetch(query, limit)
            
            return [models.TraceListItem(**dict(row)) for row in rows]

    async def get_trace_detail(self, run_id: str) -> Optional[models.TraceDetail]:
        """Fetch detailed trace data"""
        if not self.db_pool:
            return None
        
        async with self.db_pool.acquire() as conn:
            run = await conn.fetchrow(
                """
                SELECT run_id, agent_name, status, total_spans, total_cost_usd,
                       total_tokens_input, total_tokens_output, duration_ms,
                       anomaly_count, baseline_deviation_score, llm_summary,
                       span_tree, started_at, completed_at
                FROM agent_runs 
                WHERE run_id = $1
                """,
                run_id
            )
            
            if not run:
                return None
            
            # span_tree is stored as JSONB, convert to dict
            import json
            span_tree_data = json.loads(run["span_tree"]) if run["span_tree"] else []
            
            return models.TraceDetail(
                run_id=run["run_id"],
                agent_name=run["agent_name"],
                status=run["status"],
                total_spans=run["total_spans"],
                total_cost_usd=run["total_cost_usd"],
                total_tokens_input=run["total_tokens_input"],
                total_tokens_output=run["total_tokens_output"],
                duration_ms=run["duration_ms"],
                anomaly_count=run["anomaly_count"],
                baseline_deviation_score=run["baseline_deviation_score"],
                llm_summary=run["llm_summary"],
                span_tree=span_tree_data,
                started_at=run["started_at"],
                completed_at=run["completed_at"],
            )

    async def get_recent_alerts(self, limit: int = 50, severity: Optional[str] = None) -> List[models.AlertItem]:
        """Fetch recent alerts"""
        if not self.db_pool:
            return []
        
        async with self.db_pool.acquire() as conn:
            if severity:
                query = """
                    SELECT alert_id, run_id, alert_type, severity, title, description, created_at
                    FROM alerts 
                    WHERE severity = $1
                    ORDER BY created_at DESC 
                    LIMIT $2
                """
                rows = await conn.fetch(query, severity, limit)
            else:
                query = """
                    SELECT alert_id, run_id, alert_type, severity, title, description, created_at
                    FROM alerts 
                    ORDER BY created_at DESC 
                    LIMIT $1
                """
                rows = await conn.fetch(query, limit)
            
            return [models.AlertItem(**dict(row)) for row in rows]