"""
Unit tests for ppde.context (Step 3 - Context Model).

Structure mirrors the three axes:
    1. Location tests   - _determine_location mapping rules
    2. Stability tests  - _determine_stability precedence chain
    3. Integration tests - assign_context end-to-end

Every design rule has at least one positive and one negative case.
"""
import ast
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ppde.context import (
    OPERATION_BY_DETECTOR,
    Location,
    Operation,
    PatternContext,
    Stability,
    _determine_location,
    _determine_stability,
    assign_context,
)
from ppde.data_structures import Commit, FileDiff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 2, 3, 12, 0, 0)   # fixed reference point


def _make_commit(
    file_path: str,
    message: str = "update",
    days_ago: float = 10,
    sha: str = "abc123",
) -> Commit:
    """Minimal Commit factory for stability tests."""
    return Commit(
        sha=sha,
        author_email="dev@example.com",
        timestamp=NOW - timedelta(days=days_ago),
        message=message,
        file_diffs=[FileDiff(file_path=file_path, additions=1, deletions=0, diff_text="")],
    )


# ---------------------------------------------------------------------------
# 1. Location axis
# ---------------------------------------------------------------------------

class TestDetermineLocation:

    # --- MODULE_LEVEL ---

    def test_no_parents_is_module_level(self):
        """Bare code with no enclosing function or class → MODULE_LEVEL."""
        assert _determine_location(
            function_node=None,
            class_node=None,
        ) == Location.MODULE_LEVEL

    def test_function_only_no_class_is_module_level(self):
        """Top-level function (not nested, not in a class) → MODULE_LEVEL."""
        func = ast.parse("def f(): pass").body[0]
        assert _determine_location(
            function_node=func,
            class_node=None,
            parent_function_node=None,   # explicitly: no outer function
        ) == Location.MODULE_LEVEL

    # --- CLASS_METHOD ---

    def test_function_inside_class_is_class_method(self):
        """Function whose parent is a ClassDef → CLASS_METHOD."""
        cls = ast.parse("class C:\n def m(self): pass").body[0]
        method = cls.body[0]
        assert _determine_location(
            function_node=method,
            class_node=cls,
        ) == Location.CLASS_METHOD

    def test_class_without_function_is_class_method(self):
        """Code directly inside a class body (no function wrapper) → CLASS_METHOD."""
        cls = ast.parse("class C:\n x = 1").body[0]
        assert _determine_location(
            function_node=None,
            class_node=cls,
        ) == Location.CLASS_METHOD

    # --- NESTED_FUNCTION ---

    def test_function_inside_function_is_nested(self):
        """Inner function with an outer function → NESTED_FUNCTION."""
        outer = ast.parse("def outer():\n def inner(): pass").body[0]
        inner = outer.body[0]
        assert _determine_location(
            function_node=inner,
            class_node=None,
            parent_function_node=outer,
        ) == Location.NESTED_FUNCTION

    # --- Precedence: NESTED_FUNCTION beats CLASS_METHOD ---
    # (A nested function inside a method is still NESTED_FUNCTION)

    def test_nested_inside_method_is_nested_not_method(self):
        """Nested function inside a class method → NESTED_FUNCTION, not CLASS_METHOD."""
        src = "class C:\n def m(self):\n  def helper(): pass"
        cls   = ast.parse(src).body[0]
        method = cls.body[0]
        helper = method.body[0]
        assert _determine_location(
            function_node=helper,
            class_node=cls,
            parent_function_node=method,
        ) == Location.NESTED_FUNCTION


# ---------------------------------------------------------------------------
# 2. Stability axis - every precedence edge is tested
# ---------------------------------------------------------------------------

