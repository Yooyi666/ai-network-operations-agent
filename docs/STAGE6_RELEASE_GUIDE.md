# Stage 6 — Local Docker release and GitHub-ready workflow

This is a **synthetic research/demo application**, not a production network operations system. No remediation commands are executed. The LLM is billed if `--mode openai` is selected.

## Install (Windows PowerShell)

Unzip `AI_Network_Operations_Agent_Stage6_Release_Update.zip` directly into the existing `netops-agent-stage1` project root and confirm that the original `src/`, `scripts/`, `tests/`, and `data/` folders are present.

```powershell
cd C:\path\to\ai-network-operations-agent
.\.venv\Scripts\Activate.ps1
python -m pytest -q
python scripts\release_check.py
docker compose config --quiet
docker compose up --build -d simulator redis
```

Verify independently:

```powershell
docker compose ps
docker compose exec redis redis-cli ping
python scripts\stage6_smoke.py --base-url http://127.0.0.1:8000
docker compose run --rm agent --incident-id INC-0001 --mode mock --cache redis
```

The demo `docker compose run` uses **Docker service networking** and requires no API key.

### Real LLM (optional and billed)

Keep the existing untracked `.env` file in the project root, with `OPENAI_API_KEY=...`. Compose reads `.env` for variable interpolation, and the `agent` container receives the key as an environment variable. Avoid sharing `docker inspect` / environment output. Do not do this in GitHub Actions or on public/untrusted Docker hosts.

```powershell
docker compose run --rm agent --incident-id INC-0001 --mode openai --cache redis --early-stop on --consistency-guard on
```

Results may be `accepted_in_synthetic_lab` or `needs_human_review`. On a review case, **do not treat `diagnosis.root_cause` as accepted**; inspect `triage_decision`.

### Security

- `.env` is excluded from Git and Docker build context.
- Private experiments and locally generated holdouts are excluded from Git and Docker build context.
- Containers bind demo ports only on host loopback; users with Docker administrator access may inspect environment variables.
- The image runs without root privileges and never executes network device remediation.
- Redis persistence is for local demonstration, not production hardening or HA.
- CI does not contact OpenAI and does not require a paid API key.

### Publishing

1. Run static checks and all automated tests locally.
2. Run Docker container and CLI smoke tests.
3. Create a new **public** GitHub repository, but first inspect staged files with `git status --short` and `git diff --cached --name-only`.
4. Push with `git push -u origin main` using an authenticated Git client.
5. Verify the `network-agent-ci` GitHub Actions workflow passes both Python tests and Docker smoke job.
6. Add screenshots of API `/docs` and a **mock mode** diagnosis only; remove any keys/private records.
7. Report the synthetic 30-case model benchmark with coverage and its limitations; do not claim production validation or 200-case OpenAI accuracy.

### Public benchmark (read carefully)

One 30-case synthetic lab validation run (cache off, `gpt-4.1-mini`): raw 29/30; automatically accepted 29/30; accepted diagnoses correct 29/29; human review 1/30; 0 execution failures; mean 4.15s, p50 3.29s, nearest-rank p95 9.06s, max 13.60s; mean 1.53 probes and 4.60 HTTP requests. Small synthetic sample, not production evidence. Different datasets/runs must not be compared as a strict causal experiment.
