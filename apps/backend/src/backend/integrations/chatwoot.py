"""Adaptador acotado a una cuenta e inbox. Sin reintentos ciegos de escrituras."""

import hashlib
import hmac
import time
from urllib.parse import unquote

import httpx
from agil_shared.errors import DomainError


def verify_signature(settings, headers, raw: bytes):
    if settings.chatwoot_webhook_auth_mode == "relay":
        expected = settings.chatwoot_relay_token.get_secret_value()
        actual = headers.get("authorization", "").removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(expected.encode(), actual.encode()):
            raise DomainError("webhook_unauthorized", "Webhook no autorizado.", 401)
        return
    secret = settings.chatwoot_webhook_secret.get_secret_value()
    timestamp = headers.get("x-chatwoot-timestamp", "")
    signature = headers.get("x-chatwoot-signature", "")
    try:
        if abs(time.time() - int(timestamp)) > settings.chatwoot_webhook_tolerance_seconds:
            raise ValueError
    except (ValueError, TypeError):
        raise DomainError("webhook_unauthorized", "Firma de webhook inválida.", 401) from None
    expected = (
        "sha256="
        + hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    )
    if not secret or not hmac.compare_digest(signature.encode(), expected.encode()):
        raise DomainError("webhook_unauthorized", "Firma de webhook inválida.", 401)


