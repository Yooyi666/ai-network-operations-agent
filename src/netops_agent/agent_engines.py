"""Two clearly separated planners: deterministic demo vs. actual LLM tool calls."""
from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .agent_schema import Diagnosis, PROBES, RUN_DIAGNOSTIC_TOOL


class AgentEngine(Protocol):
    async def choose_probe(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]], available: list[str],
    ) -> str | None: ...

    async def diagnose(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]],
    ) -> Diagnosis: ...


class MockEngine:
    """Offline deterministic plumbing demo; NOT an LLM and NOT benchmark evidence."""

    @staticmethod
    def _suspected_probe(metrics: dict[str, Any]) -> str:
        if metrics.get("bgp_peer_up") == 0:
            return "bgp_status"
        if metrics.get("optical_rx_dbm", 0) < -20:
            return "optical_power"
        if metrics.get("dns_lookup_ms", 0) > 800:
            return "dns_query"
        if metrics.get("cpu_pct", 0) > 85:
            return "cpu_process"
        if metrics.get("interface_util_pct", 0) > 85:
            return "interface_counters"
        return "ping"

    async def choose_probe(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]], available: list[str],
    ) -> str | None:
        # Exactly one probe is enough to demonstrate graph routing in mock mode.
        if trace:
            return None
        preferred = self._suspected_probe(context["telemetry"]["telemetry"])
        return preferred if preferred in available else (available[0] if available else None)

    async def diagnose(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]],
    ) -> Diagnosis:
        probe_to_label = {
            "dns_query": "dns_resolution_failure",
            "bgp_status": "bgp_session_down",
            "interface_counters": "interface_congestion",
            "cpu_process": "cpu_saturation",
            "optical_power": "optical_link_degradation",
        }
        probe = trace[0]["probe"] if trace else "ping"
        label = probe_to_label.get(probe, "interface_congestion")
        info = trace[0].get("result", {}) if trace else {}
        return Diagnosis(
            incident_id=incident_id,
            root_cause=label,
            confidence=0.6,  # placeholder; do NOT interpret as calibrated confidence
            evidence=[f"Mock heuristic selected probe={probe}; observation={json.dumps(info, sort_keys=True)}"],
            recommended_action="Have a network engineer inspect the relevant device and confirm the suspected issue.",
        )


class OpenAIEngine:
    """Real LLM planner with an independent evidence-confirmation backstop."""

    require_confirmation = True

    def __init__(self, model_name: str | None = None) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Use --mode mock first, or set your "
                "key in a local .env file (never commit it)."
            )
        from langchain_openai import ChatOpenAI

        self.model = ChatOpenAI(
            model=model_name or os.getenv("NETOPS_MODEL_NAME", "gpt-4.1-mini"),
            temperature=0,
            timeout=25,
            max_retries=0,  # Stage 3 adds explicit retry policy and controls.
        )
        self.tool_model = self.model.bind_tools([RUN_DIAGNOSTIC_TOOL], tool_choice="auto")
        self.structured_model = self.model.with_structured_output(Diagnosis)

    async def choose_probe(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]], available: list[str],
    ) -> str | None:
        from langchain_core.messages import HumanMessage, SystemMessage

        if not available:
            return None
        response = await self.tool_model.ainvoke([
            SystemMessage(content=(
                "You are a cautious network incident triage agent. You can use ONE read-only "
                "diagnostic tool per step. Assess the public telemetry and logs. Choose a "
                "diagnostic probe ONLY when it adds confirmatory evidence; otherwise finish. "
                "On the first step, you MUST call run_diagnostic at least once. "
                "Never invent tool results or treat symptoms (like loss) as a root cause "
                "without checking protocol/device evidence. A stale CPU/traffic metric "
                "can conflict with a live probe: if a probe does not support the "
                "suspected root cause, choose another relevant probe before finishing. "
                "A generic ping result is not a root cause confirmation. No remediation actions. "
                "Do not repeat probes. Only use probes in the available list."
            )),
            HumanMessage(content=json.dumps({
                "incident_id": incident_id,
                "public_context": context,
                "completed_probe_results": trace,
                "available_probes": available,
            })),
        ])
        for call in response.tool_calls or []:
            if call.get("name") != "run_diagnostic":
                continue
            probe = call.get("args", {}).get("probe")
            if isinstance(probe, str) and probe in available:
                return probe
        return None

    async def diagnose(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]],
    ) -> Diagnosis:
        from langchain_core.messages import HumanMessage, SystemMessage

        result = await self.structured_model.ainvoke([
            SystemMessage(content=(
                "Diagnose the network incident from public telemetry, logs, and actual probe "
                "outputs. Select exactly one of the five defined root cause categories. "
                "Cite short, concrete evidence points with values. State a sensible read-only "
                "next action (do not claim remediation was executed). Confidence is an "
                "uncalibrated estimate. If probes failed, mention the uncertainty. "
                "If live probes disagree with telemetry, explain the conflict and "
                "prefer independently confirmed live device evidence. A cause-specific "
                "probe that rules a cause out must not be cited as supporting it. "
                "Never invent observations."
            )),
            HumanMessage(content=json.dumps({
                "incident_id": incident_id,
                "public_context": context,
                "probe_trace": trace,
            })),
        ])
        if not isinstance(result, Diagnosis):
            result = Diagnosis.model_validate(result)
        if result.incident_id != incident_id:
            raise ValueError("LLM returned a mismatched incident ID")
        return result


    async def reconsider_diagnosis(
        self, incident_id: str, context: dict[str, Any],
        trace: list[dict[str, Any]], initial: Diagnosis,
        confirmed_causes: list[str],
    ) -> Diagnosis:
        """One bounded LLM review of an evidence contradiction (no labels)."""
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self.structured_model.ainvoke([
            SystemMessage(content=(
                "A previous network fault classification conflicts with an observed "
                "cause-specific LIVE diagnostic signature in this SYNTHETIC LAB. "
                "Reconsider the FULL public evidence independently. Live signatures "
                "are heuristic, not ground truth. Never invent observations or simply "
                "copy a proposed class. If an apparent conflict is explainable, "
                "document why; otherwise select the supported category. "
                "Return a concise grounded explanation and read-only next action."
            )),
            HumanMessage(content=json.dumps({
                "incident_id": incident_id,
                "public_context": context,
                "probe_trace": trace,
                "previous_diagnosis": initial.model_dump(),
                "positive_live_signatures": confirmed_causes,
            })),
        ])
        if not isinstance(response, Diagnosis):
            response = Diagnosis.model_validate(response)
        if response.incident_id != incident_id:
            raise ValueError("LLM recheck returned a mismatched incident ID")
        return response


def make_engine(mode: str) -> AgentEngine:
    if mode == "mock":
        return MockEngine()
    if mode == "openai":
        return OpenAIEngine()
    raise ValueError("mode must be 'mock' or 'openai'")
