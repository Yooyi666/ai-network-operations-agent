"""Public-evidence-only consistency checks for synthetic-lab diagnostics.

Important: positive signatures are heuristic lab checks, NOT proof of real-world
root cause. Never inspect private ground-truth or assign an LLM accuracy label.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .early_stop import confirmed_causes


def verify_prediction(root_cause: str, trace: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report consistency with observed live signatures, no silent relabeling.

    `supported` only means the public *synthetic-lab signature* agrees.
    It does not establish a globally unique real-world cause.
    """
    causes = sorted(confirmed_causes(trace))
    if len(causes) > 1:
        status = 'ambiguous'
    elif not causes:
        status = 'unverified'
    elif root_cause == causes[0]:
        status = 'supported'
    else:
        status = 'contradicted'
    return {
        'status': status,
        'live_confirmed_causes': causes,
        'review_required': status != 'supported',
    }
