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

export interface ReviewHistoryItem {
  review_id: string;
  repo_name: string;
  pr_number: number;
  pr_url: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  processing_time: number | null;
  tokens_used: number | null;
  estimated_cost: number | null;
  error_message: string | null;
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

export interface DashboardOverview {
  timestamp: string;
  services: ServiceInstance[];
  queues: QueueStats[];
  recent_reviews: ReviewHistoryItem[];
  token_estimates: TokenEstimate[];
  latency_metrics: LatencyMetrics[];
  total_reviews_today: number;
  total_reviews_week: number;
  success_rate_24h: number;
  avg_processing_time_24h: number;
  total_cost_today: number;
}
