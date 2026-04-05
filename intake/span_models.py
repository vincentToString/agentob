from pydantic import BaseModel, Field
from typing import Optional

class SpanEvent(BaseModel):
    """A single step in model execution"""

    # === Required fields ===
    span_id: str = Field(..., description="Unique span identifier (UUID from client)")
    run_id: str = Field(..., description="Execution session ID (UUID from client)") # run-1, run-2, or whatever, as long as it marked the whole execution
    agent_name: str = Field(..., description="Agent identifier (e.g., 'rag-agent-v2')") # one agent can have multiple runs, with multiple spans in each run
    project_id: str = Field(..., description="Project/experiment ID (e.g., 'baseline-2024')") # one project can have multiple agents, runs
    span_type: str = Field(..., description="llm_call, tool_use, decision, retrieval, error, custom") 
    name: str = Field(..., description="Human-readable step description - for each span")
    started_at: str = Field(..., description="ISO8601 timestamp when span started")
    completed_at: str = Field(..., description="ISO8601 timestamp when span finished") # span should be sent when it finishes
    is_final: bool = Field(..., description="True if this is the last span of the run") # this served as the end of the whole run

    # === Optional fields ===
    parent_span_id: Optional[str] = Field(None, description="Parent span ID for nested execution")
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds (computed if missing)")
    sequence_index: int = Field(0, description="Ordering hint from client") # optional, can be used to order spans if timestamps are unreliable or missing
    
    # LLM-specific metrics
    model_id: Optional[str] = None # same agent can have multiple models behind for each span, e.g. gpt-3.5 for retrieval, gpt-4 for generation, etc.
    tokens_input: Optional[int] = None # token for cost calculation/performance tracking
    tokens_output: Optional[int] = None
    cost_usd: Optional[float] = None # if missing, we provide an assumption based on model and its pricing 
    input_data: Optional[dict] = None # data for actual debugging
    output_data: Optional[dict] = None
    
    # Tool-specific metrics
    tool_name: Optional[str] = None
    tool_status: Optional[str] = None  # 'success', 'error', 'timeout'
    
    # Flexible metadata (future: prompt_hash, temperature, etc.)
    metadata: dict = Field(default_factory=dict, description="Additional custom metadata")


     # ======== Added by worker after =============
    # Anomaly detection (set by analyzer worker)
    is_anomalous: bool = Field(False, description="True if anomaly detected in this span")
    anomaly_type: Optional[str] = Field(None, description="Type of anomaly: slow_retrieval, high_cost, tool_failure, etc.")
    anomaly_description: Optional[str] = Field(None, description="Human-readable anomaly description")
    
    # Tree structure (set by analyzer worker when building tree)
    depth: int = Field(0, description="Depth in span tree (0=root)")

    # potential flag _redis_ref added after receival to indicate input/output data were stored in redis
    # Potential flag io_data_excluded after analyzer to omit large input/output data