class ChatwootClient:
    def __init__(self, settings, *, transport=None):
        self.settings, self.transport = settings, transport

    async def request(self, method, path, **kwargs):
        cfg = self.settings
        method = method.upper()
        decoded_path = unquote(path) if isinstance(path, str) else ""
        if (
            not decoded_path.startswith("/")
            or decoded_path.startswith("//")
            or ".." in decoded_path.split("/")
            or "?" in decoded_path
            or "#" in decoded_path
        ):
            raise DomainError("invalid_channel_path", "Ruta del canal no permitida.", 422)
        if not cfg.chatwoot_base_url or not cfg.chatwoot_account_id or not cfg.chatwoot_inbox_id:
            raise DomainError("channel_not_configured", "Falta configurar el canal de prueba.", 503)
        contact_scope = (
            path == "/contacts"
            or path.startswith("/contacts/")
            or path == "/inboxes"
            or path.startswith("/inboxes/")
        )
        selected = (
            getattr(cfg, "chatwoot_contacts_api_token", None)
            if contact_scope
            else cfg.chatwoot_api_token
        )
        token = selected.get_secret_value() if selected is not None else ""
        if not token:
            raise DomainError(
                "channel_contacts_not_configured" if contact_scope else "channel_not_configured",
                "Falta la credencial del servicio de contactos."
                if contact_scope
                else "Falta la credencial del bot de prueba.",
                503,
            )
        headers = (
            {"api_access_token": token}
            if cfg.chatwoot_auth_scheme == "api_access_token"
            else {"Authorization": "Bearer " + token}
        )
        contacts_base = getattr(cfg, "chatwoot_contacts_base_url", "") or cfg.chatwoot_base_url
        base = contacts_base if contact_scope else cfg.chatwoot_base_url
        url = f"{str(base).rstrip('/')}/api/v1/accounts/{cfg.chatwoot_account_id}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except httpx.RequestError:
            raise DomainError(
                "channel_uncertain" if method != "GET" else "channel_unavailable",
                "No se pudo verificar el resultado del canal.",
                503,
                method == "GET",
            ) from None
        if response.is_error or response.is_redirect:
            uncertain = method.upper() != "GET" and (
                response.status_code >= 500 or response.status_code == 408
            )
            raise DomainError(
                "channel_uncertain" if uncertain else "channel_rejected",
                "El resultado del canal requiere verificación."
                if uncertain
                else "El canal rechazó la operación.",
                503,
                method.upper() == "GET",
            )
        try:
            return response.json()
        except ValueError:
            raise DomainError(
                "channel_uncertain", "Respuesta de canal no verificable.", 503
            ) from None

    async def conversation(self, conversation_id):
        data = await self.request("GET", f"/conversations/{int(conversation_id)}")
        if str(data.get("inbox_id")) != str(self.settings.chatwoot_inbox_id):
            raise DomainError("wrong_inbox", "Conversación fuera de la bandeja de prueba.", 403)
        return data

    async def send_message(self, conversation_id, content, *, private=False):
        current = await self.conversation(conversation_id)
        if not private and current.get("status") != "pending":
            raise DomainError("human_control", "La conversación está bajo atención humana.", 409)
        if not private and current.get("can_reply") is False:
            raise DomainError(
                "channel_cannot_reply",
                "El canal no permite responder con texto libre en esta conversación.",
                409,
            )
        return await self.request(
            "POST",
            f"/conversations/{int(conversation_id)}/messages",
            json={
                "content": content,
                "message_type": "outgoing",
                "private": private,
            },
        )

    async def set_open(self, conversation_id):
        await self.conversation(conversation_id)
        return await self.request(
            "POST", f"/conversations/{int(conversation_id)}/toggle_status", json={"status": "open"}
        )

    async def resolve_contact(self, customer):
        cfg = self.settings
        phone = customer.get("phone_e164") or customer.get("phone_number")
        if (
            not phone
            or not customer.get("test_contact_enabled")
            or customer.get("delivery_mode") != "live"
        ):
            raise DomainError(
                "live_contact_disabled", "El contacto de prueba no está habilitado.", 409
            )
        matches = []
        page = 1
        while page <= 20:
            result = await self.request(
                "GET", "/contacts/search", params={"q": phone, "page": page}
            )
            payload = result.get("payload", [])
            matches += [c for c in payload if c.get("phone_number") == phone]
            if not payload or len(payload) < 15:
                break
            page += 1
        if len(matches) > 1:
            raise DomainError(
                "ambiguous_channel_contact", "Hay varios contactos del canal con ese teléfono.", 409
            )
        if not matches:
            result = await self.request(
                "POST",
                "/contacts",
                json={
                    "inbox_id": cfg.chatwoot_inbox_id,
                    "phone_number": phone,
                    "name": customer.get("display_name", "Evaluador demo"),
                },
            )
            contact = result.get("payload", result)
            contact = contact.get("contact", contact)
        else:
            contact = matches[0]
        contact_id = contact["id"]
        result = await self.request("GET", f"/contacts/{contact_id}/contactable_inboxes")
        bindings = result.get("payload", [])
        valid = [
            b
            for b in bindings
            if str((b.get("inbox") or {}).get("id", b.get("inbox_id")))
            == str(cfg.chatwoot_inbox_id)
        ]
        if (
            len(valid) != 1
            or not isinstance(valid[0].get("source_id"), str)
            or not valid[0]["source_id"]
        ):
            raise DomainError(
                "channel_preparation_required",
                "Envía un mensaje inicial al número de prueba para preparar su contacto.",
                409,
            )
        source = valid[0]["source_id"]
        result = await self.request("GET", f"/contacts/{contact_id}/conversations")
        conversations = [
            c
            for c in result.get("payload", [])
            if str(c.get("inbox_id")) == str(cfg.chatwoot_inbox_id)
        ]
        eligible = [c for c in conversations if c.get("status") == "pending"]
        if eligible:
            conv = max(eligible, key=lambda c: int(c["id"]))
        elif any(c.get("status") == "open" for c in conversations):
            raise DomainError("human_control", "El contacto está bajo atención humana.", 409)
        else:
            conv = await self.request(
                "POST",
                "/conversations",
                json={
                    "source_id": source,
                    "inbox_id": cfg.chatwoot_inbox_id,
                    "contact_id": contact_id,
                    "status": "pending",
                },
            )
        return {
            "account_id": str(cfg.chatwoot_account_id),
            "inbox_id": str(cfg.chatwoot_inbox_id),
            "contact_id": str(contact_id),
            "source_id": source,
            "conversation_id": str(conv["id"]),
        }

    async def send_template(self, binding, template, operation_key):
        if str(binding["inbox_id"]) != str(self.settings.chatwoot_inbox_id) or str(
            binding["account_id"]
        ) != str(self.settings.chatwoot_account_id):
            raise DomainError(
                "wrong_inbox", "Destino de campaña fuera de la bandeja autorizada.", 403
            )
        current = await self.conversation(binding["conversation_id"])
        if current.get("status") != "pending":
            raise DomainError("human_control", "La conversación está bajo atención humana.", 409)
        params = {
            "name": template.get("template_name", template.get("name")),
            "category": template.get("category", "UTILITY"),
            "language": template.get("template_language", template.get("language")),
            "processed_params": template.get("processed_params", {}),
        }
        result = await self.request(
            "POST",
            f"/conversations/{int(binding['conversation_id'])}/messages",
            json={
                "content": "Notificación de prueba de gestión de cartera.",
                "message_type": "outgoing",
                "private": False,
                "template_params": params,
            },
        )
        return {"message_id": str(result["id"])}
