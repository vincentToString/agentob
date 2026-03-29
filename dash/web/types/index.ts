export interface ServiceInstance {
  service_name: string;
  instance_id: string;
  status: "healthy" | "degraded" | "down" | "unknown";
  activity: "idle" | "busy" | null;
  last_heartbeat: string | null;
  uptime_seconds: number | null;
  metadata: Record<string, any>;
}

export interface QueueStats {
  queue_name: string;
  messages_ready: number;
  messages_unacked: number;
  messages_total: number;
  consumers: number;
  avg_processing_time: number | null;
}

export interface TokenEstimate {
  queue_name: string;
  estimated_tokens_in_queue: number;
  estimated_cost_usd: number;
  avg_tokens_per_review: number;
}

export interface LatencyMetrics {
  service: string;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  avg_ms: number;
  sample_size: number;
}

// New trace types
export interface TraceListItem {
  run_id: string;
  agent_name: string;
  agent_framework: string | null;
  status: string;
  total_spans: number;
  total_cost_usd: number;
  duration_ms: number | null;
  anomaly_count: number;
  baseline_deviation_score: number;
  llm_summary: string | null;
  started_at: string;
}

export interface SpanTreeNode {
  span_id: string;
  parent_span_id: string | null;
  span_type: string;
  name: string;
  duration_ms: number | null;
  cost_usd: number | null;
  tokens_input: number | null;
  tokens_output: number | null;
  tool_name: string | null;
  tool_status: string | null;
  is_anomalous: boolean;
  anomaly_type: string | null;
  depth: number;
  children: SpanTreeNode[];
}

export interface TraceDetail {
  run_id: string;
  agent_name: string;
  status: string;
  total_spans: number;
  total_cost_usd: number;
  total_tokens_input: number;
  total_tokens_output: number;
  duration_ms: number | null;
  anomaly_count: number;
  baseline_deviation_score: number;
  llm_summary: string | null;
  span_tree: any[]; // Recursive structure
  started_at: string;
  completed_at: string | null;
}

export interface AlertItem {
  alert_id: string;
  run_id: string | null;
  alert_type: string;
  severity: string;
  title: string;
  description: string | null;
  created_at: string;
}

export interface DashboardOverview {
  timestamp: string;
  services: ServiceInstance[];
  queues: QueueStats[];
  recent_traces: TraceListItem[];
  recent_alerts: AlertItem[];
  token_estimates: TokenEstimate[];
  latency_metrics: LatencyMetrics[];
  total_reviews_today: number;
  total_reviews_week: number;
  success_rate_24h: number;
  avg_processing_time_24h: number;
  total_cost_today: number;
}
