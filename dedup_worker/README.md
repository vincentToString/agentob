# Dedup Worker

Deduplication worker that filters duplicate spans using BloomBox bloom filter service.

## Architecture

```
span_intake queue → Dedup Worker → BloomBox (gRPC)
                         ↓
                 span_processing queue
```

## Features

- **gRPC Communication**: Fast, efficient communication with BloomBox
- **Graceful Degradation**: If BloomBox is unavailable, worker logs warning and processes all spans (pass-through mode)
- **Health Checking**: Periodic HTTP health checks to BloomBox
- **Metrics Logging**: Tracks consumed, duplicates, published counts
- **High Throughput**: Configurable prefetch for batch processing

## Setup

### 1. Add Health Endpoint to BloomBox

In your BloomBox repository `cmd/main.go`, add this after gRPC server setup:

```go
// Add health check endpoint for HTTP gateway
http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    w.Write([]byte(`{"status":"healthy","service":"bloombox"}`))
})

log.Printf("Health check available at http://localhost%s/health", httpPort)
```

### 2. Install Dependencies

```bash
cd dedup_worker
uv sync
```

### 3. Generate gRPC Stubs

```bash
chmod +x generate_grpc.sh
./generate_grpc.sh
```

Or manually:

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. bloom.proto
```

This generates:
- `bloom_pb2.py` - Protocol buffer messages
- `bloom_pb2_grpc.py` - gRPC client stubs

### 4. Start BloomBox (Separate Repository)

```bash
cd /path/to/bloombox
docker compose up -d
```

Verify:
```bash
curl http://localhost:8080/health
# {"status":"healthy","service":"bloombox"}
```

### 5. Start AgentOB Services

```bash
cd /path/to/agentOB
docker compose up -d rabbitmq redis intake
```

### 6. Run Dedup Worker

**Option A: Docker (recommended)**
```bash
docker compose up -d dedup_worker
docker compose logs -f dedup_worker
```

**Option B: Local development**
```bash
cd dedup_worker
python -m dedup_worker.worker
```

## Configuration

Environment variables (see [config.py](config.py)):

| Variable | Default | Description |
|----------|---------|-------------|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection |
| `BLOOMBOX_GRPC_HOST` | `localhost` | BloomBox gRPC host |
| `BLOOMBOX_GRPC_PORT` | `50051` | BloomBox gRPC port |
| `BLOOMBOX_HTTP_URL` | `http://localhost:8080` | BloomBox HTTP for health checks |
| `BLOOM_EXPECTED_ITEMS` | `1000000` | Expected daily span volume |
| `BLOOM_FALSE_POS_RATE` | `0.01` | 1% false positive rate |
| `DEDUP_PREFETCH_COUNT` | `100` | RabbitMQ prefetch count |
| `BLOOMBOX_HEALTHCHECK_INTERVAL` | `30` | Health check interval (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |

## Testing

### Test 1: With BloomBox Running

```bash
# Start BloomBox
cd /path/to/bloombox && docker compose up -d

# Send test spans
curl -X POST http://localhost:8000/v1/spans \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-001",
    "run_id": "run-001",
    "agent_name": "test-agent",
    "project_id": "test-project",
    "span_type": "llm_call",
    "name": "Test span",
    "started_at": "2024-03-30T10:00:00Z",
    "completed_at": "2024-03-30T10:00:01Z",
    "is_final": false
  }'

# Send duplicate
curl -X POST http://localhost:8000/v1/spans \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-001",
    "run_id": "run-001",
    "agent_name": "test-agent",
    "project_id": "test-project",
    "span_type": "llm_call",
    "name": "Duplicate span",
    "started_at": "2024-03-30T10:00:00Z",
    "completed_at": "2024-03-30T10:00:01Z",
    "is_final": false
  }'
```

**Expected logs:**
```
✓ BloomBox connected - deduplication ENABLED
Processing span test-001 (run: run-001)
✓ Published span test-001 to span_processing
⊗ Duplicate detected: test-001 (run: run-001) - DROPPED
```

### Test 2: Without BloomBox (Graceful Degradation)

```bash
# Stop BloomBox
cd /path/to/bloombox && docker compose down

# Send test spans (same as above)
```

**Expected logs:**
```
⚠ BloomBox unavailable - deduplication DISABLED (pass-through mode)
BloomBox unavailable - processing span test-001 without dedup check
✓ Published span test-001 to span_processing
BloomBox unavailable - processing span test-001 without dedup check
✓ Published span test-001 to span_processing
```

Both spans should be published (no deduplication).

## Monitoring

### View Metrics

```bash
docker compose logs dedup_worker | grep "📊 Metrics"
```

Example output:
```
📊 Metrics: consumed=1000, duplicates=47 (4.70%), published=953, bloombox_unavailable=0
```

### Check RabbitMQ Queues

```bash
# Management UI
open http://localhost:15672

# CLI
docker exec rabbitmq rabbitmqctl list_queues name messages
```

## Troubleshooting

### gRPC Stubs Not Found

```
ImportError: cannot import name 'BloomServiceStub' from 'dedup_worker.bloom_pb2_grpc'
```

**Fix**: Generate gRPC stubs
```bash
cd dedup_worker && ./generate_grpc.sh
```

### BloomBox Connection Failed

```
Failed to connect to BloomBox: <urlopen error [Errno 111] Connection refused>
```

**Fix**: Start BloomBox
```bash
cd /path/to/bloombox && docker compose up -d
curl http://localhost:8080/health
```

### Worker Not Consuming Messages

**Check RabbitMQ connection**:
```bash
docker compose logs dedup_worker | grep "Connected to RabbitMQ"
```

**Check queue exists**:
```bash
docker exec rabbitmq rabbitmqctl list_queues | grep span_intake
```

If missing, restart intake service to create queues:
```bash
docker compose restart intake
```

## Architecture Notes

### Why Graceful Degradation?

BloomBox is a performance optimization, not a critical component:
- **With BloomBox**: Filters duplicates, reduces downstream processing load
- **Without BloomBox**: All spans processed, system continues functioning

This design ensures system resilience even if BloomBox crashes or is under maintenance.

### Why gRPC over HTTP?

- **Performance**: ~10x faster than HTTP REST for small payloads
- **Efficiency**: Binary protocol, no JSON parsing overhead
- **Type Safety**: Protocol buffers provide schema validation
- **Streaming**: Future support for bidirectional streaming if needed

### Memory Considerations

BloomBox filter memory usage:
- 1M spans @ 1% FP rate: ~1.2 MB
- 10M spans @ 0.1% FP rate: ~17.5 MB

Recommendation: Restart BloomBox filter daily to prevent unbounded growth.

## Next Steps

After dedup worker is running:
1. **Phase 3**: Refactor Analyzer Worker to consume from `span_processing` queue
2. **Phase 4**: Implement WebSocket service for real-time updates
3. **Phase 5**: Update database schema for incremental span storage
4. **Phase 6**: Frontend WebSocket integration

## Related Services

- [Intake Service](../intake/) - Accepts spans from agents
- [BloomBox](https://github.com/yourusername/bloombox) - Bloom filter service (Go)
- [Analyzer Worker](../ai_service/) - Processes spans and detects anomalies (TODO: refactor)
