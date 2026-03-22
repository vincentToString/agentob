from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class InclusionTier(Enum):
    """How much of a file to include"""
    FULL = "full"           # Complete diff --> Top Priority Files
    SUMMARY = "summary"     # Stats + brief description --> Low Priority Files
    LISTED = "listed"       # Filename only --> Non related Files


@dataclass
class FileChange:
    """Represents a changed file in a PR"""
    path: str
    status: str  # 'added', 'modified', 'removed', 'renamed'
    additions: int
    deletions: int
    changes: int
    patch: str  # Git diff patch
    
    # Computed fields
    language: str = ""
    tokens: int = 0
    is_binary: bool = False
    
    @property
    def is_deleted(self) -> bool:
        return self.status == 'removed'
    
    @property
    def is_added(self) -> bool:
        return self.status == 'added'
    
    @property
    def is_modified(self) -> bool:
        return self.status == 'modified'


@dataclass
class ScoredFile:
    """File with importance scoring"""
    file: FileChange
    importance_score: float  # 0-100
    
    # Score breakdown (for debugging)
    critical_bonus: float = 0
    language_bonus: float = 0
    size_bonus: float = 0
    type_penalty: float = 0
    
    # Classification
    is_critical: bool = False
    is_test: bool = False
    is_doc: bool = False
    
    # Inclusion decision
    inclusion_tier: Optional[InclusionTier] = None
    
    def __lt__(self, other):
        """For sorting by importance"""
        return self.importance_score < other.importance_score


@dataclass
class CompressionResult:
    """Result of PR compression"""
    # Original data
    original_files: List[FileChange]
    original_tokens: int
    
    # Compressed data
    included_full: List[ScoredFile]
    included_summary: List[ScoredFile]
    included_listed: List[ScoredFile]
    
    # Metadata
    compressed_tokens: int
    compression_ratio: float
    strategy_used: str
    
    # Statistics
    stats: Dict[str, any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "strategy": self.strategy_used,
            "stats": {
                "total_files": len(self.original_files),
                "included_full": len(self.included_full),
                "included_summary": len(self.included_summary),
                "included_listed": len(self.included_listed),
                "original_tokens": self.original_tokens,
                "compressed_tokens": self.compressed_tokens,
                "compression_ratio": self.compression_ratio,
                **self.stats
            },
            "files": {
                "full": [self._file_to_dict(sf, include_patch=True) for sf in self.included_full],
                "summary": [self._file_to_dict(sf, include_patch=False) for sf in self.included_summary],
                "listed": [sf.file.path for sf in self.included_listed]
            }
        }
    
    def _file_to_dict(self, scored_file: ScoredFile, include_patch: bool) -> Dict:
        """Convert scored file to dict"""
        f = scored_file.file
        result = {
            "path": f.path,
            "status": f.status,
            "additions": f.additions,
            "deletions": f.deletions,
            "language": f.language,
            "importance_score": round(scored_file.importance_score, 2),
            "is_critical": scored_file.is_critical
        }
        
        if include_patch:
            result["patch"] = f.patch
        
        return result


@dataclass
class CompressionConfig:
    """Configuration for compression logic"""
    max_tokens: int = 50000
    
    # Preservation settings
    preserve_critical_deletions: bool = True
    preserve_context_lines: int = 3
    
    # Token allocation
    full_diff_token_budget: float = 0.75  # 75% of tokens for full diffs
    summary_token_budget: float = 0.20    # 20% for summaries
    listed_token_budget: float = 0.05     # 5% for file lists
    
    # Scoring weights
    critical_pattern_bonus: float = 50.0
    language_bonus_multiplier: float = 0.3
    additions_weight: float = 0.1
    deletions_weight: float = 0.05
    test_file_penalty: float = 0.7
    doc_file_penalty: float = 0.5