"""Conservative, public-evidence-only operational triage disposition.

Never treats an LLM prediction as accepted when the evidence guard
reports a contradiction, ambiguity, or absence of confirmatory signatures.
Synthetic-lab signature agreement is not a production root-cause proof.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def decide_disposition(diagnosis: Mapping[str, Any], verification: Mapping[str, Any]) -> dict[str, Any]:
    """Keep raw LLM diagnosis auditable; withhold unsupported automated classification.

    Do NOT infer a replacement root cause from the lab signatures.
    The caller must not autonomously remediate network equipment.
    """
    predicted = diagnosis.get("root_cause")
    status = verification.get("status", "unverified")
    causes = verification.get("live_confirmed_causes", [])
    if not isinstance(causes, (list, tuple)):
        causes = []
    # Trust but verify the provided verification record: fail closed if a
    # caller accidentally supplies an inconsistent `supported` status.
    is_supported = (status == "supported"
                    and verification.get("review_required") is False
                    and isinstance(predicted, str)
                    and len(causes) == 1
                    and causes[0] == predicted)
    return {
        "status": "accepted_in_synthetic_lab" if is_supported else "needs_human_review",
        "accepted_root_cause": predicted if is_supported else None,
        "provisional_root_cause": predicted,
        "public_live_signatures": list(causes),
        "review_required": not is_supported,
        "reason": "single_matching_live_signature" if is_supported else f"evidence_{status}",
        "automatic_remediation_allowed": False,
        "warning": "Synthetic-lab consistency does not certify production diagnosis.",
    }
