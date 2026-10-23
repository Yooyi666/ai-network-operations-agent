# Stage 5D — Evidence Audit & Trace Capture

This is an **observability-only** update. It does not change the classifier,
LangGraph decision policy, thresholds, or benchmark labels. It does not use LLM
APIs except if the user separately runs an `openai` evaluation.

## 1. Inspect the two existing mismatches for free

Keep the original test server bound to the **same** dataset on port 8004:

```powershell
$env:INCIDENT_DATASET = "data/incidents_perf_final_v2.jsonl"
python -m uvicorn netops_agent.api:app --host 127.0.0.1 --port 8004
```

From a second terminal:

```powershell
python scripts/inspect_public_evidence.py --incident-ids INC-0027 INC-0030 --base-url http://127.0.0.1:8004 --output results/stage5/stage5d_public_evidence.json
```

The inspector calls only public GET endpoints and six allowlisted read-only
POST diagnostic endpoints. It produces **no ground-truth labels**. Do not treat
positive signatures as verified real-world root causes; the thresholds are
specific to the synthetic lab.

## 2. Preserve tool traces in a future evaluation (optional, billed)

The evaluator now supports `--capture-trace` for `mock` and `openai` modes.
Choose a NEW output filename (existing JSONL results must not be overwritten).

```powershell
python scripts/evaluate.py --mode openai --dataset data/incidents_perf_final_v2.jsonl --limit 5 --early-stop on --capture-trace --allow-billed-api --base-url http://127.0.0.1:8004 --output results/stage5/trace_smoke5.jsonl
```

This creates `probe_trace` in the case JSONL records so diagnostic output and
`stop_reason` can be audited together. It is **a new model run**, not a
recreation of the original misclassification. There is no need to perform
this paid check before inspecting the free public evidence.

## Note on benchmarking

The two inspected cases are already known failures and therefore part of a
development/debugging set. Any tuned policy must be evaluated on a **new, locked
seed** with new A/B runs. Keep accurate and latency trade-offs separate.
