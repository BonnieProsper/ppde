"""
External interaction pattern detectors.

Detects patterns related to external calls (network, database, filesystem).

Each detector is a pure function: (node, context) -> bool

IMPORTANT: These are VIOLATION patterns only.
Context/gating functions (like is_external_call) are in utils.py.
"""
import ast

from . import DetectorContext
from .utils import has_keyword_arg


def has_timeout_parameter(node: ast.AST, context: DetectorContext) -> bool:
    """
    Detect if a call has a timeout parameter.
    
    VIOLATION PATTERN: External call missing timeout.
    
    Returns True if timeout= keyword argument present, False otherwise.
    Ambiguous cases (dynamic timeout) return False.
    """
    if not isinstance(node, ast.Call):
        return False
    
    return has_keyword_arg(node, "timeout")


def has_error_wrapper(node: ast.AST, context: DetectorContext) -> bool:
    """
    Detect if node is inside a try-except block.
    
    CONTEXT-ONLY: This detector must never trigger warnings on its own.
    Used to gate other detectors or provide context.
    
    Returns True if call appears within exception handler, False otherwise.
    
    Note: This is simplified - checks if parent function has try-except,
    not if this specific call is wrapped.
    """
    if not context.in_function:
        return False
    
    func = context.function_node
    for child in ast.walk(func):
        if isinstance(child, ast.Try):
            return True
    
    return False


