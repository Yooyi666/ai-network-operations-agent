# Stage 5A — Latency baseline (no Agent behavior changes)

## Purpose

Measure **actual** end-to-end completion latency, error rate, diagnostic accuracy,
mean tool invocations, and HTTP requests *before* making optimisations. The analyzer
is offline. It reads Stage 4 `duration_ms` from evaluation JSONL and makes no API calls.
All percentile values use nearest-rank; p95 over a tiny 5-case run is not stable.

## Add this patch

Extract ZIP to project root. It adds only:
- `scripts/analyze_latency.py`
- `tests/test_latency_analysis.py`
- this document

## Tests and first baseline

```powershell
python -m pytest tests/test_latency_analysis.py -v
python scripts\analyze_latency.py --input results\stage4\stress_v2_openai5.jsonl
```

If the previous evaluation file doesn't exist, verify its path before running.
You can inspect the printed 5-case mean/percentiles, but do not cite them in the resume.

## New DEVELOPMENT (not final holdout) dataset

Generate once (choose a new seed/file if it already exists):

```powershell
python scripts\generate_stress_holdout.py --seed 20261102 --output data\incidents_perf_dev_v2.jsonl
```

In a dedicated PowerShell window (keep running):

```powershell
$env:INCIDENT_DATASET = 'data/incidents_perf_dev_v2.jsonl'
python -m uvicorn netops_agent.api:app --host 127.0.0.1 --port 8003
```

In another PowerShell window (has paid API calls; requires explicit consent):

```powershell
python scripts\evaluate.py --mode openai --dataset data/incidents_perf_dev_v2.jsonl --limit 10 --allow-billed-api --base-url http://127.0.0.1:8003 --output results/stage5/before_10.jsonl
python scripts\analyze_latency.py --input results/stage5/before_10.jsonl --output results/stage5/before_10.latency.json
```

`evaluate.py` explicitly disables cache for fair comparison; verify no incidental
system changes during runs. If OpenAI API fails three times consecutively the run
stops automatically (Stage 4 behavior). API usage is billed by the provider.

For formal p95 work, use 30+ successful samples (prefer 100-200) and repeat runs;
control model version, cache mode, dataset, local hardware, API rate limits,
concurrency, temperature, tool policies and implementation version. Do **not**
claim any particular latency improvement until before/after runs substantiate it.

## Paired comparison (once an optimization has been implemented)

Run the *same* model and dataset IDs with a distinct output file, cache off. Then:

```powershell
python scripts\analyze_latency.py --input results/stage5/before_10.jsonl --compare results/stage5/after_10.jsonl --output results/stage5/comparison.json
```

Comparisons require identical IDs, dataset fingerprint and model name.
The result reports a matched-case p95 difference, plus separate failure rates.
The tool does **not** establish causality because cloud model speed varies over time.

## Fairness

Never tune the final holdout to specific labelled examples. Optimisation should be
measured alongside accuracy: an early-stop policy is unacceptable if it reduces
quality even when it is faster. Current v2 synthetic probes are class-separating;
therefore the benchmark is a controlled simulation, not production evidence.
