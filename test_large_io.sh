#!/bin/bash

# Test with large I/O data (>10KB combined)
# This should trigger the conditional stripping in analyzer

# Create a large input (8KB) + large output (3KB) = 11KB total

curl -X POST http://localhost:8000/v1/spans \
  -H "Content-Type: application/json" \
  -d "{
    \"span_id\": \"test-large-io\",
    \"run_id\": \"test-conditional-strip\",
    \"agent_name\": \"test-agent\",
    \"project_id\": \"test\",
    \"span_type\": \"llm_call\",
    \"name\": \"Large I/O test\",
    \"started_at\": \"2024-04-05T10:00:02Z\",
    \"completed_at\": \"2024-04-05T10:00:03Z\",
    \"is_final\": true,
    \"input_data\": {
      \"prompt\": \"$(head -c 8000 /dev/zero | tr '\\0' 'x')\"
    },
    \"output_data\": {
      \"result\": \"$(head -c 3000 /dev/zero | tr '\\0' 'y')\"
    }
  }"
