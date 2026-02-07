"""
State mutation pattern detectors.

Detects patterns related to state changes.

Each detector is a pure function: (node, context) -> bool
"""
import ast

from . import DetectorContext
from .utils import assigns_to_parameter


def mutates_parameter(node: ast.AST, context: DetectorContext) -> bool:
    """
    Detect if function mutates its own parameters.
    
    Returns True if function assigns to parameter names, False otherwise.
    Excludes 'self' parameter (common in methods).
    """
    if not isinstance(node, ast.FunctionDef):
        return False
    
    return assigns_to_parameter(node, exclude_self=True)


def writes_global_state(node: ast.AST, context: DetectorContext) -> bool:
    """
    Detect if function writes to module-level variables.
    
    Returns True if function uses 'global' keyword, False otherwise.
    
    Note: This is a conservative check - only detects explicit global declarations.
    Misses mutations via object attributes or list/dict modifications.
    """
    if not isinstance(node, ast.FunctionDef):
        return False
    
    for child in ast.walk(node):
        if isinstance(child, ast.Global):
            return True
    
    return False


