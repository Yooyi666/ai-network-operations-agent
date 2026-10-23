# Stage 4.5 — Stress Benchmark v2

## Why this benchmark exists
On the locked v1 synthetic holdout, the telemetry-only rule-based baseline scored
200/200 (100%). The v1 dataset was easy and is insufficient to establish any
advantage for an LLM. The 5/5 OpenAI smoke test only validated execution.

## Predefined design (do not tune based on final holdout results)
- 200 cases, balanced: 5 root causes × 40 cases.
- Fixed seed: `20261101`; immutable JSONL, SHA256 recorded.
- Telemetry sometimes stale/missing a strong causal indicator (40% chance).
- Independently, 35% of cases contain an unrelated abnormal telemetry metric.
- Diagnostic logs: primary clue in 70%; unrelated historic clue in 20%.
- One primary fault per incident; non-causal alerts may coexist.
- Six **read-only** live probes; the true fault has a distinctive probe signature.
- Labels held solely in private JSONL, never served via FastAPI endpoints.

## Report all three approaches (avoid unfair claims)
- `baseline`: telemetry-only thresholds (weak information budget).
- `baseline-tools`: rule-based classifier with ALL six diagnostic probes; 6 calls
  per incident; matched *information access*, although compute/call budgets differ.
- `openai`: adaptive probing agent, up to 6 calls; logs + telemetry + probes.

These are **synthetic scenarios**, not independent real incidents; even a 100%
probe-based score does not establish real-world performance. Report probe counts,
error coverage, and latency alongside accuracy. Do not optimize the model or
thresholds using the final holdout; develop using a separate seed. Using
fixed rule signatures in the synthetic probe generator makes the tool-assisted
baseline an intentionally strong upper-bound comparator.

## Command sequence on Windows

First run `python -m pytest -q`; do not continue past failed tests.

```
python scripts/generate_stress_holdout.py
```

Start server in its own PowerShell (use a **different port** from v1):

```
$env:INCIDENT_DATASET = "data/incidents_stress_v2.jsonl"
python -m uvicorn netops_agent.api:app --host 127.0.0.1 --port 8002
```

In a second terminal, run both *free* baseline comparisons:

```
python scripts/evaluate.py --mode baseline --dataset data/incidents_stress_v2.jsonl --all --base-url http://127.0.0.1:8002 --output results/stage4/stress_v2_telemetry.jsonl
python scripts/evaluate.py --mode baseline-tools --dataset data/incidents_stress_v2.jsonl --all --base-url http://127.0.0.1:8002 --output results/stage4/stress_v2_tools.jsonl
```

Only after reviewing the free baselines, a **billed** LLM 5-case smoke test:

```
python scripts/evaluate.py --mode openai --dataset data/incidents_stress_v2.jsonl --limit 5 --allow-billed-api --base-url http://127.0.0.1:8002 --output results/stage4/stress_v2_openai5.jsonl
```

Note: The LLM's previous v1 5-case score is not a v2 performance result.

## Limits / future research
- Logs and probe outputs are intentionally designed, not realistic vendor/device
  traces or sampled from a production incident dataset.
- Primary label is always one of exactly five categories; uncertainty/unknown
  is not supported by the current agent output contract.
- Rule-with-probes baseline uses all six diagnostic probes, while the agent
  can use at most six and may stop earlier. Compare number of tool calls.
- Stronger future challenge: intermittent faults, multiple root causes,
  flaky probes, redacted logs, and out-of-domain incidents.
