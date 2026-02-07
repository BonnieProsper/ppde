"""
AST Pattern Detector Interfaces

Detectors are pure functions that answer: "Does this pattern exist here?"

Design principles:
- Return bool only (no tri-state, no UNKNOWN)
- Stateless (no history, no configuration)
- Imperfect detection is acceptable
- No severity, scoring, or warnings
- False positives filtered by model layer

Ambiguity handling:
- If uncertain → return False
- Model layer filters via consistency thresholds
- Detectors do not make epistemic judgments
"""
import ast
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class DetectorContext:
    """
    Minimal context provided to detectors.
    
    This is intentionally small - detectors should not need
    complex project-wide context to make local decisions.
    """
    function_node: Optional[ast.FunctionDef]  # Containing function if any
    class_node: Optional[ast.ClassDef]  # Containing class if any
    module_imports: list[str]  # Import names in the module
    
    @property
    def in_function(self) -> bool:
        """Check if node is inside a function."""
        return self.function_node is not None
    
    @property
    def in_class(self) -> bool:
        """Check if node is inside a class."""
        return self.class_node is not None


# Detector type signature
# Pure function: (node, context) -> bool
Detector = Callable[[ast.AST, DetectorContext], bool]


# Import all detector functions
from .error import has_broad_exception, swallows_exception
from .external import has_timeout_parameter
from .mutation import mutates_parameter, writes_global_state

__all__ = [
    'DetectorContext',
    'Detector',
    'has_timeout_parameter',
    'mutates_parameter',
    'writes_global_state',
    'has_broad_exception',
    'swallows_exception',
]
