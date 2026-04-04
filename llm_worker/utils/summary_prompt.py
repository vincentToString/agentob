def build_summary_prompt(run_data: dict, spans: list[dict], alerts: list[dict]) -> str:
    """
    Build prompt for LLM to generate run summary.
    
    Args:
        run_data: Run metadata from fetch_run_data()
        spans: List of span summaries
        alerts: List of alerts/anomalies
    
    Returns:
        Formatted prompt string
    """
    run = run_data["run"]
    
    # Format cost
    cost_str = f"${run['total_cost_usd']:.4f}" if run.get('total_cost_usd') else "$0.0000"
    
    # Format duration
    duration_ms = run.get('duration_ms', 0)
    if duration_ms >= 1000:
        duration_str = f"{duration_ms / 1000:.1f}s"
    else:
        duration_str = f"{duration_ms}ms"
    
    # Build anomaly summary
    anomaly_summary = ""
    if alerts:
        critical = [a for a in alerts if a['severity'] == 'critical']
        warnings = [a for a in alerts if a['severity'] == 'warning']
        
        anomaly_parts = []
        if critical:
            anomaly_parts.append(f"🔴 {len(critical)} critical issue(s):")
            for alert in critical[:3]:  # Top 3
                anomaly_parts.append(f"  - {alert['title']}")
        
        if warnings:
            anomaly_parts.append(f"⚠️  {len(warnings)} warning(s):")
            for alert in warnings[:2]:  # Top 2
                anomaly_parts.append(f"  - {alert['title']}")
        
        anomaly_summary = "\n".join(anomaly_parts)
    else:
        anomaly_summary = "✅ No anomalies detected"
    
    # Build span type breakdown
    span_types = {}
    for span in spans:
        stype = span['span_type']
        span_types[stype] = span_types.get(stype, 0) + 1
    
    span_breakdown = ", ".join([f"{count} {stype}" for stype, count in span_types.items()])

    # Rebuild issue text in plain ASCII so the prompt is stable across terminals/logs.
    if alerts:
        critical = [a for a in alerts if a["severity"] == "critical"]
        warnings = [a for a in alerts if a["severity"] == "warning"]
        anomaly_parts = []
        if critical:
            anomaly_parts.append(f"CRITICAL: {len(critical)} issue(s)")
            for alert in critical[:3]:
                anomaly_parts.append(f"- {alert['title']}")
        if warnings:
            anomaly_parts.append(f"WARNING: {len(warnings)} issue(s)")
            for alert in warnings[:2]:
                anomaly_parts.append(f"- {alert['title']}")
        anomaly_summary = "\n            ".join(anomaly_parts)
    else:
        anomaly_summary = "No anomalies detected"

    # Include a few concrete span names so the model can describe what the agent did.
    notable_steps = []
    seen_steps = set()
    for span in spans:
        name = (span.get("name") or "").strip()
        if not name:
            continue

        key = (span.get("span_type"), name)
        if key in seen_steps:
            continue

        seen_steps.add(key)
        notable_steps.append(f"- {span['span_type']}: {name}")
        if len(notable_steps) >= 8:
            break

    notable_steps_str = "\n            ".join(notable_steps) if notable_steps else "- No span names available"
    
    # Construct prompt
    prompt = f"""
            You are analyzing an AI agent execution run. Generate a concise, natural 2-3 sentence summary describing what happened.
            # Run Details
            - Agent: {run['agent_name']}
            - Duration: {duration_str}
            - Cost: {cost_str}
            - Total Spans: {run['total_spans']} ({span_breakdown})
            - Tokens: {run.get('total_tokens_input', 0)} input, {run.get('total_tokens_output', 0)} output

            # Notable Steps
            {notable_steps_str}

            # Performance & Issues
            {anomaly_summary}

            # Instructions
            Generate a 2-3 sentence summary that:
            1. Describes what the agent accomplished (infer from span types and names)
            2. Mentions performance (fast/slow, efficient/expensive)
            3. Highlights any critical issues if present
            4. Uses natural language (not bullet points)

            Return ONLY the summary text, no preamble.
            """

    return prompt.encode("ascii", "ignore").decode()
