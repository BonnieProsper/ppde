"""
Error handling pattern detectors.

Detects patterns related to exception handling.

Each detector is a pure function: (node, context) -> bool

IMPORTANT: These are VIOLATION patterns only.
Mitigation signals (like logging presence) do not belong here.
"""
import ast

from . import DetectorContext


def has_broad_exception(node: ast.AST, context: DetectorContext) -> bool:
    """
    Detect if exception handler catches broad exceptions.
    
    VIOLATION PATTERN: Overly broad exception catching.
    
    Matches:
    - Bare except: (no exception type)
    - except Exception:
    - except BaseException:
    
    Returns True if broad catch detected, False otherwise.
    """
    if not isinstance(node, ast.ExceptHandler):
        return False
    
    # Bare except (no type specified)
    if node.type is None:
        return True
    
    # except Exception / except BaseException
    if isinstance(node.type, ast.Name):
        if node.type.id in ("Exception", "BaseException"):
            return True
    
    return False


def swallows_exception(node: ast.AST, context: DetectorContext) -> bool:
    """
    Detect if exception handler swallows the exception.
    
    VIOLATION PATTERN: Exception caught but ignored.
    
    Swallowing = body contains only 'pass' statement.
    
    Returns True if exception swallowed, False otherwise.
    """
    if not isinstance(node, ast.ExceptHandler):
        return False
    
    # Check if body is just 'pass'
    if len(node.body) == 1:
        if isinstance(node.body[0], ast.Pass):
            return True
    
    return False


