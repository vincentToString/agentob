import re
import tiktoken
from typing import List, Dict, Optional
from .models import FileChange


class TokenCounter:
    """Token counting utilities for OpenAI models"""
    
    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoder = tiktoken.get_encoding(encoding_name)
    
    def count(self, text: str) -> int:
        """Count tokens in text"""
        try:
            return len(self.encoder.encode(text))
        except Exception:
            # Fallback: rough estimate
            return len(text) // 4
    
    def count_file(self, file: FileChange) -> int:
        """Count tokens in a file's patch"""
        return self.count(file.patch)


class LanguageDetector:
    """Detect programming language from file path"""
    
    EXTENSIONS = {
        # Compiled languages
        '.py': 'python',
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.go': 'go',
        '.rs': 'rust',
        '.swift': 'swift',
        '.kt': 'kotlin',
        
        # Scripting languages
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.rb': 'ruby',
        '.php': 'php',
        '.pl': 'perl',
        '.sh': 'shell',
        '.bash': 'shell',
        
        # Web
        '.html': 'html',
        '.htm': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.vue': 'vue',
        
        # Data/Config
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.xml': 'xml',
        '.toml': 'toml',
        '.ini': 'ini',
        
        # Documentation
        '.md': 'markdown',
        '.rst': 'restructuredtext',
        '.txt': 'text',
        
        # Other
        '.sql': 'sql',
        '.graphql': 'graphql',
    }
    
    
    
    @classmethod
    def detect(cls, filepath: str) -> str:
        """Detect language from filepath"""
        for ext, lang in cls.EXTENSIONS.items():
            if filepath.endswith(ext):
                return lang
        return 'unknown'
    



class FileClassifier:
    """Classify file types"""
    
    CRITICAL_PATTERNS = [
        # Security & Auth
        'auth', 'security', 'crypto', 'password', 'token',
        'session', 'jwt', 'oauth', 'permission', 'acl',
        
        # Financial
        'payment', 'billing', 'invoice', 'transaction',
        'checkout', 'cart', 'order',
        
        # Data
        'migration', 'schema', 'model', 'database',
        
        # API
        'api/', '/api/', 'routes/', 'endpoint', 'controller',
        'graphql', 'rest',
        
        # Infrastructure
        'middleware', 'interceptor', 'filter',
        'config/production', 'config/prod',
    ]
    
    TEST_PATTERNS = [
        'test_', '_test.', 'test/', '/test/',
        'tests/', '/tests/', 'spec/', '/spec/',
        '__tests__/', '*.test.', '*.spec.',
    ]
    
    DOC_PATTERNS = [
        'README', 'CHANGELOG', 'CONTRIBUTING',
        'LICENSE', 'docs/', '/docs/',
        '.md', '.rst', '.txt',
    ]
    
    GENERATED_PATTERNS = [
        'package-lock.json', 'yarn.lock', 'Gemfile.lock',
        'Pipfile.lock', 'poetry.lock',
        'node_modules/', 'vendor/', 'dist/', 'build/',
        '.min.js', '.min.css',
    ]
    
    @classmethod
    def is_critical(cls, filepath: str) -> bool:
        """Check if file matches critical patterns"""
        path_lower = filepath.lower()
        return any(pattern in path_lower for pattern in cls.CRITICAL_PATTERNS)
    
    @classmethod
    def is_test(cls, filepath: str) -> bool:
        """Check if file is a test file"""
        path_lower = filepath.lower()
        return any(pattern in path_lower for pattern in cls.TEST_PATTERNS)
    
    @classmethod
    def is_doc(cls, filepath: str) -> bool:
        """Check if file is documentation"""
        return any(pattern in filepath for pattern in cls.DOC_PATTERNS)
    
    @classmethod
    def is_generated(cls, filepath: str) -> bool:
        """Check if file is generated/vendored"""
        return any(pattern in filepath for pattern in cls.GENERATED_PATTERNS)


class PatchProcessor:
    """Process git patches"""
    
    @staticmethod
    def remove_deletion_only_hunks(patch: str) -> str:
        """
        Remove hunks that only contain deletions
        (Qodo AI strategy)
        """
        lines = patch.split('\n')
        result = []
        current_hunk = []
        in_hunk = False
        hunk_has_additions = False
        
        for line in lines:
            if line.startswith('@@'):
                # Save previous hunk if it had additions
                if in_hunk and hunk_has_additions:
                    result.extend(current_hunk)
                
                # Start new hunk
                current_hunk = [line]
                in_hunk = True
                hunk_has_additions = False
            elif in_hunk:
                current_hunk.append(line)
                if line.startswith('+') and not line.startswith('+++'):
                    hunk_has_additions = True
            else:
                result.append(line)
        
        # Don't forget last hunk
        if in_hunk and hunk_has_additions:
            result.extend(current_hunk)
        
        return '\n'.join(result)
    
    @staticmethod
    def expand_context(patch: str, lines_before: int = 3, lines_after: int = 3) -> str:
        """
        Expand context around changes
        (Enhanced strategy)
        """
        # TODO: This would require access to full file
        # For now, just preserve the patch as-is
        # In production, you'd fetch full file from GitHub API
        return patch
    
    @staticmethod
    def extract_function_signatures(patch: str, language: str) -> List[str]:
        """
        Extract function/method signatures from patch
        """
        signatures = []
        
        patterns = {
            'python': r'^\+?def\s+(\w+)\s*\(',
            'javascript': r'^\+?function\s+(\w+)\s*\(|^\+?const\s+(\w+)\s*=\s*\(',
            'typescript': r'^\+?function\s+(\w+)\s*\(|^\+?const\s+(\w+)\s*=\s*\(',
            'java': r'^\+?\s*(public|private|protected)?\s*\w+\s+(\w+)\s*\(',
        }
        
        pattern = patterns.get(language)
        if not pattern:
            return signatures
        
        for line in patch.split('\n'):
            match = re.search(pattern, line)
            if match:
                sig = match.group(1) or match.group(2)
                if sig:
                    signatures.append(sig)
        
        return signatures