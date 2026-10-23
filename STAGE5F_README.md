# Stage 5F — Fail-closed triage disposition and selective accuracy

This update **does not auto-correct misclassifications** and never accesses private labels during inference. The existing `diagnosis.root_cause` is preserved as the **provisional LLM guess** for audit. When `--consistency-guard on` is used, `triage_decision.accepted_root_cause` is `null` if the lab evidence check is anything except supported. Such cases require human review and are not autonomous successes. No tool execution or remediation authorization is added. 

## Install

Back up changed files, then extract this ZIP in your existing project root (containing `pyproject.toml`). Keep `.env` out of Git.

```powershell
python -m pytest tests/test_stage5f_triage.py tests/test_stage5f_graph.py -v
python -m pytest -q
```

To reproduce the existing problematic case (this is a known debugging case, **not** an unbiased benchmark):

```powershell
python scripts/run_agent.py --incident-id INC-0027 --mode openai --base-url http://127.0.0.1:8004 --early-stop on --consistency-guard on --cache off
```

Expect `triage_decision.status=needs_human_review`, `accepted_root_cause=null` **if** the model still disagrees with observed live signatures; a repeated run is stochastic and may differ. This invokes a paid model call.

For future evaluation, run on **new** holdout cases with `--consistency-guard on --capture-trace`. Use a unique output file (no file overwrites), and then:

```powershell
python scripts/analyze_guard_coverage.py --input results/stage5/guarded_new.jsonl --output results/stage5/guarded_new_coverage.json
```

Report **both** autonomous coverage and selective accuracy. A low coverage with high selective accuracy is not necessarily a better system. Scored benchmark examples have private labels written to evaluator output **only after** inference.

The `accepted_in_synthetic_lab` flag is NOT safety authorization for production remediation.
