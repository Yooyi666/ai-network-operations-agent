# Engineering project spec

## Goal
Investigate network incidents using a bounded, tool-using LangGraph agent and compare with a rule-based baseline.

## Problem framing
A network engineer sees an incident ID, telemetry, logs and safe diagnostic probes. The agent must infer the most likely root cause from evidence and return a structured explanation. This is a *synthetic incident lab*, not a production network operations integration.

## Labels
`dns_resolution_failure`, `bgp_session_down`, `interface_congestion`, `cpu_saturation`, `optical_link_degradation`.

## Separation of concerns
- `data/incidents_v1.jsonl`: evaluation-only file with hidden `ground_truth`. Device IDs are randomized across labels so they do not encode the answer.
- Simulator HTTP API: public incident metadata, telemetry, logs, six allowlisted diagnostic probes. Never expose `ground_truth`.
- Stage 2 agent: consume *only* public API, do not import `storage` or read JSONL.
- Stage 4 evaluator: may read `ground_truth` to score predictions after the fact.

## Planned LangGraph control flow
`START -> context -> triage -> [tool selection -> bounded execution -> evidence accumulation -> triage] -> structured diagnosis -> END`.
- Strict maximum tool calls, allowlisted read-only probes, validated parameters.
- Deadline/timeout per tool, bounded retries only for transient errors, fallback to partial evidence.
- No command execution, SSH access, device configuration changes or uncontrolled code execution.

## Roadmap & acceptance criteria
1. **Stage 1: simulator + API (provided)**: 200 seeded synthetic cases, 5 categories x 40, FastAPI endpoints, unit tests, Docker/Redis scaffold.
2. **Stage 2: real AI agent**: LangGraph StateGraph nodes/edges, model tool selection, typed JSON diagnosis, evidence traces, max 6 tool calls. Demo at least 5 incident types.
3. **Stage 3: robust tool gateway**: input validation, timeouts, bounded retries/backoff, circuit breaker, Redis TTL evidence cache, correlation IDs.
4. **Stage 4: evaluation**: rule baseline and LLM agent on locked cases; 200 scored incidents; full confusion matrix, exact-match accuracy, confidence intervals, failure taxonomy.
5. **Stage 5: profiling**: capture wall-clock end-to-end latency across a specified workload, with cold/warm cache and tool costs, report p50/p95 (same inputs and concurrency before/after).
6. **Stage 6: release**: Docker Compose full stack, integration tests, CI, architecture diagram, example traces, evaluated README, public GitHub.

## Measurement hygiene
- 200 labelled examples is dataset size, not evidence of accuracy.
- Never claim `87%`, `72%`, `6.1s` or `3.8s` until *your own run* produces them.
- Keep inference code blind to `ground_truth` and avoid per-case hardcoded answers.
- Stratify train/development/evaluation to avoid prompt tuning on locked test cases. A final score on a 200-case test set requires a separate dev set or explicit caveat that 200 was used for evaluation and tuning.
- Record model version, model parameters, dataset version/seed, sample size, warmup policy, concurrency, hardware and cache state.
