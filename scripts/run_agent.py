"""Stage 3: invoke the LangGraph agent with the reliable HTTP tool client."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

from netops_agent.agent import investigate
from netops_agent.agent_engines import make_engine
from netops_agent.reliable_client import (
    MemoryCache, RedisCache, ReliableNetworkClient, RetryExhausted, RetryPolicy,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangGraph network incident diagnosis")
    parser.add_argument("--incident-id", default="INC-0001")
    parser.add_argument("--mode", choices=("mock", "openai"), default="mock")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--cache", choices=("off", "memory", "redis"), default="off")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--cache-ttl", type=int, default=60)
    parser.add_argument("--early-stop", choices=("off", "on"), default="off",
                        help="Opt-in synthetic-lab early stopping on confirmed live evidence")
    parser.add_argument("--consistency-guard", choices=("off", "on"), default="off",
                        help="Optional bounded model recheck when live evidence contradicts final label")
    return parser.parse_args()


async def main() -> None:
    load_dotenv()
    args = arguments()
    base_url = args.base_url or os.getenv("NETOPS_API_BASE_URL", "http://127.0.0.1:8000")
    policy = RetryPolicy(attempts=args.attempts, timeout_seconds=args.timeout)
    cache = {
        "off": lambda: None,
        "memory": MemoryCache,
        "redis": lambda: RedisCache(os.getenv("REDIS_URL", "redis://localhost:6379/0")),
    }[args.cache]()

    try:
        engine = make_engine(args.mode)
        async with httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(args.timeout)) as http:
            client = ReliableNetworkClient(
                http, policy=policy, cache=cache, cache_ttl_seconds=args.cache_ttl,
            )
            result = await investigate(args.incident_id, client, engine,
                                       early_stop=args.early_stop == "on",
                                       consistency_guard=args.consistency_guard == "on")
        result["mode"] = args.mode
        result["is_real_llm"] = args.mode == "openai"
        result["cache_mode"] = args.cache
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("review_required"):
            print("WARNING: Diagnosis is provisional: evidence did not verify the class. "
                  "Manual review required; do not treat diagnosis.root_cause as accepted.",
                  file=sys.stderr)
    finally:
        if cache is not None:
            await cache.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError, httpx.HTTPError, RetryExhausted) as exc:
        print(f"Agent failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Verify the simulator is running on the configured NETOPS_API_BASE_URL", file=sys.stderr)
        sys.exit(1)
