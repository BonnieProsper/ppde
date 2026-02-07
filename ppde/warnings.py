"""
Warning Gating - Step 5

Filter, dedup, rank, cap.
Pipeline: filter → dedup → rank → cap
"""
from dataclasses import dataclass
from typing import List

from .context import Stability
from .frequency import SurpriseScore

MIN_SURPRISE  = 0.6
HIGH_SURPRISE = 0.8
MAX_WARNINGS  = 5


@dataclass(frozen=True)
class Warning:
    score: SurpriseScore


_STABILITY_RANK = {
    Stability.STABLE:   0,
    Stability.MODIFIED: 1,
    Stability.VOLATILE: 2,
}


def _passes_threshold(score: SurpriseScore) -> bool:
    return score.surprise >= MIN_SURPRISE


def _passes_stability(score: SurpriseScore) -> bool:
    stability = score.context.stability
    
    if stability == Stability.NEW:
        return False
    
    if stability == Stability.VOLATILE:
        return score.surprise >= HIGH_SURPRISE
    
    return True


def _filter(scores: List[SurpriseScore]) -> List[SurpriseScore]:
    return [s for s in scores if _passes_threshold(s) and _passes_stability(s)]


def _dedup(scores: List[SurpriseScore]) -> List[SurpriseScore]:
    # Exact key dedup
    exact_key: dict[tuple, SurpriseScore] = {}
    for s in scores:
        key = (s.detector_name, s.context)
        if key not in exact_key or s.surprise > exact_key[key].surprise:
            exact_key[key] = s
    
    # Operation collapse
    op_key: dict[tuple, SurpriseScore] = {}
    for s in exact_key.values():
        key = (s.context, s.context.operation)
        if key not in op_key or s.surprise > op_key[key].surprise:
            op_key[key] = s
    
    return list(op_key.values())


def _rank(scores: List[SurpriseScore]) -> List[SurpriseScore]:
    return sorted(
        scores,
        key=lambda s: (
            -s.surprise,
            -s.sample_size,
            _STABILITY_RANK.get(s.context.stability, 99),
        ),
    )


def _cap(scores: List[SurpriseScore]) -> List[SurpriseScore]:
    return scores[:MAX_WARNINGS]


def gate_warnings(scores: List[SurpriseScore]) -> List[Warning]:
    filtered = _filter(scores)
    deduped  = _dedup(filtered)
    ranked   = _rank(deduped)
    capped   = _cap(ranked)
    return [Warning(score=s) for s in capped]
