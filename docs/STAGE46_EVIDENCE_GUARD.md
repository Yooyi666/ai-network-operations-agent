# Stage 4.6 — Evidence guard / debugging intervention

## What failed and why
On the inspected stress v2 case, stale CPU telemetry was 90.94%, but the live
CPU process probe reported 35.53% CPU / run_queue 4. The current interface
counters showed 95.04% utilization / 1570 egress discards. A one-probe
LLM diagnosis chose `cpu_saturation`; the true label in the scorer was
`interface_congestion`. The old graph let the LLM stop with no confirmed
cause-specific probe even when live evidence disagreed with telemetry.

## Patch scope
- `src/netops_agent/evidence_guard.py`: public-context and public-probe-only
  backstop. Never imports dataset, simulator ground truth, or private labels.
- `src/netops_agent/agent.py`: if LLM declines to choose further probes while
  no strong live cause-specific evidence exists, schedule one allowed read-only
  probe; remain bounded to 6 different tools.
- `src/netops_agent/agent_engines.py`: prompts prioritize reconciling live
  evidence versus stale telemetry. Only applies automatic fallback to OpenAI
  engine, not mock engine.
- `tests/test_evidence_guard.py`: 7 regression tests with synthetic *public*
  observations and no LLM / network / API key.

## Warnings / scientific integrity
This intervention was developed after inspecting a stress-v2 holdout error,
so the original stress-v2 200 rows are now **development/debugging data**.
Do NOT reuse it as a pristine held-out final score. Generate a newly locked
independent seeded holdout before final claims (and do not inspect labels
until scoring). Run an A/B comparison on identical inputs, fixed model and
version; record both accuracy and median/p95 latency, LLM tokens and tool calls.

These simple positive-evidence thresholds are synthetic demo heuristics. A
positive counter by itself is not production-grade evidence. Real network
monitoring should use deltas/rates, per-interface baselines, time windows,
flap/downtime context, and calibrated uncertainty; a second model diagnosis
may still be incorrect despite the tool guard. Do not claim improved accuracy
until independently verified.

## Windows install
1. Stop any running Agent process (leave your FastAPI simulator running).
2. From project root, back up `src/netops_agent/agent.py` and
   `src/netops_agent/agent_engines.py` (recommended).
3. Extract ZIP into the project root; directories match existing layout.
4. `python -m pytest -q`
5. `python -m pytest tests/test_evidence_guard.py -v`
6. Optional billed validation on a single incident:
   `python scripts/run_agent.py --incident-id INC-0005 --mode openai --base-url http://127.0.0.1:8002 --cache off`
   Save the JSON trace; one more run may produce different results. Comparing
   the same previously exposed case is a regression check, not an unbiased
   evaluation and DOES incur OpenAI API fees.
