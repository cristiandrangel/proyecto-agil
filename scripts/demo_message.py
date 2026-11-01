"""Inject a local demo message using private operator login; explicit inference opt-in."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import SecretStr


def sanitize_reply(content, settings, source_id):
    value = str(content or "")
    for secret in (
        source_id,
        settings.operator_password.get_secret_value(),
        settings.session_secret.get_secret_value(),
        settings.central_operator_token.get_secret_value(),
        settings.central_agent_token.get_secret_value(),
        settings.openai_api_key.get_secret_value(),
        settings.chatwoot_api_token.get_secret_value(),
        getattr(settings, "chatwoot_contacts_api_token", SecretStr("")).get_secret_value(),
    ):
        if secret:
            value = value.replace(secret, "[dato privado omitido]")
    value = re.sub(r"https?://\S+", "[enlace omitido; consúltalo en la web de demo]", value)
    value = re.sub(
        r"(?i)\b(?:pin|token|grant|password|contraseña)\s*[:=]\s*\S+", "[secreto omitido]", value
    )
    return value[:5000]


async def send_local(settings, *, source_id, content, base_url=None, timeout=120, transport=None):
    root = str(base_url or settings.public_base_url).rstrip("/")
    origin = urlsplit(str(settings.public_base_url))
    origin_header = origin.scheme + "://" + origin.netloc
    async with httpx.AsyncClient(
        base_url=root, timeout=15, follow_redirects=False, transport=transport
    ) as client:
        response = await client.get("/login")
        match = re.search(r'name="csrf" value="([^"]+)"', response.text)
        if response.status_code != 200 or not match:
            raise RuntimeError("operator_login_unavailable")
        response = await client.post(
            "/login",
            data={
                "username": settings.operator_username,
                "password": settings.operator_password.get_secret_value(),
                "csrf": match[1],
            },
            headers={"Origin": origin_header},
        )
        if response.status_code != 303:
            raise RuntimeError("operator_login_failed")
        response = await client.get("/central")
        match = re.search(r'name="csrf-token" content="([^"]+)"', response.text)
        if response.status_code != 200 or not match:
            raise RuntimeError("operator_session_unavailable")
        response = await client.post(
            "/api/demo/messages",
            json={
                "source_id": source_id,
                "content": content,
                "message_id": str(uuid4()),
                "live_inference": True,
            },
            headers={"Origin": origin_header, "X-CSRF-Token": match[1]},
        )
        if response.status_code != 200:
            raise RuntimeError("local_message_rejected")
        event_id = response.json()["event_id"]
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            response = await client.get(f"/api/demo/messages/{event_id}")
            if response.status_code != 200:
                raise RuntimeError("local_message_status_unavailable")
            result = response.json()
            replies = [
                {
                    "content": sanitize_reply(row.get("content"), settings, source_id),
                    "state": row.get("state"),
                }
                for row in result.get("responses", [])
            ]
            # Completion of inference and completion of the sender are separate states.
            if result.get("status") in {"failed", "cancelled"} or (
                replies
                and all(
                    row["state"] in {"sent", "failed", "uncertain", "cancelled"} for row in replies
                )
            ):
                return {"event_id": event_id, "status": result.get("status"), "responses": replies}
            await asyncio.sleep(0.5)
        return {
            "event_id": event_id,
            "status": "timeout",
            "responses": [],
            "message": "El evento sigue pendiente. Consulta su estado; no reenvíes el mensaje a ciegas.",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Autoriza inferencia real usando el presupuesto local; el canal permanece simulado.",
    )
    parser.add_argument(
        "--source-id", required=True, help="source_id ficticio literal, sin normalizar."
    )
    parser.add_argument("--content", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 300:
        parser.error("--timeout debe estar entre 1 y 300 segundos")
    try:
        from backend.config import get_settings

        result = asyncio.run(
            send_local(
                get_settings(),
                source_id=args.source_id,
                content=args.content,
                base_url=args.base_url,
                timeout=args.timeout,
            )
        )
    except Exception:
        result = {
            "status": "failed",
            "message": "No se completó la entrada local. Verifica salud, credencial de operador y modo local; detalles privados omitidos.",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] not in {"failed", "cancelled", "timeout"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
