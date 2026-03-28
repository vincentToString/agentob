import logging
from typing import Tuple, List
from .models import Anomaly, SpanNode

logger = logging.getLogger(__name__)

def build_span_tree(spans: List[dict]) -> tuple[list[dict], dict]:
    """
    Convert flat span list into nested tree structure.
    Returns (tree_roots, depth_map) where depth_map is {span_id: depth}.
    
    This is done server-side
    """
    by_id = {s["span_id"]: {**s, "children": []} for s in spans}
    roots = []
    depth_map = {}
    
    for span in spans:
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(by_id[span["span_id"]])
        else:
            roots.append(by_id[span["span_id"]])
    
    # Compute depths via BFS
    def assign_depth(node, depth):
        depth_map[node["span_id"]] = depth
        node["depth"] = depth
        for child in node.get("children", []):
            assign_depth(child, depth + 1)
    
    for root in roots:
        assign_depth(root, 0)
    
    return roots, depth_map

def detect_anomalies(spans: list[dict], total_cost: float) -> list[Anomaly]:
    """Rule-based anomaly detection. No LLM needed."""
    anomalies = []
    
    # Cost spikes: any single span > 40% of total cost
    for span in spans:
        if span.get("cost_usd") and total_cost > 0:
            ratio = span["cost_usd"] / total_cost
            if ratio > 0.4 and len(spans) > 3:
                anomalies.append(Anomaly(
                    anomaly_type="cost_spike",
                    severity="warning",
                    title=f"Cost concentration in '{span['name']}'",
                    description=f"This span used {ratio:.0%} of total run cost (${span['cost_usd']:.4f} of ${total_cost:.4f})",
                    span_id=span["span_id"],
                    score=ratio,
                ))
    
    # Tool failures
    for span in spans:
        if span.get("span_type") == "tool_use" and span.get("tool_status") == "error":
            anomalies.append(Anomaly(
                anomaly_type="tool_failure",
                severity="critical",
                title=f"Tool '{span.get('tool_name', 'unknown')}' failed",
                description=f"Tool call returned error status",
                span_id=span["span_id"],
                score=1.0,
            ))
    
    # Slow spans (>30s)
    for span in spans:
        if span.get("duration_ms") and span["duration_ms"] > 30000:
            anomalies.append(Anomaly(
                anomaly_type="slow_span",
                severity="warning",
                title=f"Slow: {span['name']} ({span['duration_ms']/1000:.1f}s)",
                description=f"Exceeded 30s threshold",
                span_id=span["span_id"],
                score=span["duration_ms"] / 30000,
            ))
    
    # Excessive LLM calls (>10 in one run)
    llm_calls = [s for s in spans if s.get("span_type") == "llm_call"]
    if len(llm_calls) > 10:
        anomalies.append(Anomaly(
            anomaly_type="excessive_llm_calls",
            severity="info",
            title=f"{len(llm_calls)} LLM calls in single run",
            description="High number of LLM invocations may indicate inefficient agent logic",
            score=len(llm_calls) / 10,
        ))
    
    return anomalies

def compute_baseline_deviation(
    total_cost: float,
    total_duration: int,
    total_spans: int,
    baseline: dict
) -> float:
    """
    Compute how much this run deviates from baseline.
    Returns a score 0-10 where:
    - 0-2: Normal
    - 2-5: Slightly unusual
    - 5-8: Significantly different
    - 8+: Anomalous
    """
    if not baseline or baseline.get("sample_size", 0) == 0:
        return 0.0  # No baseline yet
    
    deviation_score = 0.0
    
    # Cost deviation
    avg_cost = baseline.get("avg_cost_usd", 0)
    if avg_cost > 0:
        cost_ratio = total_cost / avg_cost
        if cost_ratio > 2.0:  # 2x more expensive
            deviation_score += (cost_ratio - 1) * 2
        elif cost_ratio < 0.5:  # 2x cheaper (unusual but not bad)
            deviation_score += (1 - cost_ratio)
    
    # Duration deviation (use p95 as threshold)
    p95_duration = baseline.get("p95_duration_ms", 0)
    if p95_duration > 0 and total_duration > p95_duration:
        duration_ratio = total_duration / p95_duration
        deviation_score += (duration_ratio - 1) * 3
    
    # Span count deviation
    avg_spans = baseline.get("avg_spans", 0)
    if avg_spans > 0:
        span_ratio = total_spans / avg_spans
        if abs(span_ratio - 1) > 0.5:  # 50% more or fewer spans
            deviation_score += abs(span_ratio - 1) * 2
    
    return round(min(deviation_score, 10.0), 2)

def estimate_span_costs(spans: list[dict]) -> float:
    """
    Estimate cost for spans that don't have cost_usd set.
    Uses GPT-4o-mini pricing as default.
    Returns total cost across all spans.
    """
    total_cost = 0.0
    
    # GPT-4o-mini pricing (per 1M tokens)
    INPUT_PRICE = 0.150  # $0.150 per 1M input tokens
    OUTPUT_PRICE = 0.600  # $0.600 per 1M output tokens
    
    for span in spans:
        if span.get("cost_usd"):
            total_cost += span["cost_usd"]
        elif span.get("tokens_input") and span.get("tokens_output"):
            # Estimate cost if not provided
            estimated = (
                (span["tokens_input"] * INPUT_PRICE / 1_000_000) +
                (span["tokens_output"] * OUTPUT_PRICE / 1_000_000)
            )
            span["cost_usd"] = round(estimated, 6)
            total_cost += estimated
    
    return round(total_cost, 6)