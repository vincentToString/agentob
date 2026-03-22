"""
Test configuration loading and environment variables
Tests that the Config class correctly loads settings from environment
"""
import pytest
import os
from unittest.mock import patch


class TestConfig:
    
    def test_config_loads_aws_credentials(self):
        """Test that AWS credentials are loaded from environment"""
        
        test_env = {
            "AWS_ACCESS_KEY": "AKIA123456789",
            "AWS_SECRET_KEY": "test_secret_key_12345",
            "AWS_DEFAULT_REGION": "us-east-2",
            "MODEL_ID": "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0"
        }
        
        with patch.dict(os.environ, test_env):
            # Reload config after setting environment
            import importlib
            from ai_service import config
            importlib.reload(config)
            
            assert config.Config.AWS_ACCESS_KEY == "AKIA123456789"
            assert config.Config.AWS_SECRET_KEY == "test_secret_key_12345"
            assert config.Config.AWS_DEFAULT_REGION == "us-east-2"
            assert config.Config.MODEL_ID == "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0"
    
    def test_config_loads_service_settings(self):
        """Test that service settings are loaded correctly"""
        
        test_env = {
            "LLM_TIMEOUT": "45",
            "MAX_FILES_FOR_SNIPPETS": "5",
            "MAX_LINES_PER_FILE": "200",
            "RABBITMQ_URL": "amqp://test:test@localhost/"
        }
        
        with patch.dict(os.environ, test_env):
            import importlib
            from ai_service import config
            importlib.reload(config)
            
            assert config.Config.LLM_TIMEOUT == 45
            assert config.Config.MAX_FILES == 5
            assert config.Config.MAX_LINES == 200
            assert config.Config.RABBITMQ_URL == "amqp://test:test@localhost/"
            
            # Verify types are correct
            assert isinstance(config.Config.LLM_TIMEOUT, int)
            assert isinstance(config.Config.MAX_FILES, int)
            assert isinstance(config.Config.MAX_LINES, int)
    
    def test_config_has_required_attributes(self):
        """Test that Config class has all required attributes"""
        
        from ai_service.config import Config
        
        # Test that all required attributes exist
        assert hasattr(Config, 'AWS_ACCESS_KEY')
        assert hasattr(Config, 'AWS_SECRET_KEY')
        assert hasattr(Config, 'AWS_DEFAULT_REGION')
        assert hasattr(Config, 'MODEL_ID')
        assert hasattr(Config, 'LLM_TIMEOUT')
        assert hasattr(Config, 'MAX_FILES')
        assert hasattr(Config, 'MAX_LINES')
        assert hasattr(Config, 'RABBITMQ_URL')
    
    def test_config_handles_empty_strings(self):
        """Test that empty string environment variables are handled correctly"""
        
        test_env = {
            "AWS_ACCESS_KEY": "",
            "AWS_SECRET_KEY": "",
            "MODEL_ID": "",
            "AWS_DEFAULT_REGION": "",
            "LLM_TIMEOUT": "",
            "MAX_FILES_FOR_SNIPPETS": "",
            "MAX_LINES_PER_FILE": ""
        }
        
        with patch.dict(os.environ, test_env):
            import importlib
            from ai_service import config
            importlib.reload(config)
            
            # String values should remain empty
            assert config.Config.AWS_ACCESS_KEY == ""
            assert config.Config.AWS_SECRET_KEY == ""
            assert config.Config.MODEL_ID == ""
            assert config.Config.AWS_DEFAULT_REGION == ""
            
            # Integer values should fall back to defaults when empty
            assert config.Config.LLM_TIMEOUT == 20
            assert config.Config.MAX_FILES == 3
            assert config.Config.MAX_LINES == 120
    
    def test_config_invalid_integer_values(self):
        """Test handling of invalid integer environment variables"""
        
        test_env = {
            "LLM_TIMEOUT": "not_a_number",
            "MAX_FILES_FOR_SNIPPETS": "invalid",
            "MAX_LINES_PER_FILE": "also_invalid"
        }
        
        with patch.dict(os.environ, test_env):
            # This should raise ValueError when trying to convert to int
            with pytest.raises(ValueError):
                import importlib
                from ai_service import config
                importlib.reload(config)
    
    def test_config_required_for_bedrock(self):
        """Test that all required configuration for Bedrock is available"""
        
        test_env = {
            "AWS_ACCESS_KEY": "AKIA123456789",
            "AWS_SECRET_KEY": "test_secret_key",
            "AWS_DEFAULT_REGION": "us-east-2",
            "MODEL_ID": "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0"
        }
        
        with patch.dict(os.environ, test_env):
            import importlib
            from ai_service import config
            importlib.reload(config)
            
            # Verify all required Bedrock configuration is present
            assert config.Config.AWS_ACCESS_KEY is not None
            assert config.Config.AWS_SECRET_KEY is not None
            assert config.Config.AWS_DEFAULT_REGION is not None
            assert config.Config.MODEL_ID is not None
            
            # Verify the model ID is an inference profile ARN
            assert config.Config.MODEL_ID.startswith("arn:aws:bedrock:")
            assert "inference-profile" in config.Config.MODEL_ID