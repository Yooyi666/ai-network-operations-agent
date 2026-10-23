"""Deterministic Stage 3 fault injection: no LLM, Redis or live server required."""
import asyncio
from collections import Counter

import httpx
import pytest

from netops_agent.api import app
from netops_agent.reliable_client import (
    MemoryCache, ReliableNetworkClient, RetryExhausted, RetryPolicy,
)


class FaultTransport(httpx.AsyncBaseTransport):
    """Wrap the FastAPI ASGI app and inject failures at the HTTP transport boundary."""

    def __init__(self, *, path_suffix="/diagnostics/bgp_status", fail_first=0, always_fail=False,
                 delay_first=False, status_code=503):
        self.inner = httpx.ASGITransport(app=app)
        self.path_suffix = path_suffix
        self.fail_first = fail_first
        self.always_fail = always_fail
        self.delay_first = delay_first
        self.status_code = status_code
        self.counts = Counter()

    async def handle_async_request(self, request):
        path = request.url.path
        self.counts[path] += 1
        if path.endswith(self.path_suffix):
            n = self.counts[path]
            if self.delay_first and n == 1:
                await asyncio.Event().wait()  # Deterministic timeout injection
            if self.always_fail or n <= self.fail_first:
                return httpx.Response(self.status_code, json={"detail": "Injected failure"}, request=request)
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


def run(coro):
    return asyncio.run(coro)


def test_retry_503_twice_then_success():
    async def scenario():
        transport = FaultTransport(fail_first=2)
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http, RetryPolicy(attempts=3, base_backoff_seconds=0))
            result = await client.diagnostic("INC-0001", "bgp_status")
        assert result["result"]["session_state"] == "Idle"
        assert result["_netops"] == {"source": "live", "attempts": 3}
        assert transport.counts["/incidents/INC-0001/diagnostics/bgp_status"] == 3
        assert client.stats["retries"] == 2
    run(scenario())


def test_non_retryable_404_not_retried():
    async def scenario():
        transport = FaultTransport(path_suffix="invalid", fail_first=0)
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http)
            with pytest.raises(httpx.HTTPStatusError) as exc:
                await client.diagnostic("INC-9999", "bgp_status")
        assert exc.value.response.status_code == 404
        assert transport.counts["/incidents/INC-9999/diagnostics/bgp_status"] == 1
        assert client.stats["retries"] == 0
    run(scenario())


def test_permanent_503_fails_after_limit():
    async def scenario():
        transport = FaultTransport(always_fail=True)
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http, RetryPolicy(attempts=3, base_backoff_seconds=0))
            with pytest.raises(RetryExhausted) as exc:
                await client.diagnostic("INC-0001", "bgp_status")
        assert exc.value.attempts == 3
        assert transport.counts["/incidents/INC-0001/diagnostics/bgp_status"] == 3
        assert client.stats["failed_operations"] == 1
    run(scenario())


def test_cache_hit_avoids_second_http_request():
    async def scenario():
        transport = FaultTransport()
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http, cache=MemoryCache())
            one = await client.diagnostic("INC-0001", "bgp_status")
            two = await client.diagnostic("INC-0001", "bgp_status")
        assert one["_netops"]["source"] == "live"
        assert two["_netops"]["source"] == "cache"
        assert transport.counts["/incidents/INC-0001/diagnostics/bgp_status"] == 1
        assert client.stats["cache_hits"] == 1
    run(scenario())


def test_timeout_first_attempt_then_recovers():
    async def scenario():
        transport = FaultTransport(delay_first=True)
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(
                http, RetryPolicy(attempts=2, timeout_seconds=1.0, base_backoff_seconds=0)
            )
            result = await client.diagnostic("INC-0001", "bgp_status")
        assert result["_netops"]["attempts"] == 2
        assert client.stats["retries"] == 1
    run(scenario())


def test_invalid_probe_and_incident_never_reach_network():
    async def scenario():
        transport = FaultTransport()
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http)
            with pytest.raises(ValueError):
                await client.diagnostic("../../secret", "ping")
            with pytest.raises(ValueError):
                await client.diagnostic("INC-0001", "exec_shell")
        assert not transport.counts
    run(scenario())


def test_telemetry_failure_is_marked_unavailable_not_silent():
    async def scenario():
        transport = FaultTransport(path_suffix="/telemetry", always_fail=True)
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http, RetryPolicy(attempts=2, base_backoff_seconds=0))
            context = await client.context("INC-0001")
        assert context["telemetry"]["unavailable"] is True
        assert context["telemetry"]["telemetry"] == {}
        assert "telemetry unavailable" in context["collection_errors"][0]
        assert context["summary"]["incident_id"] == "INC-0001"
    run(scenario())


def test_cache_outage_falls_back_to_live_http():
    class BrokenCache:
        async def get(self, key):
            raise ConnectionError("Redis unavailable")
        async def set(self, key, value, ttl_seconds):
            raise ConnectionError("Redis unavailable")
        async def close(self):
            return None

    async def scenario():
        transport = FaultTransport()
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as http:
            client = ReliableNetworkClient(http, cache=BrokenCache())
            result = await client.diagnostic("INC-0001", "bgp_status")
        assert result["result"]["session_state"] == "Idle"
        assert result["_netops"]["source"] == "live"
        assert client.stats["cache_errors"] == 2
    run(scenario())


def test_missing_incident_summary_is_not_fabricated():
    async def scenario():
        async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as http:
            client = ReliableNetworkClient(http)
            with pytest.raises(httpx.HTTPStatusError):
                await client.context("INC-9999")
    run(scenario())


def test_retry_policy_bounds():
    with pytest.raises(ValueError):
        RetryPolicy(attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(attempts=7)
    with pytest.raises(ValueError):
        RetryPolicy(timeout_seconds=0)
