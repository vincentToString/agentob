#!/bin/bash
BASE_URL="http://localhost:8000"

echo "========================================="
echo "Test 1: First span (not final)"
echo "========================================="
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-span-1",
    "run_id": "test-run-1",
    "agent_name": "test-agent",
    "project_id": "test-project",
    "span_type": "llm_call",
    "name": "Planning search strategy",
    "started_at": "2024-04-03T10:00:00Z",
    "completed_at": "2024-04-03T10:00:03Z",
    "is_final": false,
    "model_id": "gpt-4o-mini",
    "tokens_input": 100,
    "tokens_output": 50
  }'

echo -e "\n\n========================================="
echo "Test 2: Second span (final)"
echo "========================================="
curl -X POST "${BASE_URL}/v1/spans" \
  -H "Content-Type: application/json" \
  -d '{
    "span_id": "test-span-2",
    "run_id": "test-run-1",
    "agent_name": "test-agent",
    "project_id": "test-project",
    "span_type": "tool_use",
    "name": "Search arxiv",
    "started_at": "2024-04-03T10:00:03Z",
    "completed_at": "2024-04-03T10:00:05Z",
    "is_final": true,
    "tool_name": "search_arxiv",
    "tool_status": "success"
  }'

echo -e "\n\nDone!"
