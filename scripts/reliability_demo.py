"""No API billing, no Docker, no running FastAPI needed: demonstrate retry/fallback/cache."""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter

import httpx

from netops_agent.api import app
from netops_agent.reliable_client import MemoryCache, ReliableNetworkClient, RetryExhausted, RetryPolicy


class Inject503(httpx.AsyncBaseTransport):
    def __init__(self, failures: int):
        self.inner = httpx.ASGITransport(app=app)
        self.failures = failures
        self.calls = Counter()

    async def handle_async_request(self, request):
        path = request.url.path
        self.calls[path] += 1
        if path.endswith("/diagnostics/bgp_status") and self.calls[path] <= self.failures:
            return httpx.Response(503, json={"detail": "simulated 503"}, request=request)
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


async def main():
    target = "/incidents/INC-0001/diagnostics/bgp_status"
    cases = []
    for name, failures in (("transient_503", 2), ("permanent_503", 99)):
        transport = Inject503(failures)
        async with httpx.AsyncClient(transport=transport, base_url="http://simulator") as http:
            client = ReliableNetworkClient(http, RetryPolicy(attempts=3, base_backoff_seconds=0))
            try:
                result = await client.diagnostic("INC-0001", "bgp_status")
                outcome = {"result": "ok", "probe": result["result"], "execution": result["_netops"]}
            except RetryExhausted as exc:
                outcome = {"result": "failed_safely", "error": type(exc).__name__, "attempts": exc.attempts}
            cases.append({"scenario": name, "http_requests": transport.calls[target], "outcome": outcome})

    transport = Inject503(0)
    async with httpx.AsyncClient(transport=transport, base_url="http://simulator") as http:
        client = ReliableNetworkClient(http, cache=MemoryCache())
        first = await client.diagnostic("INC-0001", "bgp_status")
        second = await client.diagnostic("INC-0001", "bgp_status")
        cases.append({
            "scenario": "cache_hit", "http_requests": transport.calls[target],
            "outcome": {"first_source": first["_netops"]["source"],
                        "second_source": second["_netops"]["source"],
                        "cache_hits": client.stats["cache_hits"]},
        })
    print(json.dumps({"stage": 3, "fault_injection": cases}, indent=2))
    assert cases[0]["http_requests"] == 3 and cases[0]["outcome"]["result"] == "ok"
    assert cases[1]["http_requests"] == 3 and cases[1]["outcome"]["result"] == "failed_safely"
    assert cases[2]["http_requests"] == 1 and cases[2]["outcome"]["second_source"] == "cache"
    print("STAGE3 RELIABILITY DEMO: PASS", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
