# Test script for Intake Service - Streaming Span Ingestion (PowerShell)
# Usage: .\test_intake.ps1

$BaseUrl = "http://localhost:8000"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "AgentOB Intake Service - Test Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Health check
Write-Host "Test 1: Health Check" -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans/health" -Method Get | ConvertTo-Json
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Write-Host ""

# Test 2: Valid span ingestion (first span)
Write-Host "Test 2: Valid Span Ingestion (First Span)" -ForegroundColor Yellow
$span1 = @{
    span_id = "550e8400-e29b-41d4-a716-446655440001"
    run_id = "550e8400-e29b-41d4-a716-446655440000"
    agent_name = "test-agent-v1"
    project_id = "test-project-2024"
    span_type = "llm_call"
    name = "Initial query expansion"
    started_at = "2024-03-30T10:00:00Z"
    completed_at = "2024-03-30T10:00:02.500Z"
    is_final = $false
    model_id = "gpt-4"
    tokens_input = 150
    tokens_output = 300
} | ConvertTo-Json

try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $span1 -ContentType "application/json" | ConvertTo-Json
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Write-Host ""

# Test 3: Second span (tool use)
Write-Host "Test 3: Tool Use Span" -ForegroundColor Yellow
$span2 = @{
    span_id = "550e8400-e29b-41d4-a716-446655440002"
    run_id = "550e8400-e29b-41d4-a716-446655440000"
    agent_name = "test-agent-v1"
    project_id = "test-project-2024"
    span_type = "tool_use"
    name = "Vector database search"
    started_at = "2024-03-30T10:00:03Z"
    completed_at = "2024-03-30T10:00:03.200Z"
    is_final = $false
    tool_name = "pinecone_search"
    tool_status = "success"
} | ConvertTo-Json

try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $span2 -ContentType "application/json" | ConvertTo-Json
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Write-Host ""

# Test 4: Final span
Write-Host "Test 4: Final Span (Run Complete)" -ForegroundColor Yellow
$span3 = @{
    span_id = "550e8400-e29b-41d4-a716-446655440003"
    run_id = "550e8400-e29b-41d4-a716-446655440000"
    agent_name = "test-agent-v1"
    project_id = "test-project-2024"
    span_type = "llm_call"
    name = "Final synthesis"
    started_at = "2024-03-30T10:00:04Z"
    completed_at = "2024-03-30T10:00:06Z"
    is_final = $true
    model_id = "gpt-4"
    tokens_input = 500
    tokens_output = 800
    cost_usd = 0.045
} | ConvertTo-Json

try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $span3 -ContentType "application/json" | ConvertTo-Json
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Write-Host ""

# Test 5: Missing required field (should fail)
Write-Host "Test 5: Missing Required Field (Expected: 422 Error)" -ForegroundColor Yellow
$invalidSpan = @{
    span_id = "test-001"
    run_id = "test-run-001"
    span_type = "llm_call"
} | ConvertTo-Json

try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $invalidSpan -ContentType "application/json"
    Write-Host "Unexpected success!" -ForegroundColor Red
} catch {
    Write-Host "✓ Expected error received" -ForegroundColor Green
}
Write-Host ""

# Test 6: Invalid span type (should fail)
Write-Host "Test 6: Invalid Span Type (Expected: 400 Error)" -ForegroundColor Yellow
$invalidType = @{
    span_id = "test-002"
    run_id = "test-run-002"
    agent_name = "test"
    project_id = "test"
    span_type = "invalid_type"
    name = "test"
    started_at = "2024-03-30T10:00:00Z"
    completed_at = "2024-03-30T10:00:02Z"
    is_final = $false
} | ConvertTo-Json

try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $invalidType -ContentType "application/json"
    Write-Host "Unexpected success!" -ForegroundColor Red
} catch {
    Write-Host "✓ Expected error received" -ForegroundColor Green
}
Write-Host ""

# Test 7: Invalid timestamp (should fail)
Write-Host "Test 7: Invalid Timestamp (Expected: 400 Error)" -ForegroundColor Yellow
$invalidTimestamp = @{
    span_id = "test-003"
    run_id = "test-run-003"
    agent_name = "test"
    project_id = "test"
    span_type = "llm_call"
    name = "test"
    started_at = "invalid-timestamp"
    completed_at = "also-invalid"
    is_final = $false
} | ConvertTo-Json

try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $invalidTimestamp -ContentType "application/json"
    Write-Host "Unexpected success!" -ForegroundColor Red
} catch {
    Write-Host "✓ Expected error received" -ForegroundColor Green
}
Write-Host ""

# Test 8: Large input/output data (should trigger Redis storage)
Write-Host "Test 8: Large I/O Data (Should Store in Redis)" -ForegroundColor Yellow
Write-Host "Creating large data (8KB input + 3KB output = 11KB > 10KB threshold)..." -ForegroundColor Gray
$largeInput = "A" * 8000
$largeOutput = "B" * 3000
$largeSpan = @{
    span_id = "large-test-001"
    run_id = "large-run-001"
    agent_name = "test-agent"
    project_id = "test-project"
    span_type = "llm_call"
    name = "Large I/O test"
    started_at = "2024-03-30T10:00:00Z"
    completed_at = "2024-03-30T10:00:02Z"
    is_final = $false
    input_data = @{
        prompt = $largeInput
    }
    output_data = @{
        response = $largeOutput
    }
} | ConvertTo-Json -Depth 3

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/v1/spans" -Method Post -Body $largeSpan -ContentType "application/json"
    Write-Host "✓ Large span accepted: $($response.span_id)" -ForegroundColor Green
    Write-Host "→ Check logs for: 'Stored large I/O data in Redis (11000 bytes...)'" -ForegroundColor Cyan
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Write-Host ""

# Test 9: Old batch endpoint (should return 410)
Write-Host "Test 9: Deprecated Batch Endpoint (Expected: 410 Gone)" -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/traces" -Method Post -Body '{}' -ContentType "application/json"
    Write-Host "Unexpected success!" -ForegroundColor Red
} catch {
    Write-Host "✓ Expected error received (410 Gone)" -ForegroundColor Green
}
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✓ Test suite complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Check logs: docker logs intake"
Write-Host "2. Check RabbitMQ UI: http://localhost:15672"
Write-Host "   - Queue 'span_intake' should have 4 messages (3 normal + 1 large)"
Write-Host "   - Username: admin, Password: password"
Write-Host "3. Check Redis for large data:"
Write-Host "   docker exec -it redis redis-cli"
Write-Host "   > GET span_data:large-test-001:io_data"
Write-Host "==========================================" -ForegroundColor Cyan
