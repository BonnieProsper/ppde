"""
Unit tests for ppde.frequency (Step 4 - Frequency Model).

Structure mirrors the risk surface:
    1. FrequencyTable - record + query correctness
    2. Sparsity gate  - MIN_OBSERVATIONS enforced
    3. Surprise math  - both directions, boundary values
    4. Exclusion gate - context-only detectors never score
    5. Integration    - full pipeline: record history → score current code
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from ppde.context import Location, Operation, PatternContext, Stability
from ppde.frequency import (
    MIN_OBSERVATIONS,
    VIOLATION_DETECTORS,
    FrequencyTable,
    compute_surprise,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(loc=Location.MODULE_LEVEL, op=Operation.EXTERNAL_CALL, stab=Stability.MODIFIED):
    return PatternContext(loc, op, stab)


def _fill_table(
    table: FrequencyTable,
    detector: str,
    context: PatternContext,
    true_count: int,
    false_count: int,
) -> None:
    """Stuff a table with a known number of True/False observations."""
    for _ in range(true_count):
        table.record(detector, context, True)
    for _ in range(false_count):
        table.record(detector, context, False)


# ---------------------------------------------------------------------------
# 1. FrequencyTable - record and query
# ---------------------------------------------------------------------------

class TestFrequencyTable:

    def test_empty_table_returns_zero_observations(self):
        t = FrequencyTable()
        assert t.total_observations("has_timeout_parameter", _ctx()) == 0

    def test_empty_table_frequency_is_none(self):
        t = FrequencyTable()
        assert t.frequency("has_timeout_parameter", _ctx()) is None

    def test_record_increments_counts(self):
        t = FrequencyTable()
        ctx = _ctx()
        t.record("has_timeout_parameter", ctx, True)
        t.record("has_timeout_parameter", ctx, True)
        t.record("has_timeout_parameter", ctx, False)
        assert t.total_observations("has_timeout_parameter", ctx) == 3

    def test_different_contexts_are_independent(self):
        t = FrequencyTable()
        ctx_a = _ctx(stab=Stability.NEW)
        ctx_b = _ctx(stab=Stability.STABLE)
        t.record("has_timeout_parameter", ctx_a, True)
        t.record("has_timeout_parameter", ctx_b, False)
        assert t.total_observations("has_timeout_parameter", ctx_a) == 1
        assert t.total_observations("has_timeout_parameter", ctx_b) == 1

    def test_different_detectors_are_independent(self):
        t = FrequencyTable()
        ctx = _ctx()
        t.record("has_timeout_parameter", ctx, True)
        t.record("mutates_parameter",      ctx, False)
        assert t.total_observations("has_timeout_parameter", ctx) == 1
        assert t.total_observations("mutates_parameter",      ctx) == 1


# ---------------------------------------------------------------------------
# 2. Sparsity gate - frequency returns None below MIN_OBSERVATIONS
# ---------------------------------------------------------------------------

class TestSparsityGate:

    def test_below_threshold_returns_none(self):
        t = FrequencyTable()
        ctx = _ctx()
        # MIN_OBSERVATIONS - 1 recordings
        _fill_table(t, "has_timeout_parameter", ctx, MIN_OBSERVATIONS - 1, 0)
        assert t.frequency("has_timeout_parameter", ctx) is None

    def test_exactly_at_threshold_returns_frequency(self):
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, MIN_OBSERVATIONS, 0)
        # All True → freq = 1.0
        assert t.frequency("has_timeout_parameter", ctx) == 1.0

    def test_one_above_threshold_returns_frequency(self):
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, MIN_OBSERVATIONS, 1)
        freq = t.frequency("has_timeout_parameter", ctx)
        assert freq is not None
        assert abs(freq - MIN_OBSERVATIONS / (MIN_OBSERVATIONS + 1)) < 1e-9


# ---------------------------------------------------------------------------
# 3. Surprise math - the core computation
# ---------------------------------------------------------------------------

class TestSurpriseMath:

    def test_pattern_usually_present_and_missing_is_high_surprise(self):
        """
        History: timeout present 80% of the time.
        Current: timeout missing.
        Surprise should equal the historical frequency (0.8).
        """
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, 8, 2)   # freq = 0.8

        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert abs(score.surprise - 0.8) < 1e-9
        assert score.observed is False
        assert abs(score.historical_freq - 0.8) < 1e-9

    def test_pattern_rarely_present_and_missing_is_low_surprise(self):
        """
        History: timeout present 20% of the time.
        Current: timeout missing.
        Surprise should be low (0.2) - this is normal for you.
        """
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, 2, 8)   # freq = 0.2

        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert abs(score.surprise - 0.2) < 1e-9

    def test_pattern_rarely_present_and_now_present_is_high_surprise(self):
        """
        History: broad exception 20% of the time.
        Current: broad exception present.
        Surprise = 1 - 0.2 = 0.8.
        """
        t = FrequencyTable()
        ctx = _ctx(op=Operation.ERROR_HANDLING)
        _fill_table(t, "has_broad_exception", ctx, 2, 8)   # freq = 0.2

        score = compute_surprise("has_broad_exception", ctx, observed=True, table=t)

        assert score is not None
        assert abs(score.surprise - 0.8) < 1e-9
        assert score.observed is True

    def test_pattern_always_present_and_missing_surprise_is_one(self):
        """freq = 1.0, observed = False → surprise = 1.0 (maximally surprising)."""
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, MIN_OBSERVATIONS, 0)

        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert score.surprise == 1.0

    def test_pattern_never_present_and_missing_surprise_is_zero(self):
        """freq = 0.0, observed = False → surprise = 0.0 (completely expected)."""
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, 0, MIN_OBSERVATIONS)

        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert score.surprise == 0.0

    def test_surprise_score_carries_sample_size(self):
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "has_timeout_parameter", ctx, 7, 5)   # 12 total

        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert score.sample_size == 12


# ---------------------------------------------------------------------------
# 4. Exclusion gate - context-only detectors never produce scores
# ---------------------------------------------------------------------------

class TestExclusionGate:

    def test_context_only_detector_returns_none(self):
        """has_error_wrapper is context-only. Even with full data, no score."""
        t = FrequencyTable()
        ctx = _ctx(op=Operation.ERROR_HANDLING)
        _fill_table(t, "has_error_wrapper", ctx, 8, 2)

        score = compute_surprise("has_error_wrapper", ctx, observed=True, table=t)

        assert score is None

    def test_all_violation_detectors_are_scorable(self):
        """Every detector in VIOLATION_DETECTORS must produce a score when data is sufficient."""
        for det_name in VIOLATION_DETECTORS:
            t = FrequencyTable()
            # Use the operation that matches this detector (doesn't matter for scoring,
            # but keeps the test honest about real usage)
            ctx = _ctx()
            _fill_table(t, det_name, ctx, 6, 6)   # 12 observations, freq = 0.5

            score = compute_surprise(det_name, ctx, observed=False, table=t)
            assert score is not None, f"{det_name} should be scorable but returned None"

    def test_unknown_detector_returns_none(self):
        """A detector not in VIOLATION_DETECTORS is silently excluded."""
        t = FrequencyTable()
        ctx = _ctx()
        _fill_table(t, "some_future_detector", ctx, 8, 2)

        score = compute_surprise("some_future_detector", ctx, observed=True, table=t)

        assert score is None


# ---------------------------------------------------------------------------
# 5. Integration - simulate a realistic history → score pipeline
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_full_pipeline_timeout_deviation(self):
        """
        Scenario: developer writes 15 external calls in MODULE_LEVEL / MODIFIED context.
        12 of them have timeout=. 3 don't.
        New code arrives without timeout.

        Expected: surprise = 12/15 = 0.8 (high - this deviates from their norm).
        """
        t = FrequencyTable()
        ctx = PatternContext(Location.MODULE_LEVEL, Operation.EXTERNAL_CALL, Stability.MODIFIED)

        # Replay history
        for _ in range(12):
            t.record("has_timeout_parameter", ctx, True)
        for _ in range(3):
            t.record("has_timeout_parameter", ctx, False)

        # Score current code (timeout missing)
        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert score.detector_name == "has_timeout_parameter"
        assert score.context == ctx
        assert score.observed is False
        assert abs(score.historical_freq - 0.8) < 1e-9
        assert abs(score.surprise - 0.8) < 1e-9
        assert score.sample_size == 15

    def test_full_pipeline_no_deviation(self):
        """
        Scenario: developer rarely uses timeout (2/12).
        New code also lacks timeout.

        Expected: surprise = 2/12 ≈ 0.167 (low - this is normal).
        """
        t = FrequencyTable()
        ctx = PatternContext(Location.CLASS_METHOD, Operation.EXTERNAL_CALL, Stability.STABLE)

        for _ in range(2):
            t.record("has_timeout_parameter", ctx, True)
        for _ in range(10):
            t.record("has_timeout_parameter", ctx, False)

        score = compute_surprise("has_timeout_parameter", ctx, observed=False, table=t)

        assert score is not None
        assert abs(score.surprise - (2 / 12)) < 1e-9

    def test_sparse_context_produces_no_score(self):
        """
        Scenario: only 4 observations in this context.
        Even with a clear pattern, we don't have enough data.
        """
        t = FrequencyTable()
        ctx = PatternContext(Location.NESTED_FUNCTION, Operation.MUTATION, Stability.NEW)

        _fill_table(t, "mutates_parameter", ctx, 4, 0)

        score = compute_surprise("mutates_parameter", ctx, observed=False, table=t)

        assert score is None   # 4 < MIN_OBSERVATIONS


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():
    print("Running frequency model tests...\n")

    suites = [
        ("FreqTable",   TestFrequencyTable),
        ("Sparsity",    TestSparsityGate),
        ("Surprise",    TestSurpriseMath),
        ("Exclusion",   TestExclusionGate),
        ("Integration", TestIntegration),
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
