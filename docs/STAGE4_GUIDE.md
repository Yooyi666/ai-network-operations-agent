# Stage 4 — Auditable evaluation (Windows PowerShell)

This stage adds a NEW 200-case **holdout dataset** (seed `20261022`). Stage 1's seed-42 dataset is a **development dataset** whose labels/features may already have been inspected. Do not tune a prompt on the new holdout after looking at its test scores and then report the tuned score as independent.

## Engineering guarantees

- Agent and baseline receive only the public FastAPI context and probes. The Python evaluator reads the private `ground_truth` **after prediction** to score it.
- The holdout simulator must serve `data/incidents_holdout_v1.jsonl` on port 8001. A preflight compares five cases' exact public telemetry against the private evaluation file; it REFUSES a mismatched dataset.
- `--mode openai` requires `--allow-billed-api`; `--all` is mandatory for 200 cases (default is only five). Each case could use many billable model calls; even 200 cases could imply over a thousand model invocations depending on tool choice. Cost depends on actual model/token consumption.
- **Caching is turned OFF** during evaluation, regardless of Redis status. Existing `INC-XXXX` IDs appear in both datasets: Redis keys in Stage 3 lack a dataset-version namespace, so cache reuse could contaminate the experiment.
- Predictions, errors, per-case duration, dataset SHA-256 and a full confusion matrix are saved under `results/stage4/`. An interrupted run can resume using the same output path and `--resume`.
- Cases with a missing prediction or runtime error are **incorrect**, not silently removed. After 3 consecutive errors, evaluation stops to limit API waste; partial data can be resumed.
- A 95% Wilson interval is displayed for descriptive purposes only; synthetic labels are not independent real-world observations.

## 1) Install Stage 4 files

Stop FastAPI before changing versions. Apply the increment ZIP over the existing Stage 3 project root, preserving `.env`, then:

```powershell
cd "C:\path\to\ai-network-operations-agent"
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 2) Generate the holdout (only ONCE)

```powershell
python scripts\generate_holdout.py
```

Expected: `Generated 200 holdout cases`, a SHA256 checksum. Existing holdout file will not be replaced by default.

## 3) Start a SEPARATE simulator for holdout data (PowerShell terminal A)

```powershell
cd "C:\path\to\ai-network-operations-agent"
.\.venv\Scripts\Activate.ps1
$env:INCIDENT_DATASET = "data/incidents_holdout_v1.jsonl"
python -m uvicorn netops_agent.api:app --host 127.0.0.1 --port 8001
```

Leave this terminal open. Stage 1 original simulator can remain at port 8000. Do **not** reuse port 8000 accidentally; wrong data are blocked by the evaluator's consistency check.

## 4) Run baseline first, free, in terminal B

```powershell
cd "C:\path\to\ai-network-operations-agent"
.\.venv\Scripts\Activate.ps1
python scripts\evaluate.py --mode baseline --all --base-url http://127.0.0.1:8001 --output results/stage4/baseline_holdout.jsonl
```

Expected baseline results may be **100%**: the five label classes are intentionally distinguishable via direct, non-overlapping thresholds. This is a simulator design limitation, **not** evidence that an AI model adds incremental diagnostic accuracy. Do not fabricate or target a 72% baseline.

## 5) Smoke-test real LLM (PAID, 5 holdout cases)

Only after baseline works and you have reviewed API spend and limits:

```powershell
python scripts\evaluate.py --mode openai --limit 5 --allow-billed-api --base-url http://127.0.0.1:8001 --output results/stage4/openai_smoke5.jsonl
```

This five-case sample is **integration smoke test only**, not a reliable estimate of accuracy. Do not tune the model on the smoke case labels then use the full holdout score as an independent test.

To evaluate all 200 (PAID; optional):

```powershell
python scripts\evaluate.py --mode openai --all --allow-billed-api --base-url http://127.0.0.1:8001 --output results/stage4/openai_holdout200.jsonl
```

To resume **after a fix or interruption** without re-billing already scored cases, repeat the same command and add `--resume`. Results are per-case JSONL; the summary is `.summary.json` and confusion matrix `.confusion.csv`.

## 6) What to report accurately

- `accuracy` = correct root-cause predictions / *all evaluated cases* (including failed cases)
- `coverage` = non-error responses / evaluated cases
- `confusion_matrix` = error distribution across five labels, plus unknown/error predictions
- `dataset_sha256` = dataset identity for reproducibility
- `model` = configured model name, `cache=off`, timestamp, latency (descriptive only, Stage 5 benchmark comes later)

**Scientific limitation:** dataset generator v1 makes individual root causes almost trivially separable (e.g., `bgp_peer_up=0`, `dns_lookup_ms>800`, `optical_rx_dbm<-20`, `cpu_pct>85`, `interface_util_pct>85`). A realistic next extension is a **harder v2** dataset with ambiguous alerts, co-occurring incidents, partial logs, sensor noise and feature overlap, plus a separate untouched holdout. Compare results there instead of handicapping the baseline to hit a preselected 72% number.

## Debugging

- `DATASET MISMATCH`: wrong port or server started without `INCIDENT_DATASET` pointing to the holdout.
- `Connection refused`: the terminal A server isn't running or port 8001 is unavailable.
- `RuntimeError: OPENAI_API_KEY is missing`: keep the key in local `.env` only. Do not paste it into chat or commit it.
- `401`, `429`: billing/auth or rate limits; fix before resuming. Do not spam paid attempts.
- `Result file exists`: choose another file or use `--resume` with **the same dataset, mode and model**; never combine incompatible experiments.
