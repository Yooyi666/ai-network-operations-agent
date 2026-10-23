"""Stdlib-only local simulator smoke test (does not call an LLM or require API keys)."""
from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def request_json(url: str, method: str = "GET") -> dict:
    req = Request(url=url, method=method)
    with urlopen(req, timeout=8) as response:
        assert response.status == 200, f"Unexpected HTTP {response.status}: {url}"
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    health = request_json(f"{base}/health")
    assert health["status"] == "ok" and health["incident_count"] >= 1, health
    telemetry = request_json(f"{base}/incidents/INC-0001/telemetry")
    assert "telemetry" in telemetry and telemetry["incident_id"] == "INC-0001", telemetry
    logs = request_json(f"{base}/incidents/INC-0001/logs")
    assert isinstance(logs.get("logs"), list), logs
    probe = request_json(f"{base}/incidents/INC-0001/diagnostics/ping", "POST")
    assert probe["probe"] == "ping" and "result" in probe, probe
    print(json.dumps({"status": "PASS", "incidents": health["incident_count"],
                      "checks": ["health", "telemetry", "logs", "ping"]}))


if __name__ == "__main__":
    main()
