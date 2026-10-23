# Publish this repository to GitHub (Windows PowerShell)

This package contains the **complete source project**, not a patch. Extract it first; do not upload the ZIP file as a single repository file. GitHub does not automatically expand uploaded ZIP archives into source files.

## 1. Unzip and review

Extract `ai-network-operations-agent-github-ready.zip` in Downloads. Open the extracted `ai-network-operations-agent` directory in VS Code. The directory should contain `README.md`, `pyproject.toml`, `Dockerfile`, `.github/`, `src/`, `scripts/`, and `tests/` **at its top level**.

The ZIP does **not** contain `.env`, API keys, `.venv/`, the `results/` folder, backup copies, or private holdouts. It **does** include a labelled **synthetic** demo dataset, `data/incidents_v1.jsonl`.

## 2. Smoke test (Docker Desktop Engine must be running)

```powershell
cd "$HOME\Downloads\ai-network-operations-agent"
docker compose config --quiet
docker compose up --build -d simulator redis
docker compose exec redis redis-cli ping
docker compose run --rm agent --incident-id INC-0001 --mode mock --cache redis
```

`PONG` and a JSON diagnosis mean container connectivity works. No OpenAI API Key is required for the mock test.

For native Python tests:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts\release_check.py
```

## 3. Create an empty GitHub repository

Open <https://github.com/new>. Repository name: **ai-network-operations-agent**. Add the description shown in `README.md`. Choose Public **only after reviewing the files**. **Do not** select "Add a README", ".gitignore", or "Choose a license" on the creation page, because this package already supplies the first two. You may add a license later after choosing terms deliberately.

## 4. Push via Git (recommended, preserves `.github` and hidden files)

From the extracted project root:

```powershell
git init
git branch -M main
git add .
git status --short
git diff --cached --name-only
```

**Inspect the staged file list.** It must not include `.env`, secrets, `.venv/`, `results/`, `backups/`, or any non-demo dataset. If you see a real key, remove it before commit and rotate/revoke the key if it was already exposed.

Then commit:

```powershell
git commit -m "Initial release: AI network operations agent"
```

Copy **your own empty repository's HTTPS URL** from GitHub (do not copy anyone else's). Use:

```powershell
git remote add origin YOUR_REPOSITORY_HTTPS_URL
git push -u origin main
```

GitHub sign-in/authentication may be requested. Replace `YOUR_REPOSITORY_HTTPS_URL` with the exact HTTPS URL of the repository you created.

## 5. Final checks on GitHub

- `README.md` displays the architecture and **30-case synthetic** performance evidence with its limitations.
- `.github/workflows/ci.yml` appears under **Actions**. Wait for the Python tests and Docker smoke check to complete; fix any failures before claiming CI green.
- Confirm `.env`, API keys, local backups, experiment results, and non-demo holdouts **do not appear** in the public files or commit history.
- A public GitHub repository with no license does not grant blanket reuse rights. Choose a license separately if you want open-source reuse.

## Security and benchmarking disclaimer

This is a read-only synthetic lab, **not** a production incident-response system. `mock` mode is not LLM inference. Report the evaluated 30-case LLM accuracy and selective accuracy along with sample sizes; do **not** claim 200-case LLM accuracy, 87% vs 72%, or p95 6.1s to 3.8s. Do not upload real network telemetry or secrets to a public repository.
