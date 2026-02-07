"""
Evaluation utilities for PPDE.

This module handles bug labeling and validation logic.
It is intentionally separate from data extraction.
"""
from datetime import timedelta
from typing import List, Optional

from ..data_structures import Commit


def find_subsequent_fix(
    commit: Commit,
    all_commits: List[Commit],
    max_days: int = 7,
) -> Optional[Commit]:
    """
    Find if a commit had a subsequent fix within time window.
    
    This is used for evaluation/labeling, not during normal operation.
    
    Args:
        commit: The commit to check
        all_commits: All commits in history (must be sorted newest first)
        max_days: Maximum days between commit and fix (default: 7)
        
    Returns:
        The fix commit if found, None otherwise
        
    A fix is identified by:
    1. Occurs within max_days after the original commit
    2. Has fix keyword in message
    3. Modifies at least one of the same files
    """
    commit_index = None
    for i, c in enumerate(all_commits):
        if c.sha == commit.sha:
            commit_index = i
            break
    
    if commit_index is None:
        return None
    
    cutoff_time = commit.timestamp + timedelta(days=max_days)
    changed_files = set(commit.files_changed)
    
    # Look at commits that came after this one
    for subsequent in all_commits[:commit_index]:
        # Stop if outside time window
        if subsequent.timestamp > cutoff_time:
            continue
        
        # Check if it's a fix
        if not subsequent.has_fix_keyword():
            continue
        
        # Check if it touches same files
        if set(subsequent.files_changed) & changed_files:
            return subsequent
    
    return None
