"""Read-only preflight. Only --live-inference may spend tracked inference budget.

Run inside the backend container for internal central/Langfuse/DB hostnames:
  uv run python -m scripts.preflight --base-url http://localhost:8000
No mode sends a Chatwoot message or mutates a contact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


class Report:
    def __init__(self):
        self.checks = []

    def add(self, name, status, detail):
        self.checks.append({"check": name, "status": status, "detail": detail})

    def result(self):
        return {
            "status": "failed" if any(check["status"] == "fail" for check in self.checks) else "ok",
            "inference_opt_in": any(check["check"] == "live_inference" for check in self.checks),
            "channel_writes": 0,
            "checks": self.checks,
        }


async def run_preflight(settings, *, base_url=None, live_inference=False, transport=None):
    """Return only safe labels/booleans; no raw responses, contacts, URLs or secrets."""
    from backend.integrations.chatwoot import ChatwootClient

    report = Report()
    report.add("configuration", "ok", "Configuración validada; secretos omitidos.")
    async with httpx.AsyncClient(timeout=15, transport=transport, follow_redirects=False) as client:

        async def health(name, url):
            try:
                response = await client.get(url)
                report.add(
                    name,
                    "ok" if response.is_success else "fail",
                    "Disponible."
                    if response.is_success
                    else "El servicio no confirmó disponibilidad.",
                )
            except httpx.RequestError:
                report.add(name, "fail", "No se pudo contactar el servicio.")

        root = str(base_url or settings.public_base_url).rstrip("/")
        for name, path in (("backend_health", "/health"), ("backend_ready", "/ready")):
            await health(name, root + path)
        central = str(settings.central_api_url).rstrip("/").removesuffix("/internal/v1")
        for name, path in (("central_health", "/health"), ("central_ready", "/ready")):
            await health(name, central + path)
        if settings.openai_api_key.get_secret_value():
            try:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={
                        "Authorization": "Bearer " + settings.openai_api_key.get_secret_value()
                    },
                )
                data = response.json() if response.is_success else {}
                models = {
                    model.get("id") for model in data.get("data", []) if isinstance(model, dict)
                }
                for label, model in (
                    ("agent_model", settings.openai_agent_model),
                    ("vision_model", settings.openai_vision_model),
                    ("transcription_model", settings.openai_transcription_model),
                ):
                    report.add(
                        label,
                        "ok" if model in models else "fail",
                        "Modelo listado para esta credencial."
                        if model in models
                        else "El modelo configurado no figura en GET /models; no se infirió.",
                    )
            except (httpx.RequestError, ValueError, TypeError):
                report.add(
                    "openai_models", "fail", "No se pudo verificar GET /models; no se infirió."
                )
        else:
            report.add(
                "openai_models", "fail", "Falta configurar la credencial de OpenAI; no se infirió."
            )
        contacts_base = getattr(settings, "chatwoot_contacts_base_url", "")
        relay_valid = True
        if contacts_base:
            parsed_relay = urlsplit(contacts_base)
            relay_valid = (
                parsed_relay.scheme in {"http", "https"}
                and bool(parsed_relay.hostname)
                and not any(
                    (
                        parsed_relay.username,
                        parsed_relay.password,
                        parsed_relay.query,
                        parsed_relay.fragment,
                    )
                )
            )
            report.add(
                "chatwoot_contacts_route",
                "ok" if relay_valid else "fail",
                "Relay de contactos configurado; credencial y destino omitidos."
                if relay_valid
                else "El origen del relay no es un HTTP(S) válido sin credenciales, query o fragmento.",
            )
        else:
            report.add(
                "chatwoot_contacts_route",
                "skip",
                "Relay opcional ausente; se usa el origen directo configurado para contactos.",
            )
        contacts_token = getattr(settings, "chatwoot_contacts_api_token", None)
        configured_channel = bool(
            relay_valid
            and settings.chatwoot_base_url
            and contacts_token is not None
            and contacts_token.get_secret_value()
            and settings.chatwoot_account_id
            and settings.chatwoot_inbox_id
        )
        report.add(
            "chatwoot_bot_token",
            "ok" if settings.chatwoot_api_token.get_secret_value() else "fail",
            "Credencial de bot presente; no se enviaron mensajes."
            if settings.chatwoot_api_token.get_secret_value()
            else "Falta la credencial de bot.",
        )
        if configured_channel:
            try:
                inbox = await ChatwootClient(settings, transport=transport).request(
                    "GET", f"/inboxes/{settings.chatwoot_inbox_id}"
                )
                scoped = str(inbox.get("id")) == str(settings.chatwoot_inbox_id)
                report.add(
                    "chatwoot_inbox",
                    "ok" if scoped else "fail",
                    "Cuenta/bandeja accesibles por lectura; no se envió ningún mensaje."
                    if scoped
                    else "La bandeja recibida no coincide con la configurada.",
                )
            except Exception:
                report.add(
                    "chatwoot_inbox",
                    "fail",
                    "No se pudo verificar la cuenta/bandeja; no se enviaron mensajes.",
                )
        else:
            report.add(
                "chatwoot_inbox",
                "fail",
                "Falta configuración de cuenta/bandeja o credencial; no se enviaron mensajes.",
            )
        webhook_ready = (
            bool(settings.chatwoot_relay_token.get_secret_value())
            if settings.chatwoot_webhook_auth_mode == "relay"
            else bool(settings.chatwoot_webhook_secret.get_secret_value())
        )
        report.add(
            "webhook_auth",
            "ok" if webhook_ready else "fail",
            "Secreto de autenticación presente; recepción real aún requiere un evento firmado."
            if webhook_ready
            else "Falta el secreto del modo de webhook configurado.",
        )
        if settings.langfuse_enabled:
            await health(
                "langfuse_health",
                str(settings.langfuse_base_url).rstrip("/") + "/api/public/health",
            )
            if (
                settings.langfuse_public_key.get_secret_value()
                and settings.langfuse_secret_key.get_secret_value()
            ):
                try:
                    from langfuse import Langfuse

                    sdk = Langfuse(
                        public_key=settings.langfuse_public_key.get_secret_value(),
                        secret_key=settings.langfuse_secret_key.get_secret_value(),
                        base_url=settings.langfuse_base_url,
                        timeout=10,
                        tracing_enabled=False,
                    )
                    authenticated = await asyncio.wait_for(
                        asyncio.to_thread(sdk.auth_check), timeout=20
                    )
                    report.add(
                        "langfuse_auth",
                        "ok" if authenticated else "fail",
                        "SDK auth_check verificado por lectura."
                        if authenticated
                        else "SDK auth_check no confirmó acceso.",
                    )
                except Exception:
                    report.add(
                        "langfuse_auth",
                        "fail",
                        "No se pudo verificar SDK auth_check; detalles y claves omitidos.",
                    )
            else:
                report.add(
                    "langfuse_auth", "fail", "Faltan claves de proyecto para SDK auth_check."
                )
        else:
            report.add("langfuse", "skip", "Observabilidad externa deshabilitada explícitamente.")
    if live_inference:
        await tracked_inference(settings, report)
    else:
        report.add(
            "inference",
            "skip",
            "No se ejecutó ninguna inferencia. Usa --live-inference para una prueba acotada y contabilizada.",
        )
    return report.result()


async def tracked_inference(settings, report):
    """Exactly one inference attempt through the shared durable budget ledger."""
    from backend.integrations.observability import Observability
    from backend.integrations.openai import InferenceClient
    from backend.services.budget import BudgetService
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = None
    inference = None
    try:
        engine = create_engine(settings.memory_database_url, pool_pre_ping=True)
        sessions = sessionmaker(engine, expire_on_commit=False)
        budget = BudgetService(
            sessions,
            limit_usd=settings.ai_local_spend_limit_usd,
            max_active_calls=settings.ai_max_concurrent_requests,
        )
        bounded = settings.model_copy(
            update={"ai_max_output_tokens": min(settings.ai_max_output_tokens, 256)}
        )
        inference = InferenceClient(bounded, budget, Observability(bounded))
        await inference.response(
            event_id="preflight-" + str(uuid4()),
            input=[{"role": "user", "content": "Prueba de conectividad. Responde OK."}],
            instructions="Responde únicamente OK. No uses herramientas ni datos de clientes.",
            tools=[],
        )
        report.add(
            "live_inference",
            "ok",
            "Una inferencia acotada completada; consumo registrado en el presupuesto compartido.",
        )
    except Exception:
        report.add(
            "live_inference",
            "fail",
            "La inferencia no se completó; no se reintenta. Revisa el ledger de presupuesto para consumo confirmado o incierto.",
        )
    finally:
        if inference:
            inference.observability.flush()
            await inference.sdk.close()
        if engine:
            engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Origen del backend; por defecto PUBLIC_BASE_URL.")
    parser.add_argument(
        "--live-inference",
        action="store_true",
        help="Autoriza una sola inferencia contabilizada, hasta 256 tokens de salida. Nunca envía mensajes.",
    )
    args = parser.parse_args(argv)
    for name in ("httpx", "httpcore", "openai", "langfuse", "opentelemetry", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        from backend.config import get_settings

        result = asyncio.run(
            run_preflight(
                get_settings(), base_url=args.base_url, live_inference=args.live_inference
            )
        )
    except Exception:
        result = {
            "status": "failed",
            "channel_writes": 0,
            "checks": [
                {
                    "check": "configuration",
                    "status": "fail",
                    "detail": "No se pudo validar la configuración. Revisa las variables requeridas; valores y errores crudos omitidos.",
                }
            ],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
