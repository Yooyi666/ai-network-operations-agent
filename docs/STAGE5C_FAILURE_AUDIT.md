# Stage 5C — Paired Early-Stopping Error Audit

This is a **read-only, no-network, no-LLM** investigation tool for evaluation results. It does not change the Agent or open ground-truth files at inference time.

From the project root:

```powershell
python -m pytest tests/test_stage5c_audit.py -v
python scripts/audit_early_stop.py --before results/stage5/final_before30.jsonl --after results/stage5/final_after30.jsonl --out-prefix results/stage5/stage5c_audit
```

Outputs:

- `results/stage5/stage5c_audit.json` — transitions (regression, recovery, both wrong, both correct), diagnosis statistics, and early-stop flags.
- `results/stage5/stage5c_audit.csv` — one row per paired incident with before/after predictions, correctness, counts, stop reason and duration.

Review **regression** cases first (`before_correct=true`, `after_correct=false`) and examine whether `early_stop_applied=true` and `stop_reason=confirmed_live_evidence`. A correlation is not a proof of cause. Next, inspect **both incorrect** and **recovery** rows.

**Limitations**: The original evaluation harness does not store complete tool traces in its JSONL output, so this audit cannot show precisely which probes were called. The model's behavior can vary on reruns. Do not optimize thresholds using revealed final holdout labels and claim the same cases as an unbiased benchmark. Use a separate development set for fixes, then regenerate a genuinely unseen final dataset.
