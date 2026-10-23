# Stage 3 — Reliable Network Tool Execution

This is an **additive upgrade** of Stage 2. It preserves the same API, 200 cases, Pydantic Diagnosis schema and LangGraph graph, while replacing the HTTP-facing tool client with `ReliableNetworkClient`.

## Reliability design

- **Input validation:** incident IDs must match `INC-####`; diagnostics use a six-value allowlist. All paths are fixed and read-only. No shell/SSH/arbitrary URL execution.
- **Per-attempt timeout:** default 2.0 seconds enforced with `asyncio.wait_for`, in addition to the HTTPX timeout.
- **Bounded retry:** at most three attempts, exponential backoff (0.05 seconds, 0.1 seconds). Retry 429, 500, 502, 503, 504, and transport/timeout failures. Do **not** retry 400/404/422 and other permanent 4xx responses.
- **Fallback:** an exhausted diagnostic probe becomes a trace event `{"probe": ..., "error": "RetryExhausted", "attempts": 3}`. The agent can finalize from partial evidence. Failed metrics/logs are explicitly tagged `unavailable`; a failed incident summary remains fatal. Response `degraded: true` means some tool or context call failed; it does *not* mean the diagnosis is verified.
- **Caching:** optional in-process `memory` or Redis, 60s TTL by default. Cache only successful JSON responses from the local, synthetic simulator. Redis downtime silently bypasses cache and still uses the live API, with `cache_errors` counting failures. Cached results are tagged `source: cache`. Do not use this TTL policy on real live networks without a freshness/incident-severity policy.
- **Observability:** `reliability` includes HTTP attempts, retries, cache hits, cache errors and failed operations. Probe trace contains execution source and attempt count. The output does not contain private evaluation labels.
- **Security:** `.env` is gitignored. No destructive operations. For a real operational system, do not blindly retry POST operations unless they are confirmed idempotent; the simulated diagnostic POST is read-only and safe to retry.

## Install on Windows / PowerShell

1. Stop the API server (`Ctrl+C`). Back up/commit your Stage 2 work. In project root, overlay the *contents* of `AI_Network_Operations_Agent_Stage3_Update.zip` (without replacing your local `.env`).
2. Activate virtual environment and install: `python -m pip install -e ".[dev]"`.
3. Tests: `python -m pytest -q` — 24 tests expected (14 Stage 2 + 10 Stage 3).
4. Free fault-injection demo: `python scripts\reliability_demo.py` — must finish with `STAGE3 RELIABILITY DEMO: PASS`. This does not need a running API, Redis, or OpenAI API key.
5. Restart API server in terminal 1: `python -m uvicorn netops_agent.api:app --reload`.
6. Run in terminal 2: `python scripts\run_agent.py --incident-id INC-0001 --mode mock --cache off`.
7. Real model, billed: `python scripts\run_agent.py --incident-id INC-0001 --mode openai --cache off`.

## Optional Redis (requires Docker Desktop)

From project root:

```powershell
docker compose up -d redis
docker compose exec redis redis-cli ping
```

The second command should print `PONG`.

Set `REDIS_URL=redis://localhost:6379/0` in `.env` (the `.env.example` contains this). Run:

```powershell
python scripts\run_agent.py --incident-id INC-0001 --mode mock --cache redis
python scripts\run_agent.py --incident-id INC-0001 --mode mock --cache redis
```

Run them quickly (<60 seconds): on the second run, at least the context API calls should hit the cache and `reliability.cache_hits` should be greater than 0. Cache entries expire after the TTL. The default cache mode is `off`; the in-memory mode is process-local and is mainly useful for testing, not persistent caching across agent runs.

Stop only the Redis container when finished: `docker compose stop redis`.

## Reproducible failure scenarios

`python scripts\reliability_demo.py` injects failures into `httpx.AsyncBaseTransport`, forwarding successful HTTP requests to the real FastAPI ASGI app in-process:

| Scenario | What must happen |
|---|---|
| transient 503 (twice) | third try succeeds, 3 requests counted |
| persistent 503 | after 3 attempts, explicit `RetryExhausted`, no infinite loop |
| repeated probe with cache | only first call reaches HTTP backend; second reports `source: cache` |

Tests also cover timeout-and-retry, no retry on 404, invalid inputs, Redis-like cache failure, missing data and partial context.

## Limitations and next stages

- Mock is deterministic and should never be cited as LLM diagnostic accuracy.
- `confidence` is **uncalibrated**; even 0.90 is just a model self-estimate.
- Persistent Redis is tested with Docker on your machine; tests included here run without Redis.
- Retries/caching are implemented on *simulator API tool calls*, not the LLM provider's HTTP call. LLM resilience and checkpointing would be distinct features.
- Neither 87%/72% accuracy nor 6.1s/3.8s p95 has been measured. Stage 4 creates the evaluation harness; Stage 5 benchmarks latency, cache hit rates and LLM call cost.
