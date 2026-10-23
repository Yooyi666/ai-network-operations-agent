"""FastAPI simulator API. Tools are allowlisted; no arbitrary shell commands."""
from __future__ import annotations

from enum import Enum

from fastapi import FastAPI, HTTPException, Query

from .storage import load_incidents, public_summary

app = FastAPI(title="Network Incident Simulator", version="0.1.0")


class ProbeName(str, Enum):
    ping = "ping"
    dns_query = "dns_query"
    bgp_status = "bgp_status"
    interface_counters = "interface_counters"
    cpu_process = "cpu_process"
    optical_power = "optical_power"


def _get_case(incident_id: str) -> dict:
    case = load_incidents().get(incident_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return case


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "incident_count": len(load_incidents()), "version": "0.1.0"}


@app.get("/incidents")
def list_incidents(limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    cases = list(load_incidents().values())
    return {"total": len(cases), "items": [public_summary(c) for c in cases[offset:offset + limit]]}


@app.get("/incidents/{incident_id}")
def incident(incident_id: str) -> dict:
    return public_summary(_get_case(incident_id))


@app.get("/incidents/{incident_id}/telemetry")
def telemetry(incident_id: str) -> dict:
    return {"incident_id": incident_id, "telemetry": _get_case(incident_id)["telemetry"]}


@app.get("/incidents/{incident_id}/logs")
def logs(incident_id: str, limit: int = Query(20, ge=1, le=100)) -> dict:
    return {"incident_id": incident_id, "logs": _get_case(incident_id)["logs"][:limit]}


@app.post("/incidents/{incident_id}/diagnostics/{probe}")
def run_diagnostic(incident_id: str, probe: ProbeName) -> dict:
    result = _get_case(incident_id)["probes"][probe.value]
    return {"incident_id": incident_id, "probe": probe.value, "result": result}
