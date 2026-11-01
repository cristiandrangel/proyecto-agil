"""Seed fictitious demo data through the authenticated central HTTP boundary."""

import asyncio
import json

from backend.config import get_settings
from backend.integrations.central import CentralClient


async def run():
    settings = get_settings()
    if not settings.demo_mode:
        raise SystemExit("DEMO_MODE must be true")
    return await CentralClient(settings, role="operator").request(
        "POST", "/demo/seed", idempotency_key="public-demo-seed-v1"
    )


def main():
    print(json.dumps(asyncio.run(run()), ensure_ascii=False))


if __name__ == "__main__":
    main()
