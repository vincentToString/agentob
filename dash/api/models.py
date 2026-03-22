from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class ServiceInstance(BaseModel):
    service_name: str
    instance_id: str
    status: ServiceStatus
    activity: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    uptime_seconds: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueueStats(BaseModel):
    queue_name: str
    messages_ready: int  # Waiting to be processed
    messages_unacked: int  # Being processed
    messages_total: int
    consumers: int
    avg_processing_time: Optional[float] = None  # seconds


class ReviewHistoryItem(BaseModel):
    review_id: str
    repo_name: str
    pr_number: int
    pr_url: str
    status: str  # "queued", "processing", "completed", "failed"
    created_at: datetime
    completed_at: Optional[datetime] = None
    processing_time: Optional[float] = None  # seconds
    tokens_used: Optional[int] = None
    estimated_cost: Optional[float] = None  # USD
    error_message: Optional[str] = None


class TokenEstimate(BaseModel):
    queue_name: str
    estimated_tokens_in_queue: int
    estimated_cost_usd: float
    avg_tokens_per_review: int


class LatencyMetrics(BaseModel):
    service: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    avg_ms: float
    sample_size: int


class DashboardOverview(BaseModel):
    timestamp: datetime
    services: List[ServiceInstance]
    queues: List[QueueStats]
    recent_reviews: List[ReviewHistoryItem]
    token_estimates: List[TokenEstimate]
    latency_metrics: List[LatencyMetrics]

    # Aggregate stats
    total_reviews_today: int
    total_reviews_week: int
    success_rate_24h: float
    avg_processing_time_24h: float
    total_cost_today: float
