-- ============================================
-- AgentOB Database Schema
-- Agent Observability Platform
-- ============================================

-- ============================================
-- BASELINES: What "normal" looks like
-- ============================================

CREATE TABLE IF NOT EXISTS agent_baselines (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    
    -- Statistical baselines (computed from historical runs)
    avg_cost_usd DECIMAL(10, 6) DEFAULT 0,
    p50_duration_ms INT DEFAULT 0,
    p95_duration_ms INT DEFAULT 0,
    p99_duration_ms INT DEFAULT 0,
    avg_spans INT DEFAULT 0,
    
    -- Tracking
    sample_size INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(project_id, agent_name)
);

-- ============================================
-- AGENT RUNS: Top-level trace metadata
-- ============================================
CREATE TABLE IF NOT EXISTS agent_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(255) UNIQUE NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    agent_framework VARCHAR(100),
    model_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'completed',
    
    -- Input/Output
    input_text TEXT,
    output_text TEXT,
    
    -- Metrics
    total_tokens_input INT DEFAULT 0,
    total_tokens_output INT DEFAULT 0,
    total_cost_usd DECIMAL(10, 6) DEFAULT 0,
    total_spans INT DEFAULT 0,
    duration_ms INT,
    
    -- Anomaly detection
    anomaly_count INT DEFAULT 0,
    baseline_deviation_score DECIMAL(5, 2) DEFAULT 0,  -- NEW: How weird is this run?
    
    -- AI-generated insights
    llm_summary TEXT,
    
    -- Pre-computed span tree (for fast frontend rendering)
    span_tree JSONB,
    
    -- Timestamps
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Flexible metadata
    metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}'
);

-- ============================================
-- SPANS: Individual steps in agent execution
-- ============================================
CREATE TABLE IF NOT EXISTS spans (
    id SERIAL PRIMARY KEY,
    span_id VARCHAR(255) UNIQUE NOT NULL,
    run_id VARCHAR(255) NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    parent_span_id VARCHAR(255),
    
    -- Span identification
    span_type VARCHAR(50) NOT NULL,  -- 'llm_call', 'tool_use', 'decision', 'retrieval', 'error'
    name VARCHAR(512) NOT NULL,
    
    -- Data
    input_data JSONB,
    output_data JSONB,
    
    -- LLM-specific metrics
    model_id VARCHAR(255),
    tokens_input INT,
    tokens_output INT,
    cost_usd DECIMAL(10, 6),
    
    -- Tool-specific metrics
    tool_name VARCHAR(255),
    tool_status VARCHAR(50),  -- 'success', 'error', 'timeout'
    
    -- Timing
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms INT,
    
    -- Tree structure
    sequence_index INT NOT NULL,
    depth INT DEFAULT 0,
    
    -- Anomaly flags
    is_anomalous BOOLEAN DEFAULT FALSE,
    anomaly_type VARCHAR(100),
    anomaly_description TEXT,
    
    -- Flexible metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- ALERTS: Anomalies and issues detected
-- ============================================
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(255) UNIQUE NOT NULL,
    run_id VARCHAR(255) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    span_id VARCHAR(255),
    
    -- Alert classification
    alert_type VARCHAR(100) NOT NULL,  -- 'cost_spike', 'tool_failure', 'baseline_deviation', etc.
    severity VARCHAR(50) NOT NULL,  -- 'critical', 'warning', 'info'
    
    -- Details
    title VARCHAR(512) NOT NULL,
    description TEXT,
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- INDEXES: Performance optimization
-- ============================================
CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id);
CREATE INDEX IF NOT EXISTS idx_spans_type ON spans(span_type);
CREATE INDEX IF NOT EXISTS idx_spans_started ON spans(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_project ON agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_runs_started ON agent_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_alerts_run ON alerts(run_id);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_baselines_lookup ON agent_baselines(project_id, agent_name);

-- ============================================
-- INITIAL DATA: Example baseline
-- ============================================
INSERT INTO agent_baselines (project_id, agent_name, avg_cost_usd, p50_duration_ms, p95_duration_ms, p99_duration_ms, avg_spans, sample_size)
VALUES ('default', 'demo_agent', 0.005, 2000, 5000, 8000, 5, 0)
ON CONFLICT (project_id, agent_name) DO NOTHING;