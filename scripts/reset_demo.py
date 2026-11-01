"""Explicit recoverable reset; never clears provider spend or external history."""

import argparse
import asyncio
import json
import uuid

from agil_shared.errors import DomainError
from backend.config import get_settings
from backend.services.demo import DemoService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=["RESET_DEMO"])
    parser.add_argument(
        "--operation-key", type=uuid.UUID, help="Reuse this key to resume a failed reset"
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    service = DemoService(get_settings())
    try:
        if args.status:
            result = asyncio.run(service.status())
        else:
            if args.confirm != "RESET_DEMO":
                parser.error("Explicit --confirm RESET_DEMO is required")
            result = asyncio.run(
                service.reset(
                    {
                        "confirmation": args.confirm,
                        "operation_key": str(args.operation_key) if args.operation_key else None,
                    }
                )
            )
        print(json.dumps(result, ensure_ascii=False))
    except DomainError as exc:
        print(
            json.dumps(
                {
                    "code": exc.code,
                    "message": exc.message,
                    "maintenance": "Inspect --status and resume the same operation key",
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
