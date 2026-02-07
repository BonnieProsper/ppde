"""
Stateless utility functions for AST pattern detection.

These are pure helper functions, not class methods.
Detectors use these as needed but remain standalone.
"""
import ast
from typing import Optional

# Call detection utilities

def is_call_to(node: ast.AST, target_names: list[str]) -> bool:
    """
    Check if node is a call to any of the target functions/methods.
    
    Examples:
        requests.get(...) -> matches ["get", "requests.get"]
        db.query(...) -> matches ["query", "db.query"]
    """
    if not isinstance(node, ast.Call):
        return False
    
    func = node.func
    
    # Direct function call: func()
    if isinstance(func, ast.Name):
        return func.id in target_names
    
    # Method call: obj.method()
    if isinstance(func, ast.Attribute):
        method_name = func.attr
        if method_name in target_names:
            return True
        
        # Check full path: obj.method
        if isinstance(func.value, ast.Name):
            full_name = f"{func.value.id}.{method_name}"
            return full_name in target_names
    
    return False


def has_keyword_arg(call_node: ast.Call, keyword: str) -> bool:
    """Check if a call has a specific keyword argument."""
    if not isinstance(call_node, ast.Call):
        return False
    
    return any(kw.arg == keyword for kw in call_node.keywords)


def is_external_call(node: ast.AST) -> bool:
    """
    Check if node is a call to external services.
    
    This is a GATING function, not a scorable pattern.
    Used to determine context for other detectors.
    
    Matches common external call patterns:
    - HTTP: requests.get/post, urllib, httpx
    - Database: db.query, session.execute, cursor.execute
    - Filesystem: open(), pathlib operations
    
    Returns True if external call detected, False otherwise.
    """
    external_patterns = [
        # HTTP libraries
        "requests.get", "requests.post", "requests.put", "requests.delete",
        "get", "post", "put", "delete",  # method names
        "urlopen", "urllib",
        # Database
        "query", "execute", "fetchall", "fetchone",
        "db.query", "session.execute", "cursor.execute",
        # Filesystem
        "open", "read", "write",
    ]
    
    return is_call_to(node, external_patterns)


# Function name utilities

def get_function_name_prefix(func_node: Optional[ast.FunctionDef]) -> Optional[str]:
    """
    Extract function name prefix (before first underscore).
    
    Examples:
        get_user -> "get"
        calculate_total -> "calculate"
        _private_method -> "_private"
    """
    if not func_node:
        return None
    
    name = func_node.name
    if '_' in name:
        return name.split('_')[0]
    return name


# Mutation detection utilities

def assigns_to_parameter(func_node: ast.FunctionDef, exclude_self: bool = True) -> bool:
    """
    Check if function assigns to any of its parameters.
    
    Args:
        func_node: Function to check
        exclude_self: If True, ignore assignments to 'self' (common in methods)
    """
    # Get parameter names
    param_names = {arg.arg for arg in func_node.args.args}
    if exclude_self:
        param_names.discard('self')
    
    # Look for assignments to these names
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in param_names:
                    return True
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name) and node.target.id in param_names:
                return True
    
    return False


# Context building utilities

def build_context(node: ast.AST, tree: ast.Module):
    """
    Build minimal context for a node within a module.
    
    Args:
        node: The AST node being inspected
        tree: The full module AST
        
    Returns:
        DetectorContext with parent function/class and imports
    """
    from . import DetectorContext
    
    # Find parent function and class
    parent_function = _find_parent_function(node, tree)
    parent_class = _find_parent_class(node, tree)
    
    # Extract imports
    imports = _extract_imports(tree)
    
    return DetectorContext(
        function_node=parent_function,
        class_node=parent_class,
        module_imports=imports,
    )


def _find_parent_function(node: ast.AST, tree: ast.Module) -> Optional[ast.FunctionDef]:
    """Find the function containing this node, if any."""
    for potential_parent in ast.walk(tree):
        if isinstance(potential_parent, ast.FunctionDef):
            for child in ast.walk(potential_parent):
                if child is node:
                    return potential_parent
    return None


def _find_parent_class(node: ast.AST, tree: ast.Module) -> Optional[ast.ClassDef]:
    """Find the class containing this node, if any."""
    for potential_parent in ast.walk(tree):
        if isinstance(potential_parent, ast.ClassDef):
            for child in ast.walk(potential_parent):
                if child is node:
                    return potential_parent
    return None


def _extract_imports(tree: ast.Module) -> list[str]:
    """
    Extract all imported names from a module.
    
    Returns list like: ['requests', 'os', 'json', 'pathlib.Path']
    """
    imports = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if module:
                    imports.append(f"{module}.{alias.name}")
                else:
                    imports.append(alias.name)
    
    return imports


def find_nodes_of_type(tree: ast.AST, node_type: type) -> list[ast.AST]:
    """
    Find all nodes of a specific type in the tree.
    
    Example:
        find_nodes_of_type(tree, ast.Call)  # All function calls
        find_nodes_of_type(tree, ast.FunctionDef)  # All functions
    """
    return [node for node in ast.walk(tree) if isinstance(node, node_type)]
