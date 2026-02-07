"""
Unit tests for ppde.explanation (Step 6 - Explanation Layer).

Test philosophy (from spec):
    - Assert on structure, not exact wording.
    - Verify explanations reflect the correct SurpriseScore fields.
    - Verify no mutation of Warning or SurpriseScore.

Structure:
    1. Output shape      - one Explanation per Warning, order preserved
    2. Observation       - detector-specific first sentence, both observed values
    3. Norm sentence     - frequency and count math, location/stability labels
    4. Deviation sentence - present and consistent
    5. Forbidden content - exhaustive scan: no advice, no "should", no "bug"
    6. Immutability      - source objects are never touched
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from ppde.context import Location, Operation, PatternContext, Stability
from ppde.explanation import Explanation, explain
from ppde.frequency import SurpriseScore
from ppde.warnings import Warning

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(loc=Location.MODULE_LEVEL, op=Operation.EXTERNAL_CALL, stab=Stability.MODIFIED):
    return PatternContext(loc, op, stab)


def _warning(
    surprise=0.8,
    detector="has_timeout_parameter",
    context=None,
    observed=False,
    historical_freq=None,
    sample_size=15,
):
    """Factory: produce a Warning with sane defaults, override what you need."""
    if context is None:
        context = _ctx()
    if historical_freq is None:
        # Back-derive so the field is consistent with surprise when observed=False
        historical_freq = surprise if not observed else (1.0 - surprise)
    score = SurpriseScore(
        detector_name=detector,
        context=context,
        observed=observed,
        historical_freq=historical_freq,
        surprise=surprise,
        sample_size=sample_size,
    )
    return Warning(score=score)


# ---------------------------------------------------------------------------
# 1. Output shape
# ---------------------------------------------------------------------------

class TestOutputShape:

    def test_empty_input_returns_empty(self):
        assert explain([]) == []

    def test_one_warning_one_explanation(self):
        result = explain([_warning()])
        assert len(result) == 1
        assert isinstance(result[0], Explanation)

    def test_order_is_preserved(self):
        """Three warnings in → three explanations out, same order."""
        w1 = _warning(surprise=0.9, detector="has_timeout_parameter",
                      context=_ctx(op=Operation.EXTERNAL_CALL))
        w2 = _warning(surprise=0.8, detector="mutates_parameter",
                      context=_ctx(op=Operation.MUTATION))
        w3 = _warning(surprise=0.7, detector="has_broad_exception",
                      context=_ctx(op=Operation.ERROR_HANDLING))
        result = explain([w1, w2, w3])
        assert result[0].warning is w1
        assert result[1].warning is w2
        assert result[2].warning is w3

    def test_explanation_wraps_warning(self):
        w = _warning()
        result = explain([w])
        assert result[0].warning is w

    def test_message_is_non_empty_string(self):
        result = explain([_warning()])
        assert isinstance(result[0].message, str)
        assert len(result[0].message) > 0


# ---------------------------------------------------------------------------
# 2. Observation sentence (sentence 1 - detector-specific)
# ---------------------------------------------------------------------------

class TestObservationSentence:

    def _first_line(self, **kwargs) -> str:
        return explain([_warning(**kwargs)])[0].message.split("\n")[0]

    # --- has_timeout_parameter ---

    def test_timeout_absent(self):
        line = self._first_line(detector="has_timeout_parameter", observed=False)
        assert "timeout" in line.lower()
        # observed=False → pattern NOT present
        assert "not" in line.lower() or "does not" in line.lower()

    def test_timeout_present(self):
        line = self._first_line(detector="has_timeout_parameter", observed=True,
                                surprise=0.8, historical_freq=0.2)
        assert "timeout" in line.lower()

    # --- mutates_parameter ---

    def test_mutates_absent(self):
        line = self._first_line(detector="mutates_parameter", observed=False,
                                context=_ctx(op=Operation.MUTATION))
        assert "parameter" in line.lower()

    def test_mutates_present(self):
        line = self._first_line(detector="mutates_parameter", observed=True,
                                context=_ctx(op=Operation.MUTATION),
                                surprise=0.8, historical_freq=0.2)
        assert "parameter" in line.lower()
        assert "reassign" in line.lower()

    # --- writes_global_state ---

    def test_global_absent(self):
        line = self._first_line(detector="writes_global_state", observed=False,
                                context=_ctx(op=Operation.MUTATION))
        assert "global" in line.lower()

    def test_global_present(self):
        line = self._first_line(detector="writes_global_state", observed=True,
                                context=_ctx(op=Operation.MUTATION),
                                surprise=0.8, historical_freq=0.2)
        assert "global" in line.lower()

    # --- has_broad_exception ---

    def test_broad_absent(self):
        line = self._first_line(detector="has_broad_exception", observed=False,
                                context=_ctx(op=Operation.ERROR_HANDLING))
        assert "exception" in line.lower()
        assert "specific" in line.lower()

    def test_broad_present(self):
        line = self._first_line(detector="has_broad_exception", observed=True,
                                context=_ctx(op=Operation.ERROR_HANDLING),
                                surprise=0.8, historical_freq=0.2)
        assert "broad" in line.lower()

    # --- swallows_exception ---

    def test_swallow_absent(self):
        line = self._first_line(detector="swallows_exception", observed=False,
                                context=_ctx(op=Operation.ERROR_HANDLING))
        assert "swallow" in line.lower()

    def test_swallow_present(self):
        line = self._first_line(detector="swallows_exception", observed=True,
                                context=_ctx(op=Operation.ERROR_HANDLING),
                                surprise=0.8, historical_freq=0.2)
        assert "swallow" in line.lower()
        assert "silently" in line.lower()

    # --- unknown detector fallback ---

    def test_unknown_detector_does_not_crash(self):
        line = self._first_line(detector="some_future_detector", observed=False)
        assert len(line) > 0

    def test_unknown_detector_uses_fallback(self):
        line = self._first_line(detector="some_future_detector", observed=False)
        assert "pattern" in line.lower()

    def test_unknown_detector_observed_true_fallback(self):
        line = self._first_line(detector="some_future_detector", observed=True,
                                surprise=0.8, historical_freq=0.2)
        assert "pattern" in line.lower()


# ---------------------------------------------------------------------------
# 3. Norm sentence (sentence 2 - math + labels)
# ---------------------------------------------------------------------------

class TestNormSentence:

    def _second_line(self, **kwargs) -> str:
        return explain([_warning(**kwargs)])[0].message.split("\n")[1]

    # --- percentage rendering ---

    def test_80_percent(self):
        line = self._second_line(historical_freq=0.8, surprise=0.8, sample_size=15)
        assert "80%" in line

    def test_0_percent(self):
        line = self._second_line(historical_freq=0.0, surprise=0.0, sample_size=10)
        assert "0%" in line

    def test_100_percent(self):
        line = self._second_line(historical_freq=1.0, surprise=1.0, sample_size=12)
        assert "100%" in line

    def test_50_percent(self):
        line = self._second_line(historical_freq=0.5, surprise=0.5, sample_size=20)
        assert "50%" in line

    # --- raw count rendering ---

    def test_count_12_out_of_15(self):
        """freq=0.8, sample=15 → round(0.8*15)=12."""
        line = self._second_line(historical_freq=0.8, surprise=0.8, sample_size=15)
        assert "12 out of 15" in line

    def test_count_0_out_of_10(self):
        line = self._second_line(historical_freq=0.0, surprise=0.0, sample_size=10)
        assert "0 out of 10" in line

    def test_count_12_out_of_12(self):
        line = self._second_line(historical_freq=1.0, surprise=1.0, sample_size=12)
        assert "12 out of 12" in line

    def test_count_10_out_of_20(self):
        line = self._second_line(historical_freq=0.5, surprise=0.5, sample_size=20)
        assert "10 out of 20" in line

    # --- location labels ---

    def test_module_level_label(self):
        ctx = _ctx(loc=Location.MODULE_LEVEL)
        line = self._second_line(context=ctx)
        assert "top-level function" in line.lower()

    def test_class_method_label(self):
        ctx = _ctx(loc=Location.CLASS_METHOD)
        line = self._second_line(context=ctx)
        assert "class method" in line.lower()

    def test_nested_function_label(self):
        ctx = _ctx(loc=Location.NESTED_FUNCTION)
        line = self._second_line(context=ctx)
        assert "nested function" in line.lower()

    # --- stability labels ---

    def test_stable_label(self):
        ctx = _ctx(stab=Stability.STABLE)
        line = self._second_line(context=ctx)
        assert "stable" in line.lower()

    def test_modified_label(self):
        ctx = _ctx(stab=Stability.MODIFIED)
        line = self._second_line(context=ctx)
        assert "modified" in line.lower()

    def test_volatile_label(self):
        ctx = _ctx(stab=Stability.VOLATILE)
        line = self._second_line(context=ctx, surprise=0.9, historical_freq=0.9)
        assert "changing" in line.lower()


# ---------------------------------------------------------------------------
# 4. Deviation sentence (sentence 3 - structurally invariant)
# ---------------------------------------------------------------------------

class TestDeviationSentence:

    def test_third_line_present(self):
        lines = explain([_warning()])[0].message.split("\n")
        assert len(lines) == 3

    def test_third_line_contains_unusual(self):
        last_line = explain([_warning()])[0].message.split("\n")[2]
        assert "unusual" in last_line.lower()

    def test_third_line_is_same_for_every_detector(self):
        """Deviation sentence is structurally invariant - same for all detectors."""
        detectors = [
            ("has_timeout_parameter",  Operation.EXTERNAL_CALL),
            ("mutates_parameter",      Operation.MUTATION),
            ("writes_global_state",    Operation.MUTATION),
            ("has_broad_exception",    Operation.ERROR_HANDLING),
            ("swallows_exception",     Operation.ERROR_HANDLING),
        ]
        third_lines = set()
        for det, op in detectors:
            ctx = _ctx(op=op)
            msg = explain([_warning(detector=det, context=ctx)])[0].message
            third_lines.add(msg.split("\n")[2])

        # All third lines must be identical
        assert len(third_lines) == 1


# ---------------------------------------------------------------------------
# 5. Forbidden content - exhaustive scan across all detectors × observed
# ---------------------------------------------------------------------------

class TestForbiddenContent:

    def _all_messages(self) -> list:
        """Generate one message for every (detector, observed) pair."""
        detectors = [
            ("has_timeout_parameter",  Operation.EXTERNAL_CALL),
            ("mutates_parameter",      Operation.MUTATION),
            ("writes_global_state",    Operation.MUTATION),
            ("has_broad_exception",    Operation.ERROR_HANDLING),
            ("swallows_exception",     Operation.ERROR_HANDLING),
        ]
        warnings = []
        for det, op in detectors:
            for obs in (True, False):
                ctx = _ctx(op=op)
                freq = 0.2 if obs else 0.8
                surp = (1.0 - freq) if obs else freq
                warnings.append(_warning(
                    detector=det, context=ctx,
                    observed=obs, historical_freq=freq, surprise=surp,
                ))
        return [e.message for e in explain(warnings)]

    def test_no_should(self):
        for msg in self._all_messages():
            assert "should" not in msg.lower(), f"Forbidden word 'should' in: {msg}"

    def test_no_best_practice(self):
        for msg in self._all_messages():
            assert "best practice" not in msg.lower()

    def test_no_bug(self):
        for msg in self._all_messages():
            assert "bug" not in msg.lower()

    def test_no_fix(self):
        for msg in self._all_messages():
            assert "fix" not in msg.lower()

    def test_no_recommend(self):
        for msg in self._all_messages():
            assert "recommend" not in msg.lower()

    def test_no_error_word(self):
        """'error' as advice/judgment. Note: 'error' in a factual detector name
        observation is fine - we check it doesn't appear as standalone advice."""
        for msg in self._all_messages():
            # "error" in "exception handler" context is factual; block advice forms
            assert "this is an error" not in msg.lower()
            assert "caused an error" not in msg.lower()


