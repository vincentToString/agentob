# compression/language_analyzer.py

from typing import Dict, List, Optional
from collections import Counter
from .models import FileChange
from ..redis_client import RedisClient
from ..config import Config

class PullRequestLanguageAnalyzer:
    """
    Dynamically determine language priority based on repository composition
    """
    
    def __init__(self):
        self._repo_cache = RedisClient(Config.REDIS_URL)
    
    async def analyze_repository(
        self, 
        repo_name: str,
        pr_number: int,
        head_sha: str,
        pr_files: Optional[List[FileChange]] = None
    ) -> Dict[str, float]:
        """
        Determine language priorities for a repository
        
        Priority sources (in order of preference):
        1. Current PR files (If this PR majorly about Python, then Python files will be the top concerns)
        
        Returns:
            Dict mapping language -> priority score (0-100)
        """

        cache_key = f"lang_scores:{repo_name}:{pr_number}:{head_sha}"

        # Check cache
        scores = await self._repo_cache.get_score(cache_key)
        if scores:
            return scores
    
        scores = self._analyze_file_list(pr_files)
        
        # Cache result
        await self._repo_cache.store_rate(cache_key, scores)
        
        return scores
    
    def _analyze_file_list(self, pr_files: List[FileChange] | None) -> Dict[str, float]:
        """
        Analyze file list to determine language distribution
        
        Strategy:
        1. Count files per language
        2. Calculate percentage distribution
        3. Assign priorities based on distribution
        """
        from .utils import LanguageDetector
        
        # Count files by language
        language_counts = Counter()
        language_line_changes = Counter()

        if not pr_files:
            return self._get_default_priorities()
        
        for file in pr_files:
            # Skip non-code files
            if self._should_skip_file(file.path):
                continue
            
            lang = LanguageDetector.detect(file.path)
            if lang != 'unknown':
                language_counts[lang] += 1
                language_line_changes[lang] += file.additions + file.deletions
        
        # Calculate priorities based on prevalence
        total_files = sum(language_counts.values())
        priorities = {}
        
        for lang in language_counts:
            # Percentage of codebase
            percentage = (language_line_changes[lang] / total_files) * 100
            
            priority = 50 + (percentage * 0.5)
            priorities[lang] = round(priority, 1)
        
        return priorities
    
    def _should_skip_file(self, path: str) -> bool:
        """Skip files that shouldn't count toward language distribution"""
        skip_patterns = [
            # Generated/vendor
            'node_modules/', 'vendor/', 'dist/', 'build/',
            '.min.js', '.min.css',
            
            # Lock files
            'package-lock.json', 'yarn.lock', 'Gemfile.lock',
            'Pipfile.lock', 'poetry.lock',
            
            # Documentation (count separately)
            'README', 'LICENSE', 'CHANGELOG',
        ]
        
        return any(pattern in path for pattern in skip_patterns)
    
    def _get_default_priorities(self) -> Dict[str, float]:
        """
        Fallback priorities when analysis is unavailable
        
        These are intentionally flat (all ~70) because we don't know
        the repository composition
        """
        return {
            'python': 70,
            'javascript': 70,
            'typescript': 70,
            'java': 70,
            'go': 70,
            'rust': 70,
            'c': 70,
            'cpp': 70,
            'ruby': 70,
            'php': 70,
            'swift': 70,
            'kotlin': 70,
            'html': 60,
            'css': 60,
            'scss': 60,
            'json': 40,
            'yaml': 40,
            'xml': 40,
            'markdown': 30,
            'text': 20,
        }
    
