from pydantic import BaseModel, Field
from typing import Optional
import os


class Anomaly(BaseModel):
    """Detected anomaly in agent execution"""
    anomaly_type: str
    severity: str  # 'critical', 'warning', 'info'
    title: str
    description: str
    span_id: Optional[str] = None
    score: float = 0.0


class SpanNode(BaseModel):
    """A span with its children, for tree representation"""
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
    children: list["SpanNode"] = []


class AnalysisResult(BaseModel):
    """Result of trace analysis"""
    analysis_id: str = Field(default_factory=lambda: os.urandom(8).hex())
    run_id: str
    agent_name: str
    total_spans: int
    total_cost_usd: float
    total_duration_ms: int
    total_tokens_input: int
    total_tokens_output: int
    anomalies: list[Anomaly] = []
    span_tree: list[dict] = [] # Store as dict for JSON serialization
    llm_summary: str = ""
    baseline_deviation_score: float = 0.0
    llm_meta: dict = Field(default_factory=dict)