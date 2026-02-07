"""
Orchestrator - Step 7

Glue layer. Wires Steps 1-6 together.
No logic, no thresholds, no reasoning.
"""
import ast
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from .context import assign_context
from .data_structures import Commit
from .detectors import (
    has_broad_exception,
    has_timeout_parameter,
    mutates_parameter,
    swallows_exception,
    writes_global_state,
)
from .explanation import Explanation, explain
from .frequency import FrequencyTable, compute_surprise
from .git_history import get_commit_history
from .warnings import gate_warnings


@dataclass
class DetectorContext:
    function_node: ast.FunctionDef | None
    class_node: ast.ClassDef | None
    module_imports: List[str]


_DETECTORS = {
    "has_timeout_parameter": has_timeout_parameter,
    "mutates_parameter":     mutates_parameter,
    "writes_global_state":   writes_global_state,
    "has_broad_exception":   has_broad_exception,
    "swallows_exception":    swallows_exception,
}


def _build_parent_map(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    parent_map = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


def _find_enclosing_function(
    node: ast.AST,
    parent_map: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | None:
    current = node
    while current in parent_map:
        current = parent_map[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
    return None


def _find_enclosing_class(
    node: ast.AST,
    parent_map: dict[ast.AST, ast.AST]
) -> ast.ClassDef | None:
    current = node
    while current in parent_map:
        current = parent_map[current]
        if isinstance(current, ast.ClassDef):
            return current
    return None


def _find_parent_function(
    func_node: ast.FunctionDef,
    parent_map: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | None:
    current = func_node
    while current in parent_map:
        current = parent_map[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
    return None


def _build_detector_context(
    node: ast.AST,
    tree: ast.Module,
    parent_map: dict[ast.AST, ast.AST]
) -> DetectorContext:
    function_node = _find_enclosing_function(node, parent_map)
    class_node = _find_enclosing_class(node, parent_map)

    imports = []
    for child in ast.iter_child_nodes(tree):
        if isinstance(child, ast.Import):
            imports.extend(alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                imports.append(child.module)

    return DetectorContext(
        function_node=function_node,
        class_node=class_node,
        module_imports=imports,
    )


def _build_frequency_table(commits: List[Commit], repo_path: Path) -> FrequencyTable:
    """
    Build frequency table from git history.
    
    Currently stubbed - returns empty table (cold start mode).
    Real implementation: replay file contents at each commit,
    run detectors, record observations.
    """
    return FrequencyTable()


def _analyze_file(
    file_path: Path,
    repo_path: Path,
    commits: List[Commit],
    table: FrequencyTable,
    now: datetime,
) -> List[Explanation]:
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    parent_map = _build_parent_map(tree)
    rel_path = str(file_path.relative_to(repo_path))

    scores = []

    for node in ast.walk(tree):
        detector_ctx = _build_detector_context(node, tree, parent_map)
        
        parent_func = None
        if detector_ctx.function_node:
            parent_func = _find_parent_function(detector_ctx.function_node, parent_map)

        for detector_name, detector_func in _DETECTORS.items():
            observed = detector_func(node, detector_ctx)

            context = assign_context(
                detector_name=detector_name,
                function_node=detector_ctx.function_node,
                class_node=detector_ctx.class_node,
                file_path=rel_path,
                commits=commits,
                now=now,
                parent_function_node=parent_func,
            )

            score = compute_surprise(detector_name, context, observed, table)
            if score is not None:
                scores.append(score)

    warnings = gate_warnings(scores)
    return explain(warnings)


def analyze_repo(path: Path) -> List[Explanation]:
    """
    Analyze a Git repository.
    
    COLD START MODE: Frequency table is empty, so no warnings are produced.
    This demonstrates conservative behavior when baseline data is missing.
    """
    repo_path = Path(path).resolve()

    commits = get_commit_history(str(repo_path))
    table = FrequencyTable()
    now = datetime.now()

    all_explanations = []

    for file_path in repo_path.rglob("*.py"):
        # Skip hidden, venv, cache
        parts = file_path.relative_to(repo_path).parts
        if any(p.startswith(".") or p == "venv" or p == "__pycache__" for p in parts):
            continue

        explanations = _analyze_file(file_path, repo_path, commits, table, now)
        all_explanations.extend(explanations)

    return all_explanations
