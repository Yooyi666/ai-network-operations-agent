"""Bounded LangGraph execution, communicating only with PUBLIC simulator APIs."""
from __future__ import annotations

import asyncio
import re
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from .agent_engines import AgentEngine
from .agent_schema import PROBES
from .evidence_guard import next_confirmation_probe
from .early_stop import is_early_stop_safe
from .diagnosis_verifier import verify_prediction
from .triage_decision import decide_disposition
from .reliable_client import RetryExhausted

MAX_TOOL_CALLS = 6
INCIDENT_ID_PATTERN = re.compile(r"^INC-\d{4}$")


class AgentState(TypedDict, total=False):
    incident_id: str
    context: dict[str, Any]
    trace: list[dict[str, Any]]
    used_probes: list[str]
    next_probe: str | None
    diagnosis: dict[str, Any]
    stop_reason: str | None
    diagnosis_verification: dict[str, Any]


class PublicNetworkClient:
    """Typed, read-only allowlist. No shell, arbitrary URLs, or secret labels."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    @staticmethod
    def validate_incident_id(incident_id: str) -> None:
        if not INCIDENT_ID_PATTERN.fullmatch(incident_id):
            raise ValueError("Invalid incident ID. Expected e.g. INC-0001")

    async def _get(self, path: str) -> dict[str, Any]:
        response = await self.http.get(path)
        response.raise_for_status()
        return response.json()

    async def context(self, incident_id: str) -> dict[str, Any]:
        self.validate_incident_id(incident_id)
        # Independent PUBLIC API calls happen concurrently.
        summary, telemetry, logs = await asyncio.gather(
            self._get(f"/incidents/{incident_id}"),
            self._get(f"/incidents/{incident_id}/telemetry"),
            self._get(f"/incidents/{incident_id}/logs"),
        )
        return {"summary": summary, "telemetry": telemetry, "logs": logs}

    async def diagnostic(self, incident_id: str, probe: str) -> dict[str, Any]:
        self.validate_incident_id(incident_id)
        if probe not in PROBES:
            raise ValueError(f"Unapproved probe: {probe}")
        response = await self.http.post(f"/incidents/{incident_id}/diagnostics/{probe}")
        response.raise_for_status()
        return response.json()


def build_graph(client: PublicNetworkClient, engine: AgentEngine, *, early_stop: bool = False,
                consistency_guard: bool = False):
    """START -> collect -> decide -> [probe -> decide]* -> final -> END."""

    async def collect(state: AgentState) -> dict[str, Any]:
        context = await client.context(state["incident_id"])
        return {"context": context, "trace": [], "used_probes": [], "next_probe": None, "stop_reason": None}

    async def decide(state: AgentState) -> dict[str, Any]:
        available = [probe for probe in PROBES if probe not in state["used_probes"]]
        if len(state["used_probes"]) >= MAX_TOOL_CALLS or not available:
            return {"next_probe": None, "stop_reason": "tool_budget"}
        # In opt-in mode, stop BEFORE another LLM planner round-trip if a
        # single specific cause is already established by live device evidence.
        # Avoid the early stop if independent probes support conflicting causes.
        # Mock mode and legacy runs retain their original behavior.
        if (early_stop and getattr(engine, "require_confirmation", False)
                and is_early_stop_safe(state["trace"])):
            return {"next_probe": None, "stop_reason": "confirmed_live_evidence"}
        proposed = await engine.choose_probe(
            state["incident_id"], state["context"], state["trace"], available
        )
        # Require one valid probe even when model refuses or makes an invalid call.
        # A preselected, fixed read-only fallback is safer than arbitrary execution.
        if proposed not in available:
            if not state["trace"]:
                proposed = "ping" if "ping" in available else None
            elif getattr(engine, "require_confirmation", False):
                # An LLM may stop after a misleading telemetry alert or a
                # *negative* live probe. Gather independent cause-specific
                # evidence before trusting its diagnosis (bounded by 6 calls).
                # The mock planner stays unchanged for reproducible demo tests.
                proposed = next_confirmation_probe(
                    state["context"], state["trace"], available
                )
            else:
                proposed = None
        return {"next_probe": proposed, "stop_reason": "planner_finished" if proposed is None else None}

    def route(state: AgentState) -> str:
        return "probe" if state.get("next_probe") else "finalize"

    async def probe(state: AgentState) -> dict[str, Any]:
        name = state["next_probe"]
        if name not in PROBES or name in state["used_probes"]:
            raise ValueError("Invalid, unsafe, or duplicate tool execution requested")
        # Each tool call is bounded by httpx timeout and the graph's max steps.
        try:
            payload = await client.diagnostic(state["incident_id"], name)
            event = {"probe": name, "result": payload["result"]}
            if "_netops" in payload:
                event["execution"] = payload["_netops"]
        except (httpx.HTTPError, KeyError, ValueError, RetryExhausted) as exc:
            # Fail closed: record tool failure rather than treating it as evidence.
            event = {"probe": name, "error": type(exc).__name__}
            if isinstance(exc, RetryExhausted):
                event["attempts"] = exc.attempts
        return {
            "trace": [*state["trace"], event],
            "used_probes": [*state["used_probes"], name],
            "next_probe": None,
        }

    async def finalize(state: AgentState) -> dict[str, Any]:
        diagnosis = await engine.diagnose(
            state["incident_id"], state["context"], state["trace"]
        )
        if diagnosis.incident_id != state["incident_id"]:
            raise ValueError("Diagnosis incident_id mismatch")
        if not consistency_guard:
            return {"diagnosis": diagnosis.model_dump()}
        initial_prediction = diagnosis.root_cause
        check = verify_prediction(initial_prediction, state["trace"])
        recheck_used = False
        recheck_error = None
        # One bounded reconsideration, only on directly contradictory PUBLIC
        # evidence; never use labels, never overwrite a prediction by fiat.
        if (check["status"] == "contradicted"
                and getattr(engine, "require_confirmation", False)
                and callable(getattr(engine, "reconsider_diagnosis", None))):
            recheck_used = True
            try:
                revised = await engine.reconsider_diagnosis(
                    state["incident_id"], state["context"], state["trace"],
                    diagnosis, check["live_confirmed_causes"],
                )
                if revised.incident_id != state["incident_id"]:
                    raise ValueError("Recheck incident ID mismatch")
                diagnosis = revised
                check = verify_prediction(diagnosis.root_cause, state["trace"])
            except Exception as exc:
                # LLM/API errors during recheck must NOT suppress the original
                # finding, nor turn an unverified classification into a pass.
                recheck_error = type(exc).__name__
        check.update({
            "initial_prediction": initial_prediction,
            "final_prediction": diagnosis.root_cause,
            "recheck_used": recheck_used,
            "recheck_error": recheck_error,
            "note": "Synthetic-lab signature agreement is not production-grade verification.",
        })
        return {"diagnosis": diagnosis.model_dump(), "diagnosis_verification": check}

    graph = StateGraph(AgentState)
    graph.add_node("collect", collect)
    graph.add_node("decide", decide)
    graph.add_node("probe", probe)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "collect")
    graph.add_edge("collect", "decide")
    graph.add_conditional_edges("decide", route, {"probe": "probe", "finalize": "finalize"})
    graph.add_edge("probe", "decide")
    graph.add_edge("finalize", END)
    return graph.compile()


async def investigate(
    incident_id: str, client: PublicNetworkClient, engine: AgentEngine,
    *, early_stop: bool = False, consistency_guard: bool = False,
) -> dict[str, Any]:
    client.validate_incident_id(incident_id)
    graph = build_graph(client, engine, early_stop=early_stop,
                        consistency_guard=consistency_guard)
    state = await graph.ainvoke({"incident_id": incident_id}, config={"recursion_limit": 25})
    degraded = bool(state["context"].get("collection_errors")) or any(
        "error" in event for event in state["trace"]
    )
    result = {
        "incident_id": incident_id,
        "diagnosis": state["diagnosis"],
        "tool_calls": len(state["trace"]),
        "trace": state["trace"],
        "degraded": degraded,
        "early_stop_enabled": early_stop,
        "early_stop_applied": state.get("stop_reason") == "confirmed_live_evidence",
        "stop_reason": state.get("stop_reason"),
    }
    if consistency_guard:
        result["diagnosis_verification"] = state["diagnosis_verification"]
        result["review_required"] = state["diagnosis_verification"]["review_required"]
        result["triage_decision"] = decide_disposition(state["diagnosis"], state["diagnosis_verification"])
    if hasattr(client, "stats"):
        result["reliability"] = dict(client.stats)
    return result
