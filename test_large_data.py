#!/usr/bin/env python3
"""
Test conditional I/O data stripping in analyzer.
Creates spans with small and large data to verify the logic.
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_small_data():
    """Test with small I/O data - should be included in WebSocket"""
    print("\n=== Test 1: Small Data (should NOT be excluded) ===")

    payload = {
        "span_id": "test-small-v2",
        "run_id": "test-strip-v2",
        "agent_name": "test-agent",
        "project_id": "test",
        "span_type": "llm_call",
        "name": "Small data test",
        "started_at": "2024-04-05T10:00:00Z",
        "completed_at": "2024-04-05T10:00:01Z",
        "is_final": False,
        "input_data": {
            "prompt": "Short prompt text",
            "context": ["doc1", "doc2"]
        },
        "output_data": {
            "result": "Short result",
            "confidence": 0.95
        }
    }

    response = requests.post(f"{BASE_URL}/v1/spans", json=payload)
    print(f"Response: {response.json()}")

    # Calculate size
    input_size = len(json.dumps(payload["input_data"]).encode('utf-8'))
    output_size = len(json.dumps(payload["output_data"]).encode('utf-8'))
    total = input_size + output_size
    print(f"Total I/O size: {total} bytes (input: {input_size}, output: {output_size})")
    print(f"Expected: NOT excluded (< 10KB)")

def test_large_data():
    """Test with large I/O data - should be excluded from WebSocket"""
    print("\n=== Test 2: Large Data (should be excluded) ===")

    # Create large prompt (8KB) and large result (4KB) = 12KB total
    large_prompt = "x" * 8000
    large_context = ["document " + "y" * 100 for _ in range(20)]  # Add more bulk
    large_result = "z" * 4000

    payload = {
        "span_id": "test-large-v2",
        "run_id": "test-strip-v2",
        "agent_name": "test-agent",
        "project_id": "test",
        "span_type": "llm_call",
        "name": "Large data test",
        "started_at": "2024-04-05T10:00:02Z",
        "completed_at": "2024-04-05T10:00:03Z",
        "is_final": True,
        "input_data": {
            "prompt": large_prompt,
            "context": large_context
        },
        "output_data": {
            "result": large_result,
            "metadata": {"tokens": 1500}
        }
    }

    response = requests.post(f"{BASE_URL}/v1/spans", json=payload)
    print(f"Response: {response.json()}")

    # Calculate size
    input_size = len(json.dumps(payload["input_data"]).encode('utf-8'))
    output_size = len(json.dumps(payload["output_data"]).encode('utf-8'))
    total = input_size + output_size
    print(f"Total I/O size: {total} bytes (input: {input_size}, output: {output_size})")
    print(f"Expected: EXCLUDED (> 10KB)")

if __name__ == "__main__":
    print("Testing Conditional I/O Data Stripping")
    print("=" * 50)

    test_small_data()
    test_large_data()

    print("\n" + "=" * 50)
    print("Check analyzer logs for 'Excluded I/O data' messages:")
    print("docker compose logs analyzer | grep Excluded")
    print("\nCheck database to verify full data is stored:")
    print("docker exec -i postgres psql -U agentob_user -d agentob_db -c \"SELECT span_id, length(input_data::text) + length(output_data::text) as total_bytes FROM spans WHERE run_id='test-strip-v2';\"")
