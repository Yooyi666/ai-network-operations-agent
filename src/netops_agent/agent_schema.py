"""Public inference schemas. Never import simulator labels or private storage here."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RootCause = Literal[
    "dns_resolution_failure",
    "bgp_session_down",
    "interface_congestion",
    "cpu_saturation",
    "optical_link_degradation",
]

PROBES = (
    "ping",
    "dns_query",
    "bgp_status",
    "interface_counters",
    "cpu_process",
    "optical_power",
)


class Diagnosis(BaseModel):
    """Validated final result; confidence is an estimate, not calibrated."""

    incident_id: str = Field(description="The original investigated incident ID")
    root_cause: RootCause = Field(description="Most probable root cause")
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1, max_length=6)
    recommended_action: str = Field(min_length=8)


# The model can choose a probe, but NEVER supply the incident ID or an API URL.
# A dedicated LangGraph node validates and executes these tool calls.
RUN_DIAGNOSTIC_TOOL = {
    "type": "function",
    "function": {
        "name": "run_diagnostic",
        "description": (
            "Request one READ-ONLY diagnostic probe for the current network incident. "
            "Probe arguments are validated by the service before execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "probe": {
                    "type": "string",
                    "enum": list(PROBES),
                    "description": "The diagnostic probe to run",
                },
                "reason": {
                    "type": "string",
                    "description": "What this measurement would confirm or rule out",
                },
            },
            "required": ["probe", "reason"],
            "additionalProperties": False,
        },
    },
}
