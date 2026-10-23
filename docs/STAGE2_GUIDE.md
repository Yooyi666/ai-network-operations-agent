# Stage 2 learning and acceptance guide

## What each module does

| File | Role |
|---|---|
| `src/netops_agent/agent_schema.py` | Typed root causes, allowlisted probes, provider-facing diagnostic tool schema, strict Pydantic diagnosis |
| `src/netops_agent/agent_engines.py` | Offline mock (not AI!) vs real OpenAI tool-call + structured-output engine |
| `src/netops_agent/agent.py` | Custom LangGraph StateGraph nodes and safe execution gateway |
| `scripts/run_agent.py` | CLI entrypoint, `.env` loading, JSON output |
| `tests/test_agent.py` | Graph integration tests, no API key needed |

## Understanding INC-0001

Public telemetry reports `bgp_peer_up=0`, ping loss=18.42%, RTT=190.95ms. Logs show `bgpd` moved from Established to Idle. Running a `bgp_status` probe returns `session_state=Idle`. The likely root cause is `bgp_session_down`, not generic congestion.

## Execution sequence

1. **collect**: three concurrent HTTP GET requests for safe incident metadata, telemetry and logs.
2. **decide**: the real model uses an OpenAI-compatible native function-call schema to select a valid named diagnostic probe; offline mock makes a deterministic choice.
3. **probe**: a separate Python node validates the requested name and performs only an allowlisted HTTP request. `incident_id` is not a model argument.
4. **decide again**: model may request another unused probe, subject to a hard limit of six.
5. **finalize**: emits a Pydantic-validated root cause, evidence, estimated confidence, and a proposed follow-up action.

## Safety and limitations

- Read-only synthetic probes; no real SSH, command execution or device configuration changes.
- Stage 2 deliberately has no automatic remediation or external data access.
- The current simulator's five fault classes have distinct telemetry patterns; scores on these synthetic cases would likely overestimate performance in real networks.
- The code limits calls and sets an HTTP request timeout. Stage 3 will implement explicit retries, circuit breakers, cache TTL, full correlation and reliability metrics.
- `mock` is not a language model. Tests passing only prove integration and deterministic business logic; they do not demonstrate AI diagnostic accuracy.
- The model's confidence is **not statistically calibrated** and evidence statements are not yet independently checked against trace contents.

## Acceptance checklist

- [ ] `python -m pytest -q`: all tests pass (expect 14 if deps are compatible)
- [ ] Simulator server responds at `/health`
- [ ] `python scripts/run_agent.py --incident-id INC-0001 --mode mock` yields BGP result and one `bgp_status` tool call
- [ ] `--mode openai` completes when a valid billed model/API key is configured
- [ ] Inspect LLM-selected probe names in `trace`; verify `tool_calls <= 6`
- [ ] Confirm no API key or private `ground_truth` appears in JSON response or Git history

## Troubleshooting

- `ModuleNotFoundError: langgraph`: update project with `python -m pip install -e ".[dev]"` in the correct active virtual environment.
- `Connection refused`: terminal 1 must still be running `python -m uvicorn netops_agent.api:app --reload`.
- `OPENAI_API_KEY is missing`: use `--mode mock`, or set a valid key privately in `.env`.
- `insufficient_quota`, access denied or model not found: check API billing/model entitlements; ChatGPT subscription and API billing are separate.
- Test failure mentioning `INCIDENT_DATASET`: run commands from project root and `python scripts/generate_dataset.py`.
