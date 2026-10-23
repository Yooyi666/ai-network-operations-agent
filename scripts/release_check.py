"""Check that public release artifacts exclude known private datasets and secrets."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = [
        "Dockerfile", "docker-compose.yml", ".dockerignore", ".gitignore",
        ".env.example", "README.md", "pyproject.toml",
        ".github/workflows/ci.yml", "data/incidents_v1.jsonl",
        "scripts/run_agent.py", "scripts/stage6_smoke.py",
    ]
    absent = [p for p in required if not (ROOT / p).is_file()]
    if absent:
        raise SystemExit(f"RELEASE CHECK FAILED: missing {absent}")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in gitignore and ".env" in dockerignore
    assert "results/" in gitignore and "results" in dockerignore
    assert "data/incidents_*.jsonl" in gitignore
    assert "data/*.jsonl" in dockerignore
    # Ignore .git if not initialized yet, but enforce tracked-file security on release.
    tracked = subprocess.run(
        ["git", "ls-files", "--cached"], cwd=ROOT, capture_output=True,
        text=True, check=False,
    )
    if tracked.returncode == 0:
        items = [s.replace("\\", "/") for s in tracked.stdout.splitlines()]
        blocked = []
        for name in items:
            if name == ".env" or name.startswith(".env.") and name != ".env.example":
                blocked.append(name)
            if name.startswith(("results/", "backups/", ".venv/")):
                blocked.append(name)
            if name.startswith("data/incidents_") and name != "data/incidents_v1.jsonl":
                blocked.append(name)
        if blocked:
            raise SystemExit(f"RELEASE CHECK FAILED: tracked private artifacts: {blocked}")
    print("STAGE6 RELEASE CHECK: PASS (static checks; run Docker and pytest separately)")


if __name__ == "__main__":
    main()
