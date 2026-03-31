#!/bin/bash

# Test script for Intake Service - Streaming Span Ingestion
# Usage: ./test_intake.sh

BASE_URL="http://localhost:8000"

echo "=========================================="
echo "AgentOB Intake Service - Test Script"
echo "=========================================="
echo ""

# Test 1: Health check
echo "Test 1: Health Check"
curl -X GET "${BASE_URL}/v1/spans/health"
echo -e "\n"

# Test 2: Valid span ingestion (first span)
echo "Test 2: Valid Span Ingestion (First Span)"
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "550e8400-e29b-41d4-a716-446655440001",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_name": "test-agent-v1",
    "project_id": "test-project-2024",
    "span_type": "llm_call",
    "name": "Initial query expansion",
    "started_at": "2024-03-30T10:00:00Z",
    "completed_at": "2024-03-30T10:00:02.500Z",
    "is_final": false,
    "model_id": "gpt-4",
    "tokens_input": 150,
    "tokens_output": 300
  }'
echo -e "\n"

# Test 3: Second span (tool use)
echo "Test 3: Tool Use Span"
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "550e8400-e29b-41d4-a716-446655440002",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_name": "test-agent-v1",
    "project_id": "test-project-2024",
    "span_type": "tool_use",
    "name": "Vector database search",
    "started_at": "2024-03-30T10:00:03Z",
    "completed_at": "2024-03-30T10:00:03.200Z",
    "is_final": false,
    "tool_name": "pinecone_search",
    "tool_status": "success"
  }'
echo -e "\n"

# Test 4: Final span
echo "Test 4: Final Span (Run Complete)"
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "550e8400-e29b-41d4-a716-446655440003",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_name": "test-agent-v1",
    "project_id": "test-project-2024",
    "span_type": "llm_call",
    "name": "Final synthesis",
    "started_at": "2024-03-30T10:00:04Z",
    "completed_at": "2024-03-30T10:00:06Z",
    "is_final": true,
    "model_id": "gpt-4",
    "tokens_input": 500,
    "tokens_output": 800,
    "cost_usd": 0.045
  }'
echo -e "\n"

# Test 5: Missing required field (should fail)
echo "Test 5: Missing Required Field (Expected: 422 Error)"
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-001",
    "run_id": "test-run-001",
    "span_type": "llm_call"
  }'
echo -e "\n"

# Test 6: Invalid span type (should fail)
echo "Test 6: Invalid Span Type (Expected: 400 Error)"
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-002",
    "run_id": "test-run-002",
    "agent_name": "test",
    "project_id": "test",
    "span_type": "invalid_type",
    "name": "test",
    "started_at": "2024-03-30T10:00:00Z",
    "completed_at": "2024-03-30T10:00:02Z",
    "is_final": false
  }'
echo -e "\n"

# Test 7: Invalid timestamp (should fail)
echo "Test 7: Invalid Timestamp (Expected: 400 Error)"
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-003",
    "run_id": "test-run-003",
    "agent_name": "test",
    "project_id": "test",
    "span_type": "llm_call",
    "name": "test",
    "started_at": "invalid-timestamp",
    "completed_at": "also-invalid",
    "is_final": false
  }'
echo -e "\n"

# Test 8: Large input/output data (should trigger Redis storage)
echo "Test 8: Large I/O Data (Should Store in Redis)"
# Create large strings (8KB input + 3KB output = 11KB > 10KB threshold)
LARGE_INPUT=$(python3 -c "print('A' * 8000)")
LARGE_OUTPUT=$(python3 -c "print('B' * 3000)")
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d "{
    \"span_id\": \"large-test-001\",
    \"run_id\": \"large-run-001\",
    \"agent_name\": \"test-agent\",
    \"project_id\": \"test-project\",
    \"span_type\": \"llm_call\",
    \"name\": \"Large I/O test\",
    \"started_at\": \"2024-03-30T10:00:00Z\",
    \"completed_at\": \"2024-03-30T10:00:02Z\",
    \"is_final\": false,
    \"input_data\": {
      \"prompt\": \"${LARGE_INPUT}\"
    },
    \"output_data\": {
      \"response\": \"${LARGE_OUTPUT}\"
    }
  }"
echo -e "\n"
echo "→ Check logs for: 'Stored large I/O data in Redis (11000 bytes...)'"
echo -e "\n"

# Test 9: Old batch endpoint (should return 410)
echo "Test 9: Deprecated Batch Endpoint (Expected: 410 Gone)"
curl -X POST "${BASE_URL}/v1/traces" \
  -H "Content-Type: application/json" \
  -d '{}'
echo -e "\n"

echo "=========================================="
echo "✓ Test suite complete!"
echo ""
echo "Next steps:"
echo "1. Check logs: docker logs intake"
echo "2. Check RabbitMQ UI: http://localhost:15672"
echo "   - Queue 'span_intake' should have 3 messages"
echo "   - Username: admin, Password: password"
echo "=========================================="
