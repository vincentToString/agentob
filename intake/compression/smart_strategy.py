# compression/smart_strategy.py

from typing import List, Dict, Tuple
from .base import CompressionStrategy
from .models import (
    FileChange, CompressionResult, CompressionConfig,
    ScoredFile, InclusionTier
)
from .utils import (
    TokenCounter, LanguageDetector, FileClassifier, PatchProcessor
)

from .language_analyzer import PullRequestLanguageAnalyzer


class SmartCompressionStrategy(CompressionStrategy):
    """
    Enhanced compression strategy with criticality-based prioritization
    
    Key improvements over Qodo:
    1. Scores files by importance (not just size)
    2. Three-tier inclusion (full/summary/listed)
    3. Preserves critical context
    4. Semantic awareness of file types
    """
    
    def __init__(self, config: CompressionConfig):
        super().__init__(config)
        self.token_counter = TokenCounter()
        self.patch_processor = PatchProcessor()

        self.language_analyzer = PullRequestLanguageAnalyzer()

        self._language_scores: Dict[str, float] = {}
    
    async def compress(self, repo_name: str, pr_number: int, head_sha: str, files: List[FileChange]) -> CompressionResult:
        """Execute smart compression algorithm"""
        
        # 1. Filter and prepare files + Populate language priorities for this PR
        files = self._prepare_files(files)
        self._language_scores = await self.language_analyzer.analyze_repository(repo_name, pr_number, head_sha, files)
        
        # 2. Score all files by importance
        scored_files = self._score_files(files)
        
        # 3. Sort by importance (highest first)
        scored_files.sort(reverse=True)
        
        # 4. Allocate to tiers based on token budget
        allocation = self._allocate_to_tiers(scored_files)
        
        # 5. Calculate statistics
        original_tokens = sum(f.file.tokens for f in scored_files)
        compressed_tokens = self._calculate_compressed_tokens(allocation)
        
        return CompressionResult(
            original_files=files,
            original_tokens=original_tokens,
            included_full=allocation['full'],
            included_summary=allocation['summary'],
            included_listed=allocation['listed'],
            compressed_tokens=compressed_tokens,
            compression_ratio=compressed_tokens / original_tokens if original_tokens > 0 else 1.0,
            strategy_used="smart",
            stats=self._generate_stats(scored_files, allocation)
        )
    
    def _prepare_files(self, files: List[FileChange]) -> List[FileChange]:
        """Filter and enrich file data"""
        prepared = []
        
        for file in files:
            # Skip binary and generated files
            if file.is_binary or FileClassifier.is_generated(file.path):
                continue
            
            # Detect language
            file.language = LanguageDetector.detect(file.path)
            
            # Process patch based on file type
            if FileClassifier.is_critical(file.path):
                # Keep deletions in critical files
                file.patch = self.patch_processor.expand_context(file.patch)
            else:
                # Remove deletion-only hunks in non-critical files
                file.patch = self.patch_processor.remove_deletion_only_hunks(file.patch)
            
            # Count tokens
            file.tokens = self.token_counter.count(file.patch)
            
            prepared.append(file)
        
        return prepared
    
    def _score_files(self, files: List[FileChange]) -> List[ScoredFile]:
        """
        Score each file's importance for code review
        
        Scoring factors:
        - Critical patterns (auth, payment, etc.): +50
        - Language priority: +0 to +30
        - Size (additions): +0 to +20
        - File type (test/doc): penalty multiplier
        """
        scored = []
        
        for file in files:
            score = 0.0
            breakdown = {
                'critical_bonus': 0.0,
                'language_bonus': 0.0,
                'size_bonus': 0.0,
                'type_penalty': 0.0
            }
            
            # 1. Critical pattern match (highest priority)
            is_critical = FileClassifier.is_critical(file.path)
            if is_critical:
                critical_bonus = self.config.critical_pattern_bonus
                score += critical_bonus
                breakdown['critical_bonus'] = critical_bonus
            
            # 2. Language priority
            lang_priority = self._language_scores.get(file.language, 50)
            language_bonus = lang_priority * self.config.language_bonus_multiplier
            score += language_bonus
            breakdown['language_bonus'] = language_bonus
            
            # 3. Size-based scoring (additions weighted more)
            additions_score = min(file.additions * self.config.additions_weight, 20)
            deletions_score = min(file.deletions * self.config.deletions_weight, 10)
            size_bonus = additions_score + deletions_score
            score += size_bonus
            breakdown['size_bonus'] = size_bonus
            
            # 4. File type penalties
            is_test = FileClassifier.is_test(file.path)
            is_doc = FileClassifier.is_doc(file.path)
            
            if is_test:
                score *= self.config.test_file_penalty
                breakdown['type_penalty'] = -(1 - self.config.test_file_penalty)
            elif is_doc:
                score *= self.config.doc_file_penalty
                breakdown['type_penalty'] = -(1 - self.config.doc_file_penalty)
            
            # 5. Bonus for deleted files (if critical)
            if file.is_deleted and is_critical:
                score += 30  # Important to know what was deleted
            
            scored.append(ScoredFile(
                file=file,
                importance_score=score,
                critical_bonus=breakdown['critical_bonus'],
                language_bonus=breakdown['language_bonus'],
                size_bonus=breakdown['size_bonus'],
                type_penalty=breakdown['type_penalty'],
                is_critical=is_critical,
                is_test=is_test,
                is_doc=is_doc
            ))
        
        return scored
    
    def _allocate_to_tiers(self, scored_files: List[ScoredFile]) -> Dict[str, List[ScoredFile]]:
        """
        Allocate files to inclusion tiers based on importance and token budget
        
        Token budget allocation:
        - 75% for full diffs (high-importance files)
        - 20% for summaries (medium-importance files)
        - 5% for listings (low-importance files)
        """
        max_tokens = self.config.max_tokens
        
        # Calculate tier budgets
        full_budget = int(max_tokens * self.config.full_diff_token_budget)
        summary_budget = int(max_tokens * self.config.summary_token_budget)
        listed_budget = int(max_tokens * self.config.listed_token_budget)
        
        allocation = {
            'full': [],
            'summary': [],
            'listed': []
        }
        
        tokens_used = {'full': 0, 'summary': 0, 'listed': 0}
        
        # First pass: Allocate to full tier (highest priority)
        for sf in scored_files:
            if tokens_used['full'] + sf.file.tokens <= full_budget:
                sf.inclusion_tier = InclusionTier.FULL
                allocation['full'].append(sf)
                tokens_used['full'] += sf.file.tokens
            else:
                break  # Move to summary tier
        
        # Second pass: Allocate to summary tier
        remaining_files = [sf for sf in scored_files if sf.inclusion_tier is None]
        
        for sf in remaining_files:
            summary_tokens = self._estimate_summary_tokens(sf)
            if tokens_used['summary'] + summary_tokens <= summary_budget:
                sf.inclusion_tier = InclusionTier.SUMMARY
                allocation['summary'].append(sf)
                tokens_used['summary'] += summary_tokens
            else:
                break  # Move to listed tier
        
        # Third pass: Allocate to listed tier
        remaining_files = [sf for sf in scored_files if sf.inclusion_tier is None]
        
        for sf in remaining_files:
            listing_tokens = 20  # Rough estimate for filename + stats
            if tokens_used['listed'] + listing_tokens <= listed_budget:
                sf.inclusion_tier = InclusionTier.LISTED
                allocation['listed'].append(sf)
                tokens_used['listed'] += listing_tokens
            else:
                # Exceeds even listing budget, still add but note truncation
                sf.inclusion_tier = InclusionTier.LISTED
                allocation['listed'].append(sf)
        
        return allocation
    
    def _estimate_summary_tokens(self, scored_file: ScoredFile) -> int:
        """
        Estimate tokens needed for file summary
        
        Summary includes:
        - Filename and path
        - +X/-Y lines changed
        - Brief description (if critical)
        - Function signatures (if available)
        """
        base_tokens = 50  # Filename + stats
        
        if scored_file.is_critical:
            base_tokens += 100  # Add description for critical files
        
        # Add tokens for function signatures
        signatures = self.patch_processor.extract_function_signatures(
            scored_file.file.patch,
            scored_file.file.language
        )
        base_tokens += len(signatures) * 10  # ~10 tokens per signature
        
        return min(base_tokens, 200)  # Cap at 200 tokens per summary
    
    def _calculate_compressed_tokens(self, allocation: Dict[str, List[ScoredFile]]) -> int:
        """Calculate total tokens in compressed output"""
        total = 0
        
        # Full tier: actual patch tokens
        for sf in allocation['full']:
            total += sf.file.tokens
        
        # Summary tier: estimated summary tokens
        for sf in allocation['summary']:
            total += self._estimate_summary_tokens(sf)
        
        # Listed tier: filename only
        for sf in allocation['listed']:
            total += 20  # Rough estimate
        
        return total
    
    def _generate_stats(
        self,
        scored_files: List[ScoredFile],
        allocation: Dict[str, List[ScoredFile]]
    ) -> Dict:
        """Generate detailed statistics about compression"""
        
        return {
            # Overall stats
            "total_files": len(scored_files),
            "total_additions": sum(sf.file.additions for sf in scored_files),
            "total_deletions": sum(sf.file.deletions for sf in scored_files),
            
            # Tier breakdown
            "included_full": len(allocation['full']),
            "included_summary": len(allocation['summary']),
            "included_listed": len(allocation['listed']),
            
            # Critical file stats
            "critical_files": sum(1 for sf in scored_files if sf.is_critical),
            "critical_in_full": sum(1 for sf in allocation['full'] if sf.is_critical),
            "critical_in_summary": sum(1 for sf in allocation['summary'] if sf.is_critical),
            
            # Language breakdown
            "languages": self._count_by_language(scored_files),
            
            # Score distribution
            "avg_importance_score": sum(sf.importance_score for sf in scored_files) / len(scored_files),
            "max_importance_score": max(sf.importance_score for sf in scored_files),
            "min_importance_score": min(sf.importance_score for sf in scored_files),
        }
    
    def _count_by_language(self, scored_files: List[ScoredFile]) -> Dict[str, int]:
        """Count files by language"""
        counts = {}
        for sf in scored_files:
            lang = sf.file.language
            counts[lang] = counts.get(lang, 0) + 1
        return counts
    