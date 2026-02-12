"""
Context Model - Step 3

Maps (detector, code location, git history) → discrete PatternContext.
Context is the GROUP BY key for frequency counting.
"""
import ast
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List

from .data_structures import Commit


class Location(Enum):
    MODULE_LEVEL    = "module"
    CLASS_METHOD    = "method"
    NESTED_FUNCTION = "nested"


class Operation(Enum):
    EXTERNAL_CALL   = "external"
    MUTATION        = "mutation"
    ERROR_HANDLING  = "error"
    COMPUTATION     = "computation"


class Stability(Enum):
    NEW      = "new"       # < 30 days old
    VOLATILE = "volatile"  # ≥3 fixes in 90 days
    MODIFIED = "modified"  # changed in 90 days
    STABLE   = "stable"    # unchanged > 90 days


assert len(Location) * len(Operation) * len(Stability) <= 100


OPERATION_BY_DETECTOR: Dict[str, Operation] = {
    "has_timeout_parameter": Operation.EXTERNAL_CALL,
    "has_error_wrapper":     Operation.ERROR_HANDLING,
    "mutates_parameter":     Operation.MUTATION,
    "writes_global_state":   Operation.MUTATION,
    "has_broad_exception":   Operation.ERROR_HANDLING,
    "swallows_exception":    Operation.ERROR_HANDLING,
}


@dataclass(frozen=True)
class PatternContext:
    location:  Location
    operation: Operation
    stability: Stability

    def signature(self) -> str:
        return f"{self.location.value}:{self.operation.value}:{self.stability.value}"


# Constants for stability calculation
_NEW_DAYS = 30
_VOLATILE_DAYS = 90
_FIX_THRESHOLD = 3


def _file_first_seen(file_path: str, commits: List[Commit]) -> datetime | None:
    """When did this file first appear in history?"""
    earliest = None
    for commit in commits:
        if file_path in commit.files_changed:
            if earliest is None or commit.timestamp < earliest:
                earliest = commit.timestamp
    return earliest


def _last_modified(file_path: str, commits: List[Commit]) -> datetime | None:
    """When was this file last touched?"""
    latest = None
    for commit in commits:
        if file_path in commit.files_changed:
            if latest is None or commit.timestamp > latest:
                latest = commit.timestamp
    return latest


def _count_fix_commits(file_path: str, commits: List[Commit], cutoff: datetime) -> int:
    """Count fix-related commits touching this file after cutoff."""
    count = 0
    for commit in commits:
        if commit.timestamp >= cutoff:
            if file_path in commit.files_changed:
                if commit.has_fix_keyword():
                    count += 1
    return count


def _determine_location(
    function_node: ast.FunctionDef | None,
    class_node: ast.ClassDef | None,
    parent_function_node: ast.FunctionDef | None = None,
) -> Location:
    """Determine code location. Precedence: NESTED > CLASS_METHOD > MODULE."""
    if function_node is not None:
        if parent_function_node is not None:
            return Location.NESTED_FUNCTION
        if class_node is not None:
            return Location.CLASS_METHOD
        return Location.MODULE_LEVEL
    
    if class_node is not None:
        return Location.CLASS_METHOD
    
    return Location.MODULE_LEVEL


def _determine_operation(detector_name: str) -> Operation:
    return OPERATION_BY_DETECTOR.get(detector_name, Operation.COMPUTATION)


def _determine_stability(file_path: str, commits: List[Commit], now: datetime) -> Stability:
    """
    File stability from git history.
    Precedence: NEW > VOLATILE > MODIFIED > STABLE
    """
    first_seen = _file_first_seen(file_path, commits)
    
    if first_seen is None:
        return Stability.NEW
    
    # Rule 1 - NEW
    if (now - first_seen).total_seconds() / 86400.0 < _NEW_DAYS:
        return Stability.NEW
    
    cutoff_90 = now - timedelta(days=_VOLATILE_DAYS)
    
    # Rule 2 - VOLATILE
    if _count_fix_commits(file_path, commits, cutoff_90) >= _FIX_THRESHOLD:
        return Stability.VOLATILE
    
    # Rule 3 - MODIFIED
    last_mod = _last_modified(file_path, commits)
    if last_mod is not None and last_mod >= cutoff_90:
        return Stability.MODIFIED
    
    if last_mod is None:
        return Stability.MODIFIED
    
    return Stability.STABLE


def assign_context(
    detector_name: str,
    function_node: ast.FunctionDef | None,
    class_node: ast.ClassDef | None,
    file_path: str,
    commits: List[Commit],
    now: datetime,
    parent_function_node: ast.FunctionDef | None = None,
) -> PatternContext:
    """Map (detector, code location, git history) to a PatternContext."""
    return PatternContext(
        location=_determine_location(function_node, class_node, parent_function_node),
        operation=_determine_operation(detector_name),
        stability=_determine_stability(file_path, commits, now),
    )