class TestDetermineStability:

    # --- NEW (highest precedence) ---

    def test_file_created_today_is_new(self):
        commits = [_make_commit("app.py", days_ago=1, sha="a1")]
        assert _determine_stability("app.py", commits, NOW) == Stability.NEW

    def test_file_created_29_days_ago_is_new(self):
        commits = [_make_commit("app.py", days_ago=29, sha="a2")]
        assert _determine_stability("app.py", commits, NOW) == Stability.NEW

    def test_new_beats_volatile(self):
        """File < 30 days old with ≥ 3 fixes → NEW wins over VOLATILE."""
        commits = [
            _make_commit("app.py", message="fix bug",  days_ago=5,  sha="n1"),
            _make_commit("app.py", message="fix crash", days_ago=10, sha="n2"),
            _make_commit("app.py", message="fix error", days_ago=15, sha="n3"),
            _make_commit("app.py", message="initial",   days_ago=20, sha="n4"),
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.NEW

    # --- VOLATILE ---

    def test_three_fixes_in_90_days_is_volatile(self):
        commits = [
            _make_commit("app.py", message="fix bug",    days_ago=40, sha="v1"),
            _make_commit("app.py", message="fix crash",  days_ago=50, sha="v2"),
            _make_commit("app.py", message="fix broken", days_ago=60, sha="v3"),
            _make_commit("app.py", message="initial",    days_ago=200, sha="v4"),  # first-seen > 30 days
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.VOLATILE

    def test_two_fixes_is_not_volatile(self):
        """Only 2 fix-commits → does NOT reach VOLATILE threshold."""
        commits = [
            _make_commit("app.py", message="fix bug",   days_ago=40, sha="v5"),
            _make_commit("app.py", message="fix crash", days_ago=50, sha="v6"),
            _make_commit("app.py", message="initial",   days_ago=200, sha="v7"),
        ]
        # 2 fixes + old file → falls through to MODIFIED (touched in 90 days)
        assert _determine_stability("app.py", commits, NOW) == Stability.MODIFIED

    def test_volatile_beats_modified(self):
        """≥ 3 fixes in 90 days takes priority even when file is also 'modified'."""
        commits = [
            _make_commit("app.py", message="fix x",  days_ago=35, sha="vm1"),
            _make_commit("app.py", message="fix y",  days_ago=45, sha="vm2"),
            _make_commit("app.py", message="fix z",  days_ago=55, sha="vm3"),
            _make_commit("app.py", message="refactor", days_ago=70, sha="vm4"),
            _make_commit("app.py", message="initial",  days_ago=200, sha="vm5"),
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.VOLATILE

    # --- MODIFIED ---

    def test_touched_in_90_days_no_fixes_is_modified(self):
        commits = [
            _make_commit("app.py", message="add feature", days_ago=60, sha="m1"),
            _make_commit("app.py", message="initial",     days_ago=200, sha="m2"),
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.MODIFIED

    def test_touched_exactly_at_90_days_is_modified(self):
        """Boundary: commit exactly 90 days ago is still within the window."""
        commits = [
            _make_commit("app.py", message="tweak",  days_ago=90, sha="m3"),
            _make_commit("app.py", message="initial", days_ago=200, sha="m4"),
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.MODIFIED

    # --- STABLE ---

    def test_no_changes_in_90_days_is_stable(self):
        commits = [
            _make_commit("app.py", message="initial", days_ago=120, sha="s1"),
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.STABLE

    def test_only_old_fixes_is_stable(self):
        """Fix commits outside the 90-day window don't count toward VOLATILE."""
        commits = [
            _make_commit("app.py", message="fix bug",    days_ago=100, sha="s2"),
            _make_commit("app.py", message="fix crash",  days_ago=110, sha="s3"),
            _make_commit("app.py", message="fix broken", days_ago=120, sha="s4"),
            _make_commit("app.py", message="initial",    days_ago=150, sha="s5"),
        ]
        assert _determine_stability("app.py", commits, NOW) == Stability.STABLE

    # --- Default / edge ---

    def test_unknown_file_defaults_to_modified(self):
        """No commit in history touches this file → conservative default MODIFIED."""
        commits = [_make_commit("other.py", days_ago=5, sha="d1")]
        assert _determine_stability("missing.py", commits, NOW) == Stability.MODIFIED

    def test_empty_history_defaults_to_modified(self):
        assert _determine_stability("app.py", [], NOW) == Stability.MODIFIED


# ---------------------------------------------------------------------------
# 3. Operation mapping
# ---------------------------------------------------------------------------

class TestOperationMapping:

    def test_all_current_detectors_are_mapped(self):
        """Every detector we ship must appear in the mapping."""
        expected = {
            "has_timeout_parameter",
            "has_error_wrapper",
            "mutates_parameter",
            "writes_global_state",
            "has_broad_exception",
            "swallows_exception",
        }
        assert set(OPERATION_BY_DETECTOR.keys()) == expected

    def test_unknown_detector_falls_back_to_computation(self):
        """Unregistered detector name → COMPUTATION (the safe default)."""
        result = OPERATION_BY_DETECTOR.get("some_future_detector", Operation.COMPUTATION)
        assert result == Operation.COMPUTATION


# ---------------------------------------------------------------------------
# 4. PatternContext / signature
# ---------------------------------------------------------------------------

class TestPatternContext:

    def test_signature_format(self):
        ctx = PatternContext(Location.CLASS_METHOD, Operation.MUTATION, Stability.VOLATILE)
        assert ctx.signature() == "method:mutation:volatile"

    def test_frozen_and_hashable(self):
        ctx = PatternContext(Location.MODULE_LEVEL, Operation.EXTERNAL_CALL, Stability.NEW)
        # Must be usable as a dict key
        d = {ctx: 42}
        assert d[ctx] == 42

    def test_equal_contexts_hash_equal(self):
        a = PatternContext(Location.MODULE_LEVEL, Operation.COMPUTATION, Stability.STABLE)
        b = PatternContext(Location.MODULE_LEVEL, Operation.COMPUTATION, Stability.STABLE)
        # Frozen dataclasses with same fields must be equal and hash-equal
        assert a == b
        assert hash(a) == hash(b)


# ---------------------------------------------------------------------------
# 5. assign_context - integration / wiring
# ---------------------------------------------------------------------------

class TestAssignContext:

    def test_same_node_different_detectors_different_operation(self):
        """
        Core design property: same location + same stability, but different
        detectors → different Operation in the resulting context.
        """
        commits = [_make_commit("svc.py", days_ago=60, sha="i1"),
                   _make_commit("svc.py", days_ago=200, sha="i0")]

        ctx_timeout = assign_context(
            detector_name="has_timeout_parameter",
            function_node=None, class_node=None,
            file_path="svc.py", commits=commits, now=NOW,
        )
        ctx_broad = assign_context(
            detector_name="has_broad_exception",
            function_node=None, class_node=None,
            file_path="svc.py", commits=commits, now=NOW,
        )

        # Location and Stability are identical
        assert ctx_timeout.location  == ctx_broad.location
        assert ctx_timeout.stability == ctx_broad.stability
        # Operation differs - this is the whole point
        assert ctx_timeout.operation == Operation.EXTERNAL_CALL
        assert ctx_broad.operation   == Operation.ERROR_HANDLING

    def test_class_method_mutation_stable(self):
        """Full wiring: class method + mutation detector + old file → expected tuple."""
        cls  = ast.parse("class C:\n def m(self): pass").body[0]
        meth = cls.body[0]
        commits = [_make_commit("models.py", days_ago=120, sha="w1")]

        ctx = assign_context(
            detector_name="mutates_parameter",
            function_node=meth,
            class_node=cls,
            file_path="models.py",
            commits=commits,
            now=NOW,
        )

        assert ctx == PatternContext(Location.CLASS_METHOD, Operation.MUTATION, Stability.STABLE)
        assert ctx.signature() == "method:mutation:stable"

    def test_nested_function_new_file(self):
        """Nested function in a brand-new file."""
        outer = ast.parse("def outer():\n def inner(): pass").body[0]
        inner = outer.body[0]
        commits = [_make_commit("scratch.py", days_ago=2, sha="nf1")]

        ctx = assign_context(
            detector_name="writes_global_state",
            function_node=inner,
            class_node=None,
            file_path="scratch.py",
            commits=commits,
            now=NOW,
            parent_function_node=outer,
        )

        assert ctx == PatternContext(Location.NESTED_FUNCTION, Operation.MUTATION, Stability.NEW)

    def test_unregistered_detector_gets_computation(self):
        """Future detector not yet in OPERATION_BY_DETECTOR → COMPUTATION."""
        commits = [_make_commit("x.py", days_ago=200, sha="ur1")]

        ctx = assign_context(
            detector_name="some_new_detector",
            function_node=None, class_node=None,
            file_path="x.py", commits=commits, now=NOW,
        )

        assert ctx.operation == Operation.COMPUTATION


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():
    print("Running context model tests...\n")

    suites = [
        ("Location",     TestDetermineLocation),
        ("Stability",    TestDetermineStability),
        ("Operation",    TestOperationMapping),
        ("PatternCtx",   TestPatternContext),
        ("Integration",  TestAssignContext),
    ]

    passed = 0
    failed = 0

    for suite_name, cls in suites:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in sorted(methods):
            label = f"{suite_name}.{method_name}"
            try:
                getattr(instance, method_name)()
                print(f"  ✓ {label}")
                passed += 1
            except Exception as e:
                print(f"  ✗ {label}")
                print(f"      {e}")
                failed += 1

    print(f"\n{'✅' if failed == 0 else '❌'} {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
