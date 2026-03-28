from pydantic import BaseModel
from typing import Optional

class SpanEvent(BaseModel):
    """A single step in agent execution"""
    span_id: str
    run_id: str
    parent_span_id: Optional[str] = None
    span_type: str  # 'llm_call', 'tool_use', 'decision', 'retrieval', 'error', 'custom'
    name: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    model_id: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost_usd: Optional[float] = None
    tool_name: Optional[str] = None
    tool_status: Optional[str] = None  # 'success', 'error', 'timeout'
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    sequence_index: int = 0
    metadata: dict = {}


class AgentTrace(BaseModel):
    """Complete trace of an agent run"""
    run_id: str
    project_id: Optional[str] = "default"
    agent_name: str
    agent_framework: Optional[str] = None  # 'langchain', 'crewai', 'autogen', 'custom'
    model_id: Optional[str] = None
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    status: str = "completed"  # 'completed', 'failed', 'timeout'
    started_at: str
    completed_at: Optional[str] = None
    spans: list[SpanEvent] = []
    metadata: dict = {}
    tags: list[str] = []