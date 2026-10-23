from fastapi.testclient import TestClient

from netops_agent.api import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "incident_count": 200, "version": "0.1.0"}


def test_list_no_ground_truth_leakage():
    payload = client.get("/incidents?limit=5").json()
    assert payload["total"] == 200
    assert len(payload["items"]) == 5
    assert "ground_truth" not in str(payload)


def test_observations_and_diagnostic_no_ground_truth_leakage():
    for endpoint in (
        "/incidents/INC-0001",
        "/incidents/INC-0001/telemetry",
        "/incidents/INC-0001/logs",
    ):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert "ground_truth" not in response.text
    probe = client.post("/incidents/INC-0001/diagnostics/ping")
    assert probe.status_code == 200
    assert "loss_pct" in probe.json()["result"]
    assert "ground_truth" not in probe.text


def test_404_422_and_input_bounds():
    assert client.get("/incidents/INC-9999").status_code == 404
    assert client.get("/incidents?limit=1000").status_code == 422
    assert client.post("/incidents/INC-0001/diagnostics/exec_shell").status_code == 422
