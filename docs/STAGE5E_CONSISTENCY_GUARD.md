# Stage 5E — Evidence consistency guard (opt-in)

## Design

Public, synthetic-lab, allowlisted read-only signatures provide a consistency
check for the final LLM diagnosis. When **exactly one** confirmed live fault
signature contradicts the LLM diagnosis, the OpenAI engine gets **at most one**
reconsideration. If it still disagrees, the LLM's classification is preserved
and `review_required=true` is reported; no silent relabeling or falsely
passing a test. Multiple positive signatures or no positive signature require
review. The optional guard changes the LLM call count and is **not free**.

The guard does **not** fetch unobserved probes and cannot verify a cause that
wasn't measured. `supported` means agreement with a synthetic signature, not
real-world truth. All diagnostics stay read-only; the system does not access
private labels. Default `off` preserves Stage 5B benchmark comparability.

## Step 1 — Free offline demonstration

```powershell
python scripts\audit_consistency.py --public-report results\stage5\stage5d_public_evidence.json --prediction INC-0027=interface_congestion INC-0030=cpu_saturation --output results\stage5\stage5e_consistency_audit.json
```

This evaluates old model predictions against *all public probes obtained
later*, **not** the exact probes used during the prior model run.

## Step 2 — Offline tests

```powershell
python -m pytest tests\test_stage5e_verifier.py tests\test_stage5e_graph.py -v
python -m pytest -q
```

## Step 3 — New, optional paid single-case Agent run

```powershell
python scripts\run_agent.py --incident-id INC-0027 --mode openai --base-url http://127.0.0.1:8004 --early-stop on --consistency-guard on --cache off
```

Requires the simulator on port 8004 and a valid API key. This is a new
stochastic run; it will not reproduce the original LLM's decisions. The new
`diagnosis_verification` field indicates rechecks and review status.

## Evaluation ethics

Once the two past holdout labels were inspected, they became development
examples. Any revised policy needs a fresh seeded holdout for final metrics.
Compared to `consistency_guard=off`, enabling it can add a SECOND LLM
classification call on contradictions. Measure both latency and accuracy,
and count review-required cases separately. Synthetic benchmarks are not
production accuracy guarantees.