# ---------------------------------------------------------------------------
# 6. Immutability - source objects must never be mutated
# ---------------------------------------------------------------------------

class TestImmutability:

    def test_warning_is_same_object(self):
        """The Warning inside the Explanation is the exact same object passed in."""
        w = _warning()
        result = explain([w])
        assert result[0].warning is w

    def test_score_is_same_object(self):
        """SurpriseScore inside Warning is untouched."""
        w = _warning()
        result = explain([w])
        assert result[0].warning.score is w.score

    def test_all_score_fields_unchanged(self):
        """Every field on SurpriseScore must be byte-identical before and after."""
        w = _warning(
            surprise=0.85,
            detector="swallows_exception",
            context=_ctx(op=Operation.ERROR_HANDLING, stab=Stability.STABLE),
            observed=True,
            historical_freq=0.15,
            sample_size=20,
        )
        # Capture field values before
        before = (w.score.detector_name, w.score.observed,
                  w.score.historical_freq, w.score.surprise, w.score.sample_size)

        explain([w])   # run the layer

        # Capture after
        after = (w.score.detector_name, w.score.observed,
                 w.score.historical_freq, w.score.surprise, w.score.sample_size)

        assert before == after


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():
    print("Running explanation layer tests...\n")

    suites = [
        ("Shape",       TestOutputShape),
        ("Observation", TestObservationSentence),
        ("Norm",        TestNormSentence),
        ("Deviation",   TestDeviationSentence),
        ("Forbidden",   TestForbiddenContent),
        ("Immutability",TestImmutability),
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
