"""
Test AWS Bedrock service integration
Tests the core functionality of calling AWS Bedrock API
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from ai_service.worker import call_bedrock


class TestBedrockService:
    
    def test_successful_bedrock_call(self):
        """Test successful AWS Bedrock API call"""
        
        # Mock response from Bedrock
        mock_response = {
            "output": {
                "message": {
                    "content": [{
                        "text": json.dumps({
                            "summary": "Code looks good with minor suggestions",
                            "findings": [
                                {
                                    "type": "suggestion",
                                    "message": "Consider adding error handling",
                                    "file": "test.py",
                                    "line": 10,
                                    "suggestion": "Add try-catch block"
                                }
                            ]
                        })
                    }]
                }
            }
        }
        
        with patch('boto3.client') as mock_boto_client:
            # Setup mock client
            mock_client = MagicMock()
            mock_client.converse.return_value = mock_response
            mock_boto_client.return_value = mock_client
            
            # Test the call
            result = call_bedrock(
                prompt_text="Review this code: def test(): pass",
                model_id="arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0",
                aws_access_key="AKIA123456789",
                aws_secret_key="test_secret_key",
                aws_region="us-east-2",
                timeout_s=30
            )
            
            # Verify result structure
            assert "summary" in result
            assert "findings" in result
            assert result["summary"] == "Code looks good with minor suggestions"
            assert len(result["findings"]) == 1
            assert result["findings"][0]["type"] == "suggestion"
            
            # Verify boto3 was called correctly
            mock_boto_client.assert_called_once_with(
                'bedrock-runtime',
                region_name="us-east-2",
                aws_access_key_id="AKIA123456789",
                aws_secret_access_key="test_secret_key"
            )
            
            # Verify converse was called with correct parameters
            mock_client.converse.assert_called_once()
            call_args = mock_client.converse.call_args
            assert call_args[1]["modelId"] == "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0"
            
            # Verify message structure
            messages = call_args[1]["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            assert "Review this code: def test(): pass" in messages[0]["content"][0]["text"]
            
            # Verify inference config
            inference_config = call_args[1]["inferenceConfig"]
            assert inference_config["temperature"] == 0.2
            assert inference_config["maxTokens"] == 4000
            assert inference_config["topP"] == 0.9
    
    def test_access_denied_error(self):
        """Test handling of AWS access denied errors"""
        
        with patch('boto3.client') as mock_boto_client:
            mock_client = MagicMock()
            mock_client.converse.side_effect = ClientError(
                error_response={'Error': {'Code': 'AccessDeniedException', 'Message': 'Access denied'}},
                operation_name='Converse'
            )
            mock_boto_client.return_value = mock_client
            
            with pytest.raises(ClientError) as exc_info:
                call_bedrock(
                    prompt_text="test",
                    model_id="test-model",
                    aws_access_key="invalid_key",
                    aws_secret_key="invalid_secret",
                    aws_region="us-east-2",
                    timeout_s=30
                )
            
            assert exc_info.value.response['Error']['Code'] == 'AccessDeniedException'
    
    def test_invalid_model_error(self):
        """Test handling of invalid model ID errors"""
        
        with patch('boto3.client') as mock_boto_client:
            mock_client = MagicMock()
            mock_client.converse.side_effect = ClientError(
                error_response={'Error': {'Code': 'ValidationException', 'Message': 'Invalid model ID'}},
                operation_name='Converse'
            )
            mock_boto_client.return_value = mock_client
            
            with pytest.raises(ClientError) as exc_info:
                call_bedrock(
                    prompt_text="test",
                    model_id="invalid-model-id",
                    aws_access_key="AKIA123456789",
                    aws_secret_key="test_secret_key",
                    aws_region="us-east-2",
                    timeout_s=30
                )
            
            assert exc_info.value.response['Error']['Code'] == 'ValidationException'
    
    def test_non_json_response_handling(self):
        """Test handling of non-JSON responses from Bedrock"""
        
        # Mock response with plain text (not JSON)
        mock_response = {
            "output": {
                "message": {
                    "content": [{
                        "text": "This is a plain text response, not JSON"
                    }]
                }
            }
        }
        
        with patch('boto3.client') as mock_boto_client:
            mock_client = MagicMock()
            mock_client.converse.return_value = mock_response
            mock_boto_client.return_value = mock_client
            
            result = call_bedrock(
                prompt_text="test",
                model_id="test-model",
                aws_access_key="AKIA123456789",
                aws_secret_key="test_secret_key",
                aws_region="us-east-2",
                timeout_s=30
            )
            
            # Should wrap non-JSON response in basic structure
            assert "summary" in result
            assert "findings" in result
            assert result["summary"] == "This is a plain text response, not JSON"
            assert result["findings"] == []
    
    def test_empty_response_handling(self):
        """Test handling of empty or malformed responses"""
        
        # Mock response with empty content
        mock_response = {
            "output": {
                "message": {
                    "content": [{
                        "text": ""
                    }]
                }
            }
        }
        
        with patch('boto3.client') as mock_boto_client:
            mock_client = MagicMock()
            mock_client.converse.return_value = mock_response
            mock_boto_client.return_value = mock_client
            
            result = call_bedrock(
                prompt_text="test",
                model_id="test-model",
                aws_access_key="AKIA123456789",
                aws_secret_key="test_secret_key",
                aws_region="us-east-2",
                timeout_s=30
            )
            
            # Should handle empty response gracefully
            assert "summary" in result
            assert "findings" in result
            assert result["summary"] == ""
            assert result["findings"] == []