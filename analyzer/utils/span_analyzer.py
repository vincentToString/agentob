"""Span Analysis and Anomaly Detection"""
import json
import logging
from typing import Optional
from ..models.span_models import SpanEvent

logger = logging.getLogger(__name__)

# =========== Anomaly Detection based on baseline =================
def detect_span_anomalies(span: dict, baseline: Optional[dict] = None):
    """
    Detect anomalies in a single span.

    Returns list of anomalies:
    [
        {"type": "slow_retrieval", "severity": "warning", "message": "..."},
        {"type": "high_cost", "severity": "info", "message": "..."}
    ]
    """
    anomalies = []
    # Rule 1: Slow Retrieval (>3 seconds)
    if span.get("span_type") == "retrieval":
        duration = span.get("duration_ms") or 0
        if duration > 3000:
            anomalies.append({
                "type": "slow_retrieval",
                "severity": "warning",
                "message": f"Retrieval took {duration}ms (threshold: 3000ms)"
            })
    
    # Rule 2:Expensive LLM Call
    if span.get("span_type") == "llm_call":
        cost = span.get("cost_usd") or 0
        if cost > 0.01:
            anomalies.append({
                "type": "high_cost",
                "severity": "info",
                "message": f"LLM call cost ${cost:.4f} (threshold: $0.01)"
            })

    # Rule 3: Tool failure
    if span.get("span_type") == "tool_use":
        tool_status = span.get("tool_status")
        if tool_status == "error":
            tool_name = span.get("tool_name") or "unknown"
            anomalies.append({
                "type": "tool_failure",
                "severity": "critical",
                "message": f"Tool '{tool_name}' failed with status: error"
            })
        elif tool_status == "timeout":
            tool_name = span.get("tool_name") or "unknown"
            anomalies.append({
                "type": "tool_timeout",
                "severity": "warning",
                "message": f"Tool '{tool_name}' timed out"
            })

    # Rule 4: Large input data (>50KB)
    input_data = span.get("input_data")
    if input_data:
        try:
            input_size = len(json.dumps(input_data))
            if input_size > 50000:
                anomalies.append({
                    "type": "large_input",
                    "severity": "warning",
                    "message": f"Large input data: {input_size} bytes (threshold: 50KB)"
                })
        except Exception:
            pass  # Ignore serialization errors

    # Rule 5: Large output data (>50KB)
    output_data = span.get("output_data")
    if output_data:
        try:
            output_size = len(json.dumps(output_data))
            if output_size > 50000:
                anomalies.append({
                    "type": "large_output",
                    "severity": "warning",
                    "message": f"Large output data: {output_size} bytes (threshold: 50KB)"
                })
        except Exception:
            pass

    # Rule 6: Baseline deviation (if baseline provided)
    if baseline and span.get("span_type") == "llm_call":
        avg_duration = baseline.get("p50_duration_ms", 0)
        if avg_duration > 0:
            duration = span.get("duration_ms") or 0
            if duration > avg_duration * 2:
                anomalies.append({
                    "type": "baseline_deviation",
                    "severity": "warning",
                    "message": f"Duration {duration}ms is 2x slower than baseline ({avg_duration}ms)"
                })
    
    return anomalies