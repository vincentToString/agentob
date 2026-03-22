"""
Real API integration tests - COSTS MONEY!
These tests use actual AWS Bedrock API calls and will incur charges.
Only run when you want to validate the real integration.

To run only these tests:
    pytest tests/test_real_api.py -v -s

To skip these tests in normal runs, they are marked with @pytest.mark.expensive
"""
import pytest
from pathlib import Path
import json

from ai_service.config import Config
from ai_service.worker import call_bedrock, load_prompt_template, render_prompt, parse_diff


@pytest.mark.expensive
class TestRealAPIIntegration:
    """
    Tests that require real AWS API calls - THESE COST MONEY!
    Only run when you need to validate the actual integration.
    """
    
    def test_real_bedrock_with_prompt_template(self):
        """
        Test real AWS Bedrock API call using the actual prompt template
        WARNING: This will make a real API call and cost money!
        """
        
        # Check if we have real AWS credentials configured
        if not Config.AWS_ACCESS_KEY or not Config.AWS_SECRET_KEY:
            pytest.skip("AWS credentials not configured - skipping real API test")
        
        if not Config.MODEL_ID or not Config.MODEL_ID.startswith("arn:aws:bedrock:"):
            pytest.skip("AWS Bedrock model not configured - skipping real API test")
        
        # Load the actual prompt template
        prompt_path = Path(__file__).parent.parent / "prompt.md"
        if not prompt_path.exists():
            pytest.skip(f"Prompt template not found at {prompt_path} - skipping test")
        
        prompt_template = load_prompt_template(prompt_path)
        
        # Create sample PR data for testing
        sample_pr_data = {
            "repo_name": "test/sample-repo",
            "pr_number": 42,
            "pr_title": "Add new feature for user authentication", 
            "pr_author": "developer123",
            "pr_body": "This PR adds JWT-based authentication to the application with proper error handling and tests.",
            "pr_url": "https://github.com/test/sample-repo/pull/42"
        }
        
        # Sample diff content for testing
        sample_diff = """diff --git a/auth.py b/auth.py
index 1234567..abcdefg 100644
--- a/auth.py
+++ b/auth.py
@@ -1,5 +1,15 @@
+import jwt
+from datetime import datetime, timedelta
+
 def authenticate_user(username, password):
-    # TODO: Implement authentication
-    return False
+    if verify_credentials(username, password):
+        token = jwt.encode({
+            'user': username,
+            'exp': datetime.utcnow() + timedelta(hours=24)
+        }, SECRET_KEY, algorithm='HS256')
+        return token
+    return None
+
+def verify_credentials(username, password):
+    # Database lookup logic here
+    return username == "admin" and password == "secret123"
"""
        
        # Parse the diff (simulate what happens in the worker)
        files, snippets = parse_diff(sample_diff, max_files=3, max_lines_per_file=120)
        
        # Create a mock event object
        class MockEvent:
            def __init__(self, data):
                for key, value in data.items():
                    setattr(self, key, value)
        
        mock_event = MockEvent(sample_pr_data)
        
        # Render the prompt with real data
        rendered_prompt = render_prompt(prompt_template, mock_event, files, snippets)
        
        print(f"\n{'='*60}")
        print("REAL API TEST - AWS BEDROCK INTEGRATION")
        print(f"{'='*60}")
        print(f"Model: {Config.MODEL_ID}")
        print(f"Region: {Config.AWS_DEFAULT_REGION}")
        print(f"Access Key: {Config.AWS_ACCESS_KEY[:10]}...")
        print(f"{'='*60}")
        print("RENDERED PROMPT:")
        print(f"{'='*60}")
        print(rendered_prompt)
        print(f"{'='*60}")
        
        # Make the real API call
        print("Making REAL AWS Bedrock API call...")
        print("WARNING: This will cost money!")
        
        try:
            result = call_bedrock(
                prompt_text=rendered_prompt,
                model_id=Config.MODEL_ID,
                aws_access_key=Config.AWS_ACCESS_KEY,
                aws_secret_key=Config.AWS_SECRET_KEY,
                aws_region=Config.AWS_DEFAULT_REGION,
                timeout_s=Config.LLM_TIMEOUT
            )
            
            print(f"{'='*60}")
            print("BEDROCK RESPONSE RECEIVED!")
            print(f"{'='*60}")
            print("Raw Response:")
            print(json.dumps(result, indent=2))
            print(f"{'='*60}")
            
            # Validate the response structure
            assert isinstance(result, dict), "Response should be a dictionary"
            assert "summary" in result, "Response should contain 'summary' field"
            assert "findings" in result, "Response should contain 'findings' field"
            
            # Validate response content length
            summary = result.get("summary", "")
            print(f"Summary length: {len(summary)} characters")
            print(f"Summary: {summary}")
            print(f"{'='*60}")
            
            # Check that we got a substantial response (> 200 characters)
            assert len(summary) > 200, f"Summary should be > 200 characters, got {len(summary)}"
            
            # Validate findings structure
            findings = result.get("findings", [])
            print(f"Number of findings: {len(findings)}")
            
            if findings:
                print("Sample finding:")
                print(json.dumps(findings[0], indent=2))
            
            print(f"{'='*60}")
            print("REAL API TEST COMPLETED SUCCESSFULLY!")
            print(f"Cost incurred: Real AWS Bedrock API call made")
            print(f"{'='*60}")
            
            # Assert test passed
            assert True, "Real API integration test completed successfully"
            
        except Exception as e:
            print(f"{'='*60}")
            print(f"REAL API TEST FAILED!")
            print(f"Error: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            print(f"{'='*60}")
            raise
    
    def test_prompt_template_exists(self):
        """Test that the prompt template file exists and is readable"""
        
        prompt_path = Path(__file__).parent.parent / "prompt.md"
        
        # Check file exists
        assert prompt_path.exists(), f"Prompt template not found at {prompt_path}"
        
        # Check file is readable and not empty
        content = prompt_path.read_text(encoding="utf-8")
        assert len(content) > 100, "Prompt template should have substantial content"
        
        # Check for expected template variables
        expected_vars = ["{{repo_name}}", "{{pr_number}}", "{{pr_title}}", "{{pr_author}}", "{{pr_body}}", "{{files_table}}", "{{snippets}}"]
        
        for var in expected_vars:
            assert var in content, f"Prompt template should contain variable {var}"
        
        print(f"\nPrompt template validation passed")
        print(f"Template length: {len(content)} characters")
        print(f"Variables found: {expected_vars}")
    
    def test_config_ready_for_real_api(self):
        """Test that configuration is properly set up for real API calls"""
        
        # Check AWS credentials
        assert Config.AWS_ACCESS_KEY, "AWS_ACCESS_KEY must be configured"
        assert Config.AWS_SECRET_KEY, "AWS_SECRET_KEY must be configured"
        assert Config.AWS_DEFAULT_REGION, "AWS_DEFAULT_REGION must be configured"
        assert Config.MODEL_ID, "MODEL_ID must be configured"
        
        # Validate AWS credential format
        assert Config.AWS_ACCESS_KEY.startswith("AKIA"), "AWS_ACCESS_KEY should start with 'AKIA'"
        assert len(Config.AWS_ACCESS_KEY) == 20, "AWS_ACCESS_KEY should be 20 characters"
        assert len(Config.AWS_SECRET_KEY) >= 30, "AWS_SECRET_KEY should be at least 30 characters"
        
        # Validate model ID is inference profile ARN
        assert Config.MODEL_ID.startswith("arn:aws:bedrock:"), "MODEL_ID should be a Bedrock ARN"
        assert "inference-profile" in Config.MODEL_ID, "MODEL_ID should be an inference profile ARN"
        
        # Validate timeout settings
        assert isinstance(Config.LLM_TIMEOUT, int), "LLM_TIMEOUT should be an integer"
        assert Config.LLM_TIMEOUT > 0, "LLM_TIMEOUT should be positive"
        
        print(f"\nConfiguration validation passed")
        print(f"AWS Access Key: {Config.AWS_ACCESS_KEY[:10]}...")
        print(f"AWS Region: {Config.AWS_DEFAULT_REGION}")
        print(f"Model ID: {Config.MODEL_ID}")
        print(f"Timeout: {Config.LLM_TIMEOUT}s")


# Add custom pytest marker for expensive tests
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "expensive: mark test as expensive (real API calls that cost money)"
    )