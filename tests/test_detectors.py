"""
Unit tests for AST pattern detectors.

Tests demonstrate positive matches, negative matches, and edge cases.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ppde.detectors import DetectorContext
from ppde.detectors.error import (
    has_broad_exception,
    swallows_exception,
)
from ppde.detectors.external import (
    has_error_wrapper,
    has_timeout_parameter,
)
from ppde.detectors.mutation import (
    mutates_parameter,
    writes_global_state,
)
from ppde.detectors.utils import is_external_call  # Now a utility, not a detector


def parse_code(code: str) -> ast.AST:
    """Parse Python code into AST."""
    return ast.parse(code)


def empty_context() -> DetectorContext:
    """Create minimal empty context for testing."""
    return DetectorContext(
        function_node=None,
        class_node=None,
        module_imports=[],
    )


def context_with_function(code: str) -> tuple[ast.AST, DetectorContext]:
    """Create context with function node."""
    tree = parse_code(code)
    func = tree.body[0]
    ctx = DetectorContext(
        function_node=func if isinstance(func, ast.FunctionDef) else None,
        class_node=None,
        module_imports=[],
    )
    return tree, ctx


# External Interaction Tests

def test_is_external_call():
    """Test utility function (not a violation detector)."""
    print("Testing is_external_call (utility)...")
    
    # Positive: requests.get
    tree = parse_code("requests.get(url)")
    call_node = tree.body[0].value
    assert is_external_call(call_node) == True, "Should detect requests.get"
    
    # Positive: db.query
    tree = parse_code("db.query(sql)")
    call_node = tree.body[0].value
    assert is_external_call(call_node) == True, "Should detect db.query"
    
    # Negative: regular function call
    tree = parse_code("calculate_total(items)")
    call_node = tree.body[0].value
    assert is_external_call(call_node) == False, "Should not detect regular call"
    
    print("✓ is_external_call (utility) tests passed")


def test_has_timeout_parameter():
    print("Testing has_timeout_parameter...")
    ctx = empty_context()
    
    # Positive: has timeout
    tree = parse_code("requests.get(url, timeout=30)")
    call_node = tree.body[0].value
    assert has_timeout_parameter(call_node, ctx) == True, "Should detect timeout parameter"
    
    # Negative: no timeout
    tree = parse_code("requests.get(url)")
    call_node = tree.body[0].value
    assert has_timeout_parameter(call_node, ctx) == False, "Should not detect timeout when absent"
    
    # Edge: not a call
    tree = parse_code("x = 5")
    assign_node = tree.body[0]
    assert has_timeout_parameter(assign_node, ctx) == False, "Should return False for non-call"
    
    print("✓ has_timeout_parameter tests passed")


def test_has_error_wrapper():
    print("Testing has_error_wrapper (context-only)...")
    
    # Positive: call inside try-except
    code = """
def fetch_data():
    try:
        requests.get(url)
    except Exception:
        pass
"""
    tree, ctx = context_with_function(code)
    call_node = tree.body[0].body[0].body[0].value  # The requests.get call
    assert has_error_wrapper(call_node, ctx) == True, "Should detect try-except wrapper"
    
    # Negative: no try-except
    code = """
def fetch_data():
    requests.get(url)
"""
    tree, ctx = context_with_function(code)
    assert has_error_wrapper(tree, ctx) == False, "Should not detect wrapper when absent"
    
    print("✓ has_error_wrapper (context-only) tests passed")


# State Mutation Tests

def test_mutates_parameter():
    print("Testing mutates_parameter...")
    
    # Positive: assigns to parameter
    code = """
def process(items):
    items.append(5)
    items = []
"""
    tree = parse_code(code)
    func_node = tree.body[0]
    ctx = empty_context()
    assert mutates_parameter(func_node, ctx) == True, "Should detect parameter mutation"
    
    # Negative: doesn't mutate parameter
    code = """
def calculate(x):
    result = x * 2
    return result
"""
    tree = parse_code(code)
    func_node = tree.body[0]
    assert mutates_parameter(func_node, ctx) == False, "Should not detect mutation when absent"
    
    # Edge: mutates self (should be excluded)
    code = """
def method(self, x):
    self.value = x
"""
    tree = parse_code(code)
    func_node = tree.body[0]
    assert mutates_parameter(func_node, ctx) == False, "Should exclude self mutation"
    
    print("✓ mutates_parameter tests passed")


def test_writes_global_state():
    print("Testing writes_global_state...")
    
    # Positive: uses global keyword
    code = """
def update_counter():
    global counter
    counter += 1
"""
    tree = parse_code(code)
    func_node = tree.body[0]
    ctx = empty_context()
    assert writes_global_state(func_node, ctx) == True, "Should detect global write"
    
    # Negative: no global keyword
    code = """
def increment(x):
    return x + 1
"""
    tree = parse_code(code)
    func_node = tree.body[0]
    assert writes_global_state(func_node, ctx) == False, "Should not detect when absent"
    
    print("✓ writes_global_state tests passed")


# Error Handling Tests

def test_has_broad_exception():
    print("Testing has_broad_exception...")
    ctx = empty_context()
    
    # Positive: bare except
    code = """
try:
    risky()
except:
    pass
"""
    tree = parse_code(code)
    handler = tree.body[0].handlers[0]
    assert has_broad_exception(handler, ctx) == True, "Should detect bare except"
    
    # Positive: except Exception
    code = """
try:
    risky()
except Exception:
    pass
"""
    tree = parse_code(code)
    handler = tree.body[0].handlers[0]
    assert has_broad_exception(handler, ctx) == True, "Should detect except Exception"
    
    # Negative: specific exception
    code = """
try:
    risky()
except ValueError:
    pass
"""
    tree = parse_code(code)
    handler = tree.body[0].handlers[0]
    assert has_broad_exception(handler, ctx) == False, "Should not detect specific exception"
    
    print("✓ has_broad_exception tests passed")


def test_swallows_exception():
    print("Testing swallows_exception...")
    ctx = empty_context()
    
    # Positive: only pass in handler
    code = """
try:
    risky()
except Exception:
    pass
"""
    tree = parse_code(code)
    handler = tree.body[0].handlers[0]
    assert swallows_exception(handler, ctx) == True, "Should detect swallowed exception"
    
    # Negative: has logging
    code = """
try:
    risky()
except Exception:
    log.error("Failed")
"""
    tree = parse_code(code)
    handler = tree.body[0].handlers[0]
    assert swallows_exception(handler, ctx) == False, "Should not detect when handler has code"
    
    print("✓ swallows_exception tests passed")


def run_all_tests():
    """Run all detector tests."""
    print("Running AST pattern detector tests...\n")
    
    try:
        # Utility (not a detector)
        test_is_external_call()
        
        # External interaction
        test_has_timeout_parameter()
        test_has_error_wrapper()
        
        # State mutation
        test_mutates_parameter()
        test_writes_global_state()
        
        # Error handling
        test_has_broad_exception()
        test_swallows_exception()
        
        print("\n✅ All detector tests passed!")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
