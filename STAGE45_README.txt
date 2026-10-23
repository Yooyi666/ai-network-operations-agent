AI Network Operations Agent — Stage 4.5 update (apply over existing Stage 4)

Adds separate synthetic stress dataset generator and two baseline comparison modes.
Does not overwrite the original v1 dataset, .env, Redis settings, or the LLM engine.

Files:
 src/netops_agent/stress_simulator.py    NEW
 src/netops_agent/evaluation.py          MODIFIED
 scripts/generate_stress_holdout.py       NEW
 scripts/evaluate.py                     MODIFIED
 tests/test_stress_benchmark.py          NEW
 docs/STRESS_BENCHMARK_V2.md             NEW

After extracting into your project root:
  python -m pytest -q
  python scripts/generate_stress_holdout.py

For the rest, see docs/STRESS_BENCHMARK_V2.md.

Internal verification on environment with FastAPI/httpx/pytest (without LangGraph):
29 tests passed (API, simulator, evaluation, reliability, stress benchmark).
End-to-end HTTP evaluation with 200 generated v2 cases:
 telemetry-only baseline 108/200 (54%); six-probe rule baseline 200/200 (100%).
These are SYNTHETIC stress-test numbers, not real-world diagnostic accuracy.
A full test run including LangGraph needs to be performed on the user's machine.
