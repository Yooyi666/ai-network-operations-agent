# Stage 5B — Evidence-based Early Stopping (opt-in)

## Motivation

Stage 5A's initial 10 synthetic cases: 10/10 correct, mean 8816.49 ms,
p50 8474.62 ms, p95 9782.34 ms (nearest rank), average 6 probes and 9 HTTP
requests. Small and cloud-API-dependent; not a production latency estimate.

The Stage 4.6 Evidence Guard prevents stopping *too early* when live evidence
is weak, but the LLM can continue selecting probes after sufficient evidence.
Stage 5B adds **opt-in** `--early-stop on` in the graph's decision node.
When a single cause-specific read-only live probe matches the synthetic-lab
signature, the graph skips further planning calls and finalizes once.

Signatures: BGP Idle, optical alarm, DNS timeout, high interface utilization
AND egress discards, high CPU AND run queue. Ping/RTT/loss alone does not count.
Simultaneous positive signatures for different causes disable early stopping.
Probe failure is not treated as affirmative evidence. The six-probe budget,
allowlist, existing retry behavior, and private-label isolation remain.

**Only validated for this synthetic lab.** Do not apply these hardcoded lab
thresholds to real network operations without domain-specific assessment.

## How to run

```powershell
python -m pytest tests/test_early_stop_policy.py tests/test_stage5b_graph.py -v
python -m pytest -q
# 8003 server must still serve data/incidents_perf_dev_v2.jsonl
python scripts/run_agent.py --incident-id INC-0001 --mode openai --base-url http://127.0.0.1:8003 --cache off --early-stop on
```

For a paired comparison with Stage 5A `before_10.jsonl` on the **same dataset**:

```powershell
python scripts/evaluate.py --mode openai --dataset data/incidents_perf_dev_v2.jsonl --limit 10 --early-stop on --allow-billed-api --base-url http://127.0.0.1:8003 --output results/stage5/after_10_early_stop.jsonl
python scripts/analyze_latency.py --input results/stage5/before_10.jsonl --compare results/stage5/after_10_early_stop.jsonl --output results/stage5/compare_10.json
```

The first command makes billed model calls. Check your account budget. Both
runs must be cache=off, same model and dataset hash, same temperature, same
infrastructure. Server must be started with `INCIDENT_DATASET` pointing to
`data/incidents_perf_dev_v2.jsonl`. Compare diagnostic accuracy, error rate,
mean tool calls, mean HTTP calls, and p50/p95 — do not optimize p95 in isolation.

### Optional fresh A/B run with policy toggles

The original `before_10.jsonl` was generated before this flag existed; it is
considered `early_stop=off`. To remeasure with closer temporal proximity, run
with `--early-stop off` into a **new output**, then `--early-stop on` into a
second **new output**. Alternate order across repetitions if budget permits.

`--resume` is protected against mixing early-stop on/off runs. Per-case results
include the `early_stop` setting and (for Agent runs) `stop_reason` and
`early_stop_applied`. This is an end-to-end elapsed-time benchmark, not a
model-only latency measurement. A 10-case p95 is especially unstable.

### Acceptance

1. Offline unit and graph integration tests pass.
2. For a live case with confirmed evidence, `stop_reason` is
   `confirmed_live_evidence`; `tool_calls` must be < 6, and diagnosis remains
   evidence-supported.
3. On paired cases, accuracy must not degrade meaningfully. Investigate all
   incorrect cases, missing evidence, and errors before calling it an improvement.
4. Report actual observed latency change; never assert a target like 3.8s
   without real measurements.
