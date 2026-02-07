"""
Frequency Model - Step 4

Historical pattern frequencies and surprise scores.
Surprise = how often you do the opposite.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .context import PatternContext

MIN_OBSERVATIONS = 10

VIOLATION_DETECTORS = {
    "has_timeout_parameter",
    "mutates_parameter",
    "writes_global_state",
    "has_broad_exception",
    "swallows_exception",
}


@dataclass
class FrequencyTable:
    _counts: Dict[str, Dict[PatternContext, List[int]]] = field(default_factory=dict)

    def record(self, detector_name: str, context: PatternContext, observed: bool):
        if detector_name not in self._counts:
            self._counts[detector_name] = {}
        if context not in self._counts[detector_name]:
            self._counts[detector_name][context] = [0, 0]
        
        idx = 1 if observed else 0
        self._counts[detector_name][context][idx] += 1

    def total_observations(self, detector_name: str, context: PatternContext) -> int:
        if detector_name not in self._counts:
            return 0
        if context not in self._counts[detector_name]:
            return 0
        counts = self._counts[detector_name][context]
        return counts[0] + counts[1]

    def frequency(self, detector_name: str, context: PatternContext) -> Optional[float]:
        total = self.total_observations(detector_name, context)
        if total < MIN_OBSERVATIONS:
            return None
        if total == 0:
            return None
        counts = self._counts[detector_name][context]
        return counts[1] / total


@dataclass(frozen=True)
class SurpriseScore:
    detector_name:   str
    context:         PatternContext
    observed:        bool
    historical_freq: float
    surprise:        float
    sample_size:     int


def compute_surprise(
    detector_name: str,
    context: PatternContext,
    observed: bool,
    table: FrequencyTable,
) -> Optional[SurpriseScore]:
    """
    Compare current observation to historical frequency.
    Returns None if detector is context-only or sample is too sparse.
    """
    if detector_name not in VIOLATION_DETECTORS:
        return None
    
    sample_size = table.total_observations(detector_name, context)
    if sample_size < MIN_OBSERVATIONS:
        return None
    
    historical_freq = table.frequency(detector_name, context)
    if historical_freq is None:
        return None
    
    surprise = historical_freq if not observed else (1.0 - historical_freq)
    
    return SurpriseScore(
        detector_name=detector_name,
        context=context,
        observed=observed,
        historical_freq=historical_freq,
        surprise=surprise,
        sample_size=sample_size,
    )
