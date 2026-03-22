from abc import ABC, abstractmethod
from typing import List
from .models import FileChange, CompressionResult, CompressionConfig


class CompressionStrategy(ABC):
    """Abstract base class for compression strategies"""
    
    def __init__(self, config: CompressionConfig):
        self.config = config
    
    @abstractmethod
    async def compress(self, repo_name:str, pr_number: int,head_sha: str, files: List[FileChange]) -> CompressionResult:
        """Compress PR files according to strategy"""
        pass
