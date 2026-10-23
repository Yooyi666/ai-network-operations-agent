"""Stage 3: bounded read-only HTTP tool execution with optional, degradable caching.

Safe for the *synthetic* simulator. Never retry non-idempotent real production
operations without idempotency keys / an explicit safety policy.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .agent_schema import PROBES

_INCIDENT_ID = re.compile(r"^INC-\d{4}$")
_RETRYABLE_HTTP = frozenset({429, 500, 502, 503, 504})


class AsyncCache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    timeout_seconds: float = 2.0
    base_backoff_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not 1 <= self.attempts <= 5:
            raise ValueError("attempts must be between 1 and 5")
        if not 0.01 <= self.timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0.01 and 30")
        if not 0 <= self.base_backoff_seconds <= 2:
            raise ValueError("base_backoff_seconds must be between 0 and 2")


class RetryExhausted(RuntimeError):
    def __init__(self, attempts: int, cause: Exception):
        self.attempts = attempts
        self.cause_type = type(cause).__name__
        super().__init__(f"network tool failed after {attempts} attempts ({self.cause_type})")


class MemoryCache:
    """TTL cache for local demo/tests. Not persistent across processes."""

    def __init__(self):
        self.items: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> str | None:
        value = self.items.get(key)
        if value is None:
            return None
        expires, payload = value
        if time.monotonic() >= expires:
            self.items.pop(key, None)
            return None
        return payload

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.items[key] = (time.monotonic() + ttl_seconds, value)

    async def close(self) -> None:
        self.items.clear()


class RedisCache:
    """Optional redis.asyncio wrapper. Never store credentials or ground-truth labels."""

    def __init__(self, url: str):
        from redis.asyncio import Redis

        self.redis = Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=0.2,
            socket_timeout=0.2, health_check_interval=20,
        )

    async def get(self, key: str) -> str | None:
        return await self.redis.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self.redis.set(key, value, ex=ttl_seconds)

    async def close(self) -> None:
        await self.redis.aclose()


class ReliableNetworkClient:
    """Drop-in replacement for Stage 2 PublicNetworkClient.

    Uses only fixed endpoints derived from a validated incident ID and probe enum.
    Concurrent context collection can degrade when logs/metrics are unavailable;
    incident summary remains mandatory. Errors are surfaced, never disguised as
    successful diagnostic evidence.
    """

    def __init__(
        self, http: httpx.AsyncClient, policy: RetryPolicy | None = None,
        cache: AsyncCache | None = None, cache_ttl_seconds: int = 60,
    ):
        if not 1 <= cache_ttl_seconds <= 3600:
            raise ValueError("cache_ttl_seconds must be between 1 and 3600")
        self.http = http
        self.policy = policy or RetryPolicy()
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.stats = {
            "http_requests": 0, "retries": 0, "cache_hits": 0,
            "cache_errors": 0, "failed_operations": 0,
        }

    @staticmethod
    def validate_incident_id(incident_id: str) -> None:
        if not _INCIDENT_ID.fullmatch(incident_id):
            raise ValueError("Invalid incident ID. Expected e.g. INC-0001")

    async def _cached(self, key: str) -> dict[str, Any] | None:
        if self.cache is None:
            return None
        try:
            value = await asyncio.wait_for(self.cache.get(key), timeout=0.4)
            if value is not None:
                decoded = json.loads(value)
                if isinstance(decoded, dict):
                    self.stats["cache_hits"] += 1
                    return decoded
        except Exception:  # Redis failing must not block diagnostic reads
            self.stats["cache_errors"] += 1
        return None

    async def _store(self, key: str, payload: dict[str, Any]) -> None:
        if self.cache is None:
            return
        try:
            await asyncio.wait_for(
                self.cache.set(key, json.dumps(payload), self.cache_ttl_seconds),
                timeout=0.4,
            )
        except Exception:
            self.stats["cache_errors"] += 1

    async def _request(self, method: str, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Retry only transient transport errors/statuses and enforce per-attempt timeout."""
        if method not in {"GET", "POST"}:
            raise ValueError("Unsupported method")
        key = f"netops:stage3:v1:{method}:{path}"
        cached = await self._cached(key)
        if cached is not None:
            return cached, {"source": "cache", "attempts": 0}

        for attempt in range(1, self.policy.attempts + 1):
            self.stats["http_requests"] += 1
            try:
                response = await asyncio.wait_for(
                    self.http.request(method, path), timeout=self.policy.timeout_seconds
                )
                if response.status_code in _RETRYABLE_HTTP:
                    response.raise_for_status()
                else:
                    # 400/404/422 etc are permanent; never retry them.
                    response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Network API returned a non-object JSON response")
                # Prevent caching responses that are invalid for the API surface.
                self._validate_payload(method, path, payload)
                await self._store(key, payload)
                return payload, {"source": "live", "attempts": attempt}
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_HTTP:
                    raise
                last_error: Exception = exc
            except (httpx.TransportError, TimeoutError, asyncio.TimeoutError) as exc:
                last_error = exc

            if attempt < self.policy.attempts:
                self.stats["retries"] += 1
                await asyncio.sleep(self.policy.base_backoff_seconds * (2 ** (attempt - 1)))
            else:
                self.stats["failed_operations"] += 1
                raise RetryExhausted(attempt, last_error) from last_error
        raise AssertionError("unreachable")

    @staticmethod
    def _validate_payload(method: str, path: str, payload: dict[str, Any]) -> None:
        if "/diagnostics/" in path:
            if not isinstance(payload.get("result"), dict) or not isinstance(payload.get("probe"), str):
                raise ValueError("Malformed diagnostic payload")
        elif path.endswith("/telemetry"):
            if not isinstance(payload.get("telemetry"), dict):
                raise ValueError("Malformed telemetry payload")
        elif path.endswith("/logs"):
            if not isinstance(payload.get("logs"), list):
                raise ValueError("Malformed logs payload")
        else:
            if not isinstance(payload.get("incident_id"), str):
                raise ValueError("Malformed incident summary")

    async def context(self, incident_id: str) -> dict[str, Any]:
        self.validate_incident_id(incident_id)
        base = f"/incidents/{incident_id}"
        results = await asyncio.gather(
            self._request("GET", base),
            self._request("GET", f"{base}/telemetry"),
            self._request("GET", f"{base}/logs"),
            return_exceptions=True,
        )
        if isinstance(results[0], BaseException):
            # Without a valid incident summary, don't invent an incident.
            raise results[0]
        summary = results[0][0]
        if summary.get("incident_id") != incident_id:
            raise ValueError("Incident summary mismatch")
        errors: list[str] = []
        if isinstance(results[1], BaseException):
            errors.append(f"telemetry unavailable: {type(results[1]).__name__}")
            telemetry = {"incident_id": incident_id, "telemetry": {}, "unavailable": True}
        else:
            telemetry = results[1][0]
        if isinstance(results[2], BaseException):
            errors.append(f"logs unavailable: {type(results[2]).__name__}")
            logs = {"incident_id": incident_id, "logs": [], "unavailable": True}
        else:
            logs = results[2][0]
        return {
            "summary": summary, "telemetry": telemetry, "logs": logs,
            "collection_errors": errors,
        }

    async def diagnostic(self, incident_id: str, probe: str) -> dict[str, Any]:
        self.validate_incident_id(incident_id)
        if probe not in PROBES:
            raise ValueError(f"Unapproved probe: {probe}")
        payload, meta = await self._request(
            "POST", f"/incidents/{incident_id}/diagnostics/{probe}"
        )
        if payload.get("incident_id") != incident_id or payload.get("probe") != probe:
            raise ValueError("Diagnostic response identity mismatch")
        return {**payload, "_netops": meta}
