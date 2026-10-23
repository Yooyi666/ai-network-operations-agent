FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The image contains only synthetic demo data. No API keys or local .env files.
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY data/incidents_v1.jsonl ./data/incidents_v1.jsonl
RUN python -m pip install --no-cache-dir . \
    && groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /home/appuser --create-home appuser
COPY scripts/ ./scripts/
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "netops_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
