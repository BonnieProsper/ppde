"""
Explanation Layer - Step 6

Translate Warnings to human-readable text.
Three sentences: what happened, what's normal, why it's unusual.
"""
from dataclasses import dataclass
from typing import List

from .context import Location, Stability
from .frequency import SurpriseScore
from .warnings import Warning


@dataclass(frozen=True)
class Explanation:
    warning: Warning
    message: str


_OBSERVATION = {
    ("has_timeout_parameter", False): "This call does not specify a timeout.",
    ("has_timeout_parameter", True):  "This call specifies a timeout.",
    ("mutates_parameter",     False): "This function does not reassign any of its parameters.",
    ("mutates_parameter",     True):  "This function reassigns one or more of its parameters.",
    ("writes_global_state",   False): "This function does not write to global state.",
    ("writes_global_state",   True):  "This function writes to global state.",
    ("has_broad_exception",   False): "This exception handler catches a specific exception type.",
    ("has_broad_exception",   True):  "This exception handler catches a broad exception type.",
    ("swallows_exception",    False): "This exception handler does not swallow the exception.",
    ("swallows_exception",    True):  "This exception handler swallows the exception silently.",
}

_OBSERVATION_FALLBACK = {
    False: "The pattern was not detected here.",
    True:  "The pattern was detected here.",
}

_LOCATION_LABEL = {
    Location.MODULE_LEVEL:    "a top-level function",
    Location.CLASS_METHOD:    "a class method",
    Location.NESTED_FUNCTION: "a nested function",
}

_STABILITY_LABEL = {
    Stability.NEW:      "a recently created file",
    Stability.VOLATILE: "a frequently changing file",
    Stability.MODIFIED: "a recently modified file",
    Stability.STABLE:   "a stable file",
}


def _sentence_observation(score: SurpriseScore) -> str:
    key = (score.detector_name, score.observed)
    return _OBSERVATION.get(key, _OBSERVATION_FALLBACK[score.observed])


def _sentence_norm(score: SurpriseScore) -> str:
    true_count = round(score.historical_freq * score.sample_size)
    pct = f"{score.historical_freq:.0%}"
    
    loc_label  = _LOCATION_LABEL.get(score.context.location,  "this context")
    stab_label = _STABILITY_LABEL.get(score.context.stability, "this file")
    
    return (
        f"In {loc_label} within {stab_label}, "
        f"this pattern is present {pct} of the time "
        f"({true_count} out of {score.sample_size})."
    )


def _sentence_deviation() -> str:
    return "This deviation is unusual for you."


def _build_message(score: SurpriseScore) -> str:
    return "\n".join([
        _sentence_observation(score),
        _sentence_norm(score),
        _sentence_deviation(),
    ])


def explain(warnings: List[Warning]) -> List[Explanation]:
    return [
        Explanation(warning=w, message=_build_message(w.score))
        for w in warnings
    ]
