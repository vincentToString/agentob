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


class TraceListItem(BaseModel):
    """Summary of a trace for list view"""
    run_id: str
    agent_name: str
    agent_framework: Optional[str] = None
    status: str
    total_spans: int
    total_cost_usd: float
    duration_ms: Optional[int] = None
    anomaly_count: int = 0
    baseline_deviation_score: float = 0.0
    llm_summary: Optional[str] = None
    started_at: datetime


class SpanTreeNode(BaseModel):
    """Recursive span tree node"""
    span_id: str
    parent_span_id: Optional[str] = None
    span_type: str
    name: str
    duration_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    tool_name: Optional[str] = None
    tool_status: Optional[str] = None
    is_anomalous: bool = False
    anomaly_type: Optional[str] = None
    depth: int = 0
    children: List[dict] = []  # Recursive - will be SpanTreeNode


class TraceDetail(BaseModel):
    """Full trace details"""
    run_id: str
    agent_name: str
    status: str
    total_spans: int
    total_cost_usd: float
    total_tokens_input: int
    total_tokens_output: int
    duration_ms: Optional[int] = None
    anomaly_count: int = 0
    baseline_deviation_score: float = 0.0
    llm_summary: Optional[str] = None
    span_tree: List[dict] = []  # Pre-computed tree from worker
    started_at: datetime
    completed_at: Optional[datetime] = None


class AlertItem(BaseModel):
    """Alert/anomaly detected"""
    alert_id: str
    run_id: Optional[str]
    alert_type: str
    severity: str
    title: str
    description: Optional[str]
    created_at: datetime
    
class DashboardOverview(BaseModel):
    timestamp: datetime
    services: List[ServiceInstance]
    queues: List[QueueStats]
    recent_traces: List[TraceListItem]
    recent_alerts: List[AlertItem]
    token_estimates: List[TokenEstimate]
    latency_metrics: List[LatencyMetrics]

    # Aggregate stats
    total_reviews_today: int
    total_reviews_week: int
    success_rate_24h: float
    avg_processing_time_24h: float
    total_cost_today: float

