# compression/__init__.py

from typing import Optional
from .models import (
    FileChange, CompressionResult, CompressionConfig,
    ScoredFile, InclusionTier
)
from .smart_strategy import SmartCompressionStrategy
from .utils import TokenCounter, LanguageDetector, FileClassifier
from .base import CompressionStrategy


class CompressionFactory:
    """Factory for creating compression strategies"""
    
    STRATEGIES = {
        'smart': SmartCompressionStrategy,
    }
    
    @classmethod
    def create(cls, strategy_name: str, config: Optional[CompressionConfig] = None) -> CompressionStrategy:
        """Create a compression strategy by name"""
        if config is None:
            config = CompressionConfig()
        
        strategy_class = cls.STRATEGIES.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(cls.STRATEGIES.keys())}")
        
        return strategy_class(config)


__all__ = [
    'FileChange',
    'CompressionResult',
    'CompressionConfig',
    'ScoredFile',
    'InclusionTier',
    'SmartCompressionStrategy',
    'CompressionFactory',
    'TokenCounter',
    'LanguageDetector',
    'FileClassifier',
]