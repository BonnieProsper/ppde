"""
Unit tests for ppde.warnings (Step 5 - Warning Gating).

Structure mirrors the five rules in the spec:
    1. Surprise threshold
    2. Stability-aware suppression
    3. Deduplication (exact key + operation collapse)
    4. Ranking (sort order)
    5. Max warnings cap

Plus an integration suite that runs realistic multi-score scenarios
through the full pipeline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ppde.context import Location, Operation, PatternContext, Stability
from ppde.frequency import SurpriseScore
from ppde.warnings import (
    HIGH_SURPRISE,
    MAX_WARNINGS,
    MIN_SURPRISE,
    gate_warnings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(loc=Location.MODULE_LEVEL, op=Operation.EXTERNAL_CALL, stab=Stability.MODIFIED):
    return PatternContext(loc, op, stab)


def _score(
    surprise,
    detector="has_timeout_parameter",
    context=None,
    observed=False,
    historical_freq=None,
    sample_size=15,
):
    """Factory: produce a SurpriseScore with sane defaults, override what you need."""
    if context is None:
        context = _ctx()
    if historical_freq is None:
        # Back-derive so the field is consistent with surprise when observed=False
        historical_freq = surprise if not observed else (1.0 - surprise)
    return SurpriseScore(
        detector_name=detector,
        context=context,
        observed=observed,
        historical_freq=historical_freq,
        surprise=surprise,
        sample_size=sample_size,
    )


# ---------------------------------------------------------------------------
# 1. Surprise threshold (Rule 1)
# ---------------------------------------------------------------------------

class TestSurpriseThreshold:

    def test_below_threshold_is_dropped(self):
        scores = [_score(MIN_SURPRISE - 0.01)]
        assert gate_warnings(scores) == []

    def test_exactly_at_threshold_passes(self):
        scores = [_score(MIN_SURPRISE)]
        assert len(gate_warnings(scores)) == 1

    def test_above_threshold_passes(self):
        scores = [_score(0.9)]
        assert len(gate_warnings(scores)) == 1

    def test_empty_input_returns_empty(self):
        assert gate_warnings([]) == []


# ---------------------------------------------------------------------------
# 2. Stability-aware suppression (Rule 2)
# ---------------------------------------------------------------------------

class TestStabilitySuppression:

    # --- NEW: always suppressed ---

    def test_new_context_suppressed_regardless_of_surprise(self):
        """Even surprise = 1.0 is suppressed when stability is NEW."""
        scores = [_score(1.0, context=_ctx(stab=Stability.NEW))]
        assert gate_warnings(scores) == []

    def test_new_context_suppressed_at_high_surprise(self):
        scores = [_score(HIGH_SURPRISE, context=_ctx(stab=Stability.NEW))]
        assert gate_warnings(scores) == []

    # --- VOLATILE: requires HIGH_SURPRISE ---

    def test_volatile_below_high_surprise_suppressed(self):
        scores = [_score(HIGH_SURPRISE - 0.01, context=_ctx(stab=Stability.VOLATILE))]
        assert gate_warnings(scores) == []

    def test_volatile_exactly_at_high_surprise_passes(self):
        scores = [_score(HIGH_SURPRISE, context=_ctx(stab=Stability.VOLATILE))]
        assert len(gate_warnings(scores)) == 1

    def test_volatile_above_high_surprise_passes(self):
        scores = [_score(0.95, context=_ctx(stab=Stability.VOLATILE))]
        assert len(gate_warnings(scores)) == 1

    # --- MODIFIED / STABLE: normal rules ---

    def test_modified_passes_at_min_surprise(self):
        scores = [_score(MIN_SURPRISE, context=_ctx(stab=Stability.MODIFIED))]
        assert len(gate_warnings(scores)) == 1

    def test_stable_passes_at_min_surprise(self):
        scores = [_score(MIN_SURPRISE, context=_ctx(stab=Stability.STABLE))]
        assert len(gate_warnings(scores)) == 1


# ---------------------------------------------------------------------------
# 3. Deduplication (Rule 3)
# ---------------------------------------------------------------------------

class TestDeduplication:

    # --- Level A: exact (detector_name, context) ---

    def test_exact_duplicate_keeps_higher_surprise(self):
        """Two scores, same detector + context. Higher surprise survives."""
        ctx = _ctx()
        scores = [
            _score(0.7, detector="has_timeout_parameter", context=ctx),
            _score(0.9, detector="has_timeout_parameter", context=ctx),
        ]
        warnings = gate_warnings(scores)
        assert len(warnings) == 1
        assert warnings[0].score.surprise == 0.9

    # --- Level B: operation collapse ---

    def test_same_operation_keeps_highest_surprise_only(self):
        """
        Two different detectors, same context, same operation family.
        Both are ERROR_HANDLING in the same context → only the higher surprise survives.
        """
        ctx = _ctx(op=Operation.ERROR_HANDLING, stab=Stability.STABLE)
        scores = [
            _score(0.7, detector="has_broad_exception", context=ctx),
            _score(0.85, detector="swallows_exception", context=ctx),
        ]
        warnings = gate_warnings(scores)
        assert len(warnings) == 1
        assert warnings[0].score.detector_name == "swallows_exception"
        assert warnings[0].score.surprise == 0.85

    def test_different_operations_are_independent(self):
        """EXTERNAL_CALL and MUTATION in same location - both survive."""
        ctx_ext  = _ctx(op=Operation.EXTERNAL_CALL, stab=Stability.STABLE)
        ctx_mut  = _ctx(op=Operation.MUTATION,       stab=Stability.STABLE)
        scores = [
            _score(0.8, detector="has_timeout_parameter", context=ctx_ext),
            _score(0.75, detector="mutates_parameter",    context=ctx_mut),
        ]
        warnings = gate_warnings(scores)
        assert len(warnings) == 2

    def test_same_operation_different_locations_are_independent(self):
        """Same operation but different Location → different (context, operation) keys."""
        ctx_mod = _ctx(loc=Location.MODULE_LEVEL, op=Operation.ERROR_HANDLING, stab=Stability.STABLE)
        ctx_cls = _ctx(loc=Location.CLASS_METHOD,  op=Operation.ERROR_HANDLING, stab=Stability.STABLE)
        scores = [
            _score(0.7,  detector="has_broad_exception", context=ctx_mod),
            _score(0.85, detector="swallows_exception",  context=ctx_cls),
        ]
        warnings = gate_warnings(scores)
        assert len(warnings) == 2


# ---------------------------------------------------------------------------
# 4. Ranking (Rule 4)
# ---------------------------------------------------------------------------

class TestRanking:

    def test_higher_surprise_ranks_first(self):
        ctx = _ctx(stab=Stability.STABLE)
        scores = [
            _score(0.7,  detector="has_timeout_parameter", context=ctx),
            _score(0.9,  detector="mutates_parameter",     context=_ctx(op=Operation.MUTATION, stab=Stability.STABLE)),
        ]
        warnings = gate_warnings(scores)
        assert warnings[0].score.surprise == 0.9
        assert warnings[1].score.surprise == 0.7

    def test_tiebreak_on_sample_size(self):
        """Same surprise - larger sample_size ranks first."""
        ctx_a = _ctx(op=Operation.EXTERNAL_CALL, stab=Stability.STABLE)
        ctx_b = _ctx(op=Operation.MUTATION,      stab=Stability.STABLE)
        scores = [
            _score(0.8, detector="has_timeout_parameter", context=ctx_a, sample_size=12),
            _score(0.8, detector="mutates_parameter",     context=ctx_b, sample_size=25),
        ]
        warnings = gate_warnings(scores)
        assert warnings[0].score.sample_size == 25
        assert warnings[1].score.sample_size == 12

    def test_tiebreak_on_stability_after_sample_size(self):
        """Same surprise, same sample_size - STABLE ranks above MODIFIED."""
        ctx_stable   = _ctx(op=Operation.EXTERNAL_CALL, stab=Stability.STABLE)
        ctx_modified = _ctx(op=Operation.MUTATION,      stab=Stability.MODIFIED)
        scores = [
            _score(0.8, detector="has_timeout_parameter", context=ctx_modified, sample_size=15),
            _score(0.8, detector="mutates_parameter",     context=ctx_stable,   sample_size=15),
        ]
        warnings = gate_warnings(scores)
        assert warnings[0].score.context.stability == Stability.STABLE
        assert warnings[1].score.context.stability == Stability.MODIFIED


# ---------------------------------------------------------------------------
# 5. Max warnings cap (Rule 5)
# ---------------------------------------------------------------------------

class TestWarningsCap:

    def test_more_than_max_is_truncated(self):
        """Generate MAX_WARNINGS + 3 valid scores across distinct operations/locations.
        Only MAX_WARNINGS should come back."""
        scores = []
        # Use distinct (location, operation) pairs so dedup doesn't collapse them
        locations  = [Location.MODULE_LEVEL, Location.CLASS_METHOD, Location.NESTED_FUNCTION]
        operations = [Operation.EXTERNAL_CALL, Operation.MUTATION, Operation.ERROR_HANDLING]
        detectors  = ["has_timeout_parameter", "mutates_parameter", "has_broad_exception"]

        i = 0
        for loc in locations:
            for op, det in zip(operations, detectors):
                ctx = PatternContext(loc, op, Stability.STABLE)
                # Descending surprise so ranking is deterministic
                surprise = 0.95 - (i * 0.01)
                scores.append(_score(surprise, detector=det, context=ctx))
                i += 1
                if i >= MAX_WARNINGS + 3:
                    break
            if i >= MAX_WARNINGS + 3:
                break

        warnings = gate_warnings(scores)
        assert len(warnings) == MAX_WARNINGS

    def test_exactly_max_is_not_truncated(self):
        """Exactly MAX_WARNINGS valid scores → all returned."""
        scores = []
        locations  = [Location.MODULE_LEVEL, Location.CLASS_METHOD, Location.NESTED_FUNCTION]
        operations = [Operation.EXTERNAL_CALL, Operation.MUTATION, Operation.ERROR_HANDLING]
        detectors  = ["has_timeout_parameter", "mutates_parameter", "has_broad_exception"]

        i = 0
        for loc in locations:
            for op, det in zip(operations, detectors):
                if i >= MAX_WARNINGS:
                    break
                ctx = PatternContext(loc, op, Stability.STABLE)
                scores.append(_score(0.9 - (i * 0.01), detector=det, context=ctx))
                i += 1
            if i >= MAX_WARNINGS:
                break

        warnings = gate_warnings(scores)
        assert len(warnings) == MAX_WARNINGS

    def test_fewer_than_max_returns_all(self):
        ctx_a = _ctx(op=Operation.EXTERNAL_CALL, stab=Stability.STABLE)
        ctx_b = _ctx(op=Operation.MUTATION,      stab=Stability.STABLE)
        scores = [
            _score(0.9, detector="has_timeout_parameter", context=ctx_a),
            _score(0.7, detector="mutates_parameter",     context=ctx_b),
        ]
        warnings = gate_warnings(scores)
        assert len(warnings) == 2


# ---------------------------------------------------------------------------
# 6. Integration - realistic multi-score scenarios
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_mixed_scenario(self):
        """
        Realistic input:
            - 1 NEW context (suppressed)
            - 1 VOLATILE below HIGH_SURPRISE (suppressed)
            - 1 VOLATILE above HIGH_SURPRISE (passes)
            - 2 ERROR_HANDLING in same context (collapse to 1)
            - 1 low-surprise MODIFIED (below threshold, dropped)
            - 1 high-surprise STABLE (passes)

        Expected output: 3 warnings (volatile, best error handler, stable)
        """
        ctx_new      = _ctx(stab=Stability.NEW)
        ctx_volatile = _ctx(stab=Stability.VOLATILE)
        ctx_err      = _ctx(op=Operation.ERROR_HANDLING, stab=Stability.STABLE)
        ctx_stable   = _ctx(op=Operation.MUTATION, stab=Stability.STABLE)

        scores = [
            _score(0.95, detector="has_timeout_parameter", context=ctx_new),       # suppressed: NEW
            _score(0.7,  detector="has_timeout_parameter", context=ctx_volatile),  # suppressed: VOLATILE < 0.8
            _score(0.85, detector="has_timeout_parameter", context=ctx_volatile),  # passes: VOLATILE >= 0.8
            _score(0.7,  detector="has_broad_exception",   context=ctx_err),       # collapse: lower surprise
            _score(0.9,  detector="swallows_exception",    context=ctx_err),       # collapse: wins
            _score(0.3,  detector="mutates_parameter",     context=ctx_stable),    # dropped: below threshold
            _score(0.88, detector="mutates_parameter",     context=ctx_stable),    # passes
        ]

        warnings = gate_warnings(scores)

        assert len(warnings) == 3

        # Ranked by surprise: 0.9, 0.88, 0.85
        assert warnings[0].score.surprise == 0.9
        assert warnings[0].score.detector_name == "swallows_exception"

        assert warnings[1].score.surprise == 0.88
        assert warnings[1].score.detector_name == "mutates_parameter"

        assert warnings[2].score.surprise == 0.85
        assert warnings[2].score.detector_name == "has_timeout_parameter"

    def test_all_suppressed_returns_empty(self):
        """Every score is either NEW or below threshold → empty output."""
        scores = [
            _score(0.95, context=_ctx(stab=Stability.NEW)),
            _score(0.4,  context=_ctx(stab=Stability.STABLE)),
            _score(0.55, context=_ctx(stab=Stability.MODIFIED)),
        ]
        assert gate_warnings(scores) == []

    def test_warning_wraps_score_faithfully(self):
        """The Warning object must contain the exact SurpriseScore, unmodified."""
        original = _score(0.8)
        warnings = gate_warnings([original])
        assert len(warnings) == 1
        assert warnings[0].score is original


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():
    print("Running warning gating tests...\n")

    suites = [
        ("Threshold",    TestSurpriseThreshold),
        ("Stability",    TestStabilitySuppression),
        ("Dedup",        TestDeduplication),
        ("Ranking",      TestRanking),
        ("Cap",          TestWarningsCap),
        ("Integration",  TestIntegration),
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
