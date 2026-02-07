"""
Data structures for Git history representation.

All structures are immutable and deterministic.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class FileDiff:
    """Represents changes to a single file in a commit."""
    
    file_path: str
    additions: int
    deletions: int
    diff_text: str  # Full unified diff for this file
    
    @property
    def is_python(self) -> bool:
        """Check if this is a Python file."""
        return self.file_path.endswith('.py')


@dataclass(frozen=True)
class Commit:
    """Represents a single commit with metadata and changes."""
    
    sha: str
    author_email: str
    timestamp: datetime
    message: str
    file_diffs: List[FileDiff]
    
    @property
    def files_changed(self) -> List[str]:
        """Get list of changed file paths."""
        return [diff.file_path for diff in self.file_diffs]
    
    @property
    def python_files_changed(self) -> List[str]:
        """Get list of changed Python files."""
        return [diff.file_path for diff in self.file_diffs if diff.is_python]
    
    def age_in_days(self, reference_time: datetime) -> float:
        """Calculate age of commit in days from reference time."""
        delta = reference_time - self.timestamp
        return delta.total_seconds() / 86400.0
    
    def has_fix_keyword(self) -> bool:
        """Check if commit message suggests a bug fix."""
        message_lower = self.message.lower()
        fix_keywords = ['fix', 'bug', 'error', 'crash', 'broken', 'issue']
        return any(keyword in message_lower for keyword in fix_keywords)
    
    def is_refactor(self) -> bool:
        """Check if commit message suggests intentional refactor."""
        message_lower = self.message.lower()
        refactor_keywords = ['refactor', 'cleanup', 'style', 'migration']
        return any(keyword in message_lower for keyword in refactor_keywords)
