"""Owner-side channel relay: account/inbox boundary, never a generic proxy.

Both broad Chatwoot credentials remain on this host. Reads/contact preparation
use the service user; conversation writes use the bot to preserve its actor and
pending/handoff semantics. Responses never publish conversation/message content.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PHONE = re.compile(r"\+[1-9][0-9]{7,14}\Z")
MAX_BODY = 2048
MAX_MESSAGE_CHARS = 20_000
MAX_MESSAGE_BODY = 256 * 1024
MESSAGE_PATH = re.compile(r"/api/v1/accounts/[0-9]+/conversations/[0-9]+/messages\Z")
MAX_UPSTREAM = 1024 * 1024


class RelaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    chatwoot_upstream_base_url: str
    chatwoot_upstream_api_token: SecretStr
    chatwoot_upstream_bot_token: SecretStr
    chatwoot_relay_shared_token: SecretStr
    chatwoot_relay_account_id: int
    chatwoot_relay_inbox_id: int
    chatwoot_relay_quota_path: str = "/var/lib/channel-relay/quota.sqlite3"
    chatwoot_relay_requests_per_minute: int = 60
    chatwoot_relay_creates_per_day: int = 10
    chatwoot_relay_sends_per_day: int = 100
    chatwoot_upstream_auth_scheme: Literal["api_access_token", "bearer"] = "api_access_token"

    @field_validator("chatwoot_upstream_base_url")
    @classmethod
    def origin_only(cls, value):
        origin = urlsplit(value)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Upstream must be a fixed HTTP(S) origin without credentials or path")
        return value.rstrip("/")

    @model_validator(mode="after")
    def limits(self):
        if self.chatwoot_relay_account_id < 1 or self.chatwoot_relay_inbox_id < 1:
            raise ValueError("Configure a positive account and inbox")
        if (
            not 1 <= self.chatwoot_relay_requests_per_minute <= 60
            or not 1 <= self.chatwoot_relay_creates_per_day <= 10
            or not 1 <= self.chatwoot_relay_sends_per_day <= 100
        ):
            raise ValueError(
                "Relay caps are 60 requests/minute, 10 contacts/day and 100 messages/day"
            )
        relay, user = (
            self.chatwoot_relay_shared_token.get_secret_value(),
            self.chatwoot_upstream_api_token.get_secret_value(),
        )
        bot = self.chatwoot_upstream_bot_token.get_secret_value()
        if (
            not 16 <= len(bot) <= 1024
            or hmac.compare_digest(relay.encode(), bot.encode())
            or hmac.compare_digest(user.encode(), bot.encode())
            or not 32 <= len(relay) <= 256
            or not 16 <= len(user) <= 1024
            or hmac.compare_digest(relay.encode(), user.encode())
        ):
            raise ValueError("Configure distinct strong relay and upstream credentials")
        return self


class RelayError(Exception):
    def __init__(self, code, status=400, *, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


def error_response(error):
    return JSONResponse(
        {"code": error.code, "message": "La operación no está disponible en el canal de prueba."},
        status_code=error.status,
        headers={
            "Cache-Control": "no-store",
            **({"Retry-After": str(error.retry_after)} if error.retry_after else {}),
        },
    )


class RequestQuota:
    def __init__(self, maximum, clock=time.monotonic):
        self.maximum, self.clock = maximum, clock
        self.recent = deque()
        self.lock = threading.Lock()

    def take(self):
        with self.lock:
            now = self.clock()
            while self.recent and self.recent[0] <= now - 60:
                self.recent.popleft()
            if len(self.recent) >= self.maximum:
                raise RelayError(
                    "relay_rate_limit",
                    429,
                    retry_after=max(1, int(60 - (now - self.recent[0])) + 1),
                )
            self.recent.append(now)


class CreateQuota:
    """Conservative durable quota: failed/uncertain create attempts are not refunded."""

    def __init__(self, filename, maximum, today=None, *, category="creates"):
        self.filename, self.maximum = filename, maximum
        if category not in {"creates", "sends"}:
            raise ValueError("Unknown quota category")
        self.table = "daily_" + category
        self.error_code = "relay_create_limit" if category == "creates" else "relay_send_limit"
        self.today = today or (lambda: datetime.now(timezone.utc).date().isoformat())
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(filename, timeout=5) as connection:
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} (day TEXT PRIMARY KEY, attempts INTEGER NOT NULL)"
            )

    def take(self):
        try:
            with sqlite3.connect(self.filename, timeout=5) as connection:
                connection.execute("BEGIN IMMEDIATE")
                day = self.today()
                row = connection.execute(
                    f"SELECT attempts FROM {self.table} WHERE day=?", (day,)
                ).fetchone()
                if row and row[0] >= self.maximum:
                    raise RelayError(self.error_code, 429)
                connection.execute(
                    f"INSERT INTO {self.table}(day,attempts) VALUES (?,1) ON CONFLICT(day) DO UPDATE SET attempts=attempts+1",
                    (day,),
                )
        except sqlite3.Error:
            raise RelayError("relay_quota_unavailable", 503) from None


def identifier(value):
    raw = str(value)
    if len(raw) > 19 or not raw.isascii() or not raw.isdigit() or not 0 < int(raw) < 2**63:
        raise RelayError("contact_unavailable", 404)
    return int(raw)


def phone(value):
    if not isinstance(value, str) or PHONE.fullmatch(value) is None:
        raise RelayError("exact_phone_required", 422)
    return value


def payload_list(data):
    return (
        data.get("payload", [])
        if isinstance(data, dict) and isinstance(data.get("payload"), list)
        else []
    )


def contact_object(data):
    if not isinstance(data, dict):
        raise RelayError("upstream_invalid", 503)
    result = data.get("payload", data)
    if isinstance(result, dict):
        result = result.get("contact", result)
    if not isinstance(result, dict):
        raise RelayError("upstream_invalid", 503)
    return result


def inbox_of(binding):
    if not isinstance(binding, dict):
        return None
    inbox = binding.get("inbox")
    return inbox.get("id") if isinstance(inbox, dict) else binding.get("inbox_id")


def test_bindings(bindings, inbox_id):
    safe = []
    if not isinstance(bindings, list):
        return safe
    for binding in bindings:
        if str(inbox_of(binding)) != str(inbox_id):
            continue
        item = {"inbox_id": inbox_id}
        if binding.get("id") is not None:
            try:
                item["id"] = identifier(binding["id"])
            except RelayError:
                continue
        if isinstance(binding.get("source_id"), str) and binding["source_id"]:
            item["source_id"] = binding["source_id"]
        safe.append(item)
    return safe


def sanitized_contact(contact, inbox_id):
    bindings = test_bindings(contact.get("contact_inboxes", []), inbox_id)
    if not bindings:
        return None
    try:
        return {
            "id": identifier(contact.get("id")),
            "phone_number": phone(contact.get("phone_number")),
            "name": "Contacto demo",
            "contact_inboxes": bindings,
        }
    except RelayError:
        return None


def authenticate(request, expected):
    headers = request.headers
    authorization = headers.getlist("authorization")
    api = headers.getlist("api_access_token")
    if len(authorization) > 1 or len(api) > 1:
        raise RelayError("relay_unauthorized", 401)
    candidates = []
    if authorization:
        scheme, separator, value = authorization[0].partition(" ")
        if not separator or scheme.lower() != "bearer":
            raise RelayError("relay_unauthorized", 401)
        candidates.append(value)
    if api:
        candidates.append(api[0])
    if not candidates or any(
        len(value) > 256 or not hmac.compare_digest(expected.encode(), value.encode())
        for value in candidates
    ):
        raise RelayError("relay_unauthorized", 401)


def create_app(settings: RelaySettings | None = None, *, transport=None, clock=time.monotonic):
    cfg = settings or RelaySettings()
    for logger_name in ("httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    requests = RequestQuota(cfg.chatwoot_relay_requests_per_minute, clock)
    creates = CreateQuota(cfg.chatwoot_relay_quota_path, cfg.chatwoot_relay_creates_per_day)
    sends = CreateQuota(
        cfg.chatwoot_relay_quota_path, cfg.chatwoot_relay_sends_per_day, category="sends"
    )
    mutation_lock = asyncio.Lock()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.middleware("http")
    async def boundary(request, call_next):
        try:
            requests.take()
            authenticate(request, cfg.chatwoot_relay_shared_token.get_secret_value())
            maximum = (
                MAX_MESSAGE_BODY
                if request.method == "POST" and MESSAGE_PATH.fullmatch(request.url.path)
                else MAX_BODY
            )
            length = request.headers.get("content-length")
            if length is not None and (
                len(length) > 10 or not length.isdigit() or int(length) > maximum
            ):
                raise RelayError("request_too_large", 413)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        except RelayError as error:
            return error_response(error)

    @app.exception_handler(RelayError)
    async def relay_error(request, error):
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return error_response(RelayError("invalid_request", 422))

    def scope(account_id, inbox_id=None):
        if str(account_id) != str(cfg.chatwoot_relay_account_id) or (
            inbox_id is not None and str(inbox_id) != str(cfg.chatwoot_relay_inbox_id)
        ):
            raise RelayError("relay_scope_denied", 403)

    def no_query(request):
        if request.query_params:
            raise RelayError("query_denied", 422)

    async def upstream(method, suffix, *, params=None, body=None, unavailable=False, bot=False):
        origin = cfg.chatwoot_upstream_base_url
        url = f"{origin}/api/v1/accounts/{cfg.chatwoot_relay_account_id}{suffix}"
        token = (
            cfg.chatwoot_upstream_bot_token if bot else cfg.chatwoot_upstream_api_token
        ).get_secret_value()
        headers = {
            "Accept": "application/json",
            **(
                {"api_access_token": token}
                if cfg.chatwoot_upstream_auth_scheme == "api_access_token"
                else {"Authorization": "Bearer " + token}
            ),
        }
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(10, connect=3),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    method, url, params=params, json=body, headers=headers
                ) as response:
                    if unavailable and response.status_code in {403, 404}:
                        raise RelayError("contact_unavailable", 404)
                    if response.status_code == 429:
                        raw_retry = response.headers.get("retry-after", "60")
                        retry = (
                            int(raw_retry)
                            if raw_retry.isascii() and raw_retry.isdigit() and len(raw_retry) < 5
                            else 60
                        )
                        raise RelayError(
                            "upstream_rate_limited", 429, retry_after=min(300, max(1, retry))
                        )
                    if method == "POST" and response.status_code in {409, 422}:
                        raise RelayError("channel_preparation_required", 409)
                    if not 200 <= response.status_code < 300:
                        raise RelayError("upstream_unavailable", 503)
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_UPSTREAM:
                            raise RelayError("upstream_invalid", 503)
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise RelayError("upstream_invalid", 503)
                    return data
        except (httpx.RequestError, ValueError, UnicodeDecodeError):
            raise RelayError("upstream_unavailable", 503) from None

    async def json_body(request, maximum=MAX_BODY):
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise RelayError("invalid_request", 422)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > maximum:
                raise RelayError("request_too_large", 413)
        try:
            body = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            raise RelayError("invalid_request", 422) from None
        if not isinstance(body, dict):
            raise RelayError("invalid_request", 422)
        return body

    async def associated(contact_id):
        data = contact_object(
            await upstream("GET", f"/contacts/{identifier(contact_id)}", unavailable=True)
        )
        if identifier(data.get("id")) != identifier(contact_id) or not test_bindings(
            data.get("contact_inboxes", []), cfg.chatwoot_relay_inbox_id
        ):
            raise RelayError("contact_unavailable", 404)
        return data

    async def binding_for(contact):
        # Chatwoot can retain several aliases in one inbox. Its contactable API
        # gives the canonical destination for NEW conversations, not the alias
        # used by every existing conversation. Require persisted exact membership.
        data = await upstream(
            "GET",
            f"/contacts/{identifier(contact.get('id'))}/contactable_inboxes",
            unavailable=True,
        )
        bindings = test_bindings(payload_list(data), cfg.chatwoot_relay_inbox_id)
        persisted = test_bindings(contact.get("contact_inboxes"), cfg.chatwoot_relay_inbox_id)
        if (
            len(bindings) != 1
            or not isinstance(bindings[0].get("source_id"), str)
            or sum(item.get("source_id") == bindings[0]["source_id"] for item in persisted) != 1
        ):
            raise RelayError("channel_preparation_required", 409)
        return bindings[0]

    async def checked_conversation(conversation_id, *, expected_contact=None):
        requested = identifier(conversation_id)
        data = await upstream("GET", f"/conversations/{requested}", unavailable=True)
        if (
            identifier(data.get("id")) != requested
            or str(data.get("inbox_id")) != str(cfg.chatwoot_relay_inbox_id)
            or str(data.get("account_id")) != str(cfg.chatwoot_relay_account_id)
        ):
            raise RelayError("conversation_unavailable", 404)
        # The installed Chatwoot serializer puts the contact in meta.sender.
        # Never return this object: it can contain other inboxes and private data.
        meta = data.get("meta")
        sender = meta.get("sender") if isinstance(meta, dict) else None
        contact_id = identifier(sender.get("id") if isinstance(sender, dict) else None)
        if expected_contact is not None and contact_id != identifier(expected_contact):
            raise RelayError("conversation_unavailable", 404)
        contact = await associated(contact_id)
        binding = None
        supplied_binding = data.get("contact_inbox")
        if supplied_binding is not None:
            supplied = test_bindings([supplied_binding], cfg.chatwoot_relay_inbox_id)
            if (
                len(supplied) != 1
                or not isinstance(supplied[0].get("source_id"), str)
                or sum(
                    item.get("source_id") == supplied[0]["source_id"]
                    and (item.get("id") is None or supplied[0].get("id") == item["id"])
                    for item in test_bindings(
                        contact.get("contact_inboxes"), cfg.chatwoot_relay_inbox_id
                    )
                )
                != 1
            ):
                raise RelayError("conversation_unavailable", 404)
            binding = supplied[0]
        if data.get("status") not in {"open", "pending", "resolved", "snoozed"} or not isinstance(
            data.get("can_reply"), bool
        ):
            raise RelayError("upstream_invalid", 503)
        return {
            "id": requested,
            "inbox_id": cfg.chatwoot_relay_inbox_id,
            "status": data["status"],
            "can_reply": data["can_reply"],
            # The installed show serializer has no contact_inbox. Do not invent
            # its source from the contact's aliases or canonical phone destination.
            **({"contact_inbox": binding} if binding is not None else {}),
        }

    async def approved_template(params):
        if (
            not isinstance(params, dict)
            or set(params) != {"name", "language", "category", "processed_params"}
            or params.get("processed_params") != {}
            or any(
                not isinstance(params.get(key), str)
                or re.fullmatch(r"[A-Za-z0-9_]{1,512}", params[key]) is None
                for key in ("name", "language", "category")
            )
        ):
            raise RelayError("template_denied", 422)
        data = await upstream("GET", f"/inboxes/{cfg.chatwoot_relay_inbox_id}")
        if identifier(data.get("id")) != cfg.chatwoot_relay_inbox_id:
            raise RelayError("upstream_invalid", 503)
        templates = data.get("message_templates")
        if not isinstance(templates, list) or not any(
            isinstance(template, dict)
            and all(template.get(key) == params[key] for key in ("name", "language", "category"))
            and str(template.get("status", "")).upper() == "APPROVED"
            for template in templates
        ):
            raise RelayError("template_denied", 422)
        # Demo templates currently have no dynamic parameters or URL/button overrides.
        return {key: params[key] for key in ("name", "language", "category", "processed_params")}

    @app.get("/api/v1/accounts/{account_id}/conversations/{conversation_id}")
    async def get_conversation(account_id: str, conversation_id: str, request: Request):
        scope(account_id)
        no_query(request)
        return await checked_conversation(conversation_id)

    @app.post("/api/v1/accounts/{account_id}/conversations")
    async def create_conversation(account_id: str, request: Request):
        scope(account_id)
        no_query(request)
        body = await json_body(request)
        if (
            set(body) != {"source_id", "inbox_id", "contact_id", "status"}
            or body.get("status") != "pending"
            or not isinstance(body.get("source_id"), str)
        ):
            raise RelayError("invalid_request", 422)
        scope(account_id, body["inbox_id"])
        contact_id = identifier(body["contact_id"])
        async with mutation_lock:
            binding = await binding_for(await associated(contact_id))
            if body["source_id"] != binding["source_id"]:
                raise RelayError("channel_preparation_required", 409)
            existing = await upstream(
                "GET", f"/contacts/{contact_id}/conversations", unavailable=True
            )
            if any(
                isinstance(item, dict)
                and str(item.get("inbox_id")) == str(cfg.chatwoot_relay_inbox_id)
                and item.get("status") in {"open", "pending"}
                for item in payload_list(existing)
            ):
                raise RelayError("conversation_already_active", 409)
            created = await upstream(
                "POST",
                "/conversations",
                bot=True,
                body={
                    "contact_id": contact_id,
                    "inbox_id": cfg.chatwoot_relay_inbox_id,
                    "source_id": binding["source_id"],
                    "status": "pending",
                },
            )
            current = await checked_conversation(
                identifier(created.get("id")), expected_contact=contact_id
            )
            if current["status"] != "pending":
                raise RelayError("upstream_invalid", 503)
            return JSONResponse(current, status_code=201)

    @app.post("/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages")
    async def send_message(account_id: str, conversation_id: str, request: Request):
        scope(account_id)
        no_query(request)
        requested = identifier(conversation_id)
        body = await json_body(request, MAX_MESSAGE_BODY)
        if (
            set(body) - {"content", "message_type", "private", "template_params"}
            or body.get("message_type") != "outgoing"
            or not isinstance(body.get("private"), bool)
            or not isinstance(body.get("content"), str)
            or not 1 <= len(body["content"]) <= MAX_MESSAGE_CHARS
        ):
            raise RelayError("message_denied", 422)
        async with mutation_lock:
            template = None
            if "template_params" in body:
                if body["private"]:
                    raise RelayError("template_denied", 422)
                template = await approved_template(body["template_params"])
            current = await checked_conversation(requested)
            if current["status"] != "pending":
                raise RelayError("human_control", 409)
            if not body["private"] and template is None and current["can_reply"] is not True:
                raise RelayError("channel_cannot_reply", 409)
            outgoing = {key: body[key] for key in ("content", "message_type", "private")}
            if template is not None:
                outgoing["template_params"] = template
            sends.take()  # Durable and conservative: timeout/failure never refunds an attempt.
            data = await upstream(
                "POST", f"/conversations/{requested}/messages", body=outgoing, bot=True
            )
            if (
                str(data.get("inbox_id")) != str(cfg.chatwoot_relay_inbox_id)
                or identifier(data.get("conversation_id")) != requested
            ):
                raise RelayError("upstream_invalid", 503)
            return {"id": identifier(data.get("id"))}

    @app.post("/api/v1/accounts/{account_id}/conversations/{conversation_id}/toggle_status")
    async def open_conversation(account_id: str, conversation_id: str, request: Request):
        scope(account_id)
        no_query(request)
        body = await json_body(request)
        if body != {"status": "open"}:
            raise RelayError("status_denied", 422)
        async with mutation_lock:
            current = await checked_conversation(conversation_id)
            data = await upstream(
                "POST",
                f"/conversations/{current['id']}/toggle_status",
                body={"status": "open"},
                bot=True,
            )
            payload = data.get("payload")
            if (
                not isinstance(payload, dict)
                or identifier(payload.get("conversation_id")) != current["id"]
                or payload.get("current_status") != "open"
            ):
                raise RelayError("upstream_invalid", 503)
            return {"id": current["id"], "status": "open"}

    async def search_phone(number, page=1):
        data = await upstream("GET", "/contacts/search", params={"q": number, "page": page})
        return [
            contact
            for contact in payload_list(data)
            if isinstance(contact, dict) and contact.get("phone_number") == number
        ]

    @app.get("/api/v1/accounts/{account_id}/inboxes/{inbox_id}")
    async def get_inbox(account_id: str, inbox_id: str, request: Request):
        scope(account_id, inbox_id)
        no_query(request)
        data = await upstream("GET", f"/inboxes/{cfg.chatwoot_relay_inbox_id}")
        if identifier(data.get("id")) != cfg.chatwoot_relay_inbox_id:
            raise RelayError("upstream_invalid", 503)
        templates = data.get("message_templates", [])
        safe_templates = []
        if isinstance(templates, list):
            for template in templates:
                if isinstance(template, dict):
                    safe_templates.append(
                        {
                            k: v
                            for k, v in template.items()
                            if k in {"id", "name", "language", "category", "status"}
                            and isinstance(v, (str, int))
                            and not isinstance(v, bool)
                        }
                    )
        return {
            "id": cfg.chatwoot_relay_inbox_id,
            "name": "Bandeja demo",
            "channel_type": data.get("channel_type")
            if isinstance(data.get("channel_type"), str)
            and re.fullmatch(r"Channel::[A-Za-z0-9]{1,40}", data["channel_type"])
            else "",
            "message_templates": safe_templates,
        }

    @app.get("/api/v1/accounts/{account_id}/contacts")
    @app.get("/api/v1/accounts/{account_id}/contacts/search")
    async def search_contacts(account_id: str, request: Request):
        scope(account_id)
        query = request.query_params
        if (
            set(query) - {"q", "page"}
            or len(query.getlist("q")) != 1
            or len(query.getlist("page")) > 1
        ):
            raise RelayError("exact_phone_required", 422)
        number = phone(query.get("q"))
        page_value = query.get("page", "1")
        if (
            len(page_value) > 2
            or not page_value.isascii()
            or not page_value.isdigit()
            or not 1 <= int(page_value) <= 20
        ):
            raise RelayError("invalid_page", 422)
        contacts = await search_phone(number, int(page_value))
        result = [sanitized_contact(contact, cfg.chatwoot_relay_inbox_id) for contact in contacts]
        return {"payload": [contact for contact in result if contact is not None]}

    @app.get("/api/v1/accounts/{account_id}/contacts/{contact_id}/contactable_inboxes")
    async def contactable_inboxes(account_id: str, contact_id: str, request: Request):
        scope(account_id)
        no_query(request)
        await associated(contact_id)
        data = await upstream(
            "GET", f"/contacts/{identifier(contact_id)}/contactable_inboxes", unavailable=True
        )
        return {"payload": test_bindings(payload_list(data), cfg.chatwoot_relay_inbox_id)}

    @app.get("/api/v1/accounts/{account_id}/contacts/{contact_id}/conversations")
    async def conversations(account_id: str, contact_id: str, request: Request):
        scope(account_id)
        no_query(request)
        await associated(contact_id)
        data = await upstream(
            "GET", f"/contacts/{identifier(contact_id)}/conversations", unavailable=True
        )
        safe = []
        for conversation in payload_list(data):
            if not isinstance(conversation, dict) or str(conversation.get("inbox_id")) != str(
                cfg.chatwoot_relay_inbox_id
            ):
                continue
            try:
                item = {
                    "id": identifier(conversation.get("id")),
                    "inbox_id": cfg.chatwoot_relay_inbox_id,
                    "status": conversation.get("status")
                    if isinstance(conversation.get("status"), str)
                    and conversation.get("status") in {"open", "pending", "resolved", "snoozed"}
                    else "unavailable",
                    "can_reply": conversation.get("can_reply") is True,
                }
                binding = conversation.get("contact_inbox")
                filtered = test_bindings([binding], cfg.chatwoot_relay_inbox_id)
                if filtered:
                    item["contact_inbox"] = filtered[0]
                safe.append(item)
            except RelayError:
                continue
        return {"payload": safe}

    @app.post("/api/v1/accounts/{account_id}/contacts")
    async def create_contact(account_id: str, request: Request):
        scope(account_id)
        no_query(request)
        body = await json_body(request)
        if not isinstance(body, dict) or set(body) - {"inbox_id", "phone_number", "name"}:
            raise RelayError("invalid_request", 422)
        scope(account_id, str(body.get("inbox_id", "missing")))
        number = phone(body.get("phone_number"))
        if "name" in body and (not isinstance(body["name"], str) or len(body["name"]) > 120):
            raise RelayError("invalid_request", 422)
        existing = await search_phone(number)
        if existing:
            safe = [sanitized_contact(contact, cfg.chatwoot_relay_inbox_id) for contact in existing]
            if len(safe) != 1 or safe[0] is None:
                raise RelayError("channel_preparation_required", 409)
            return {"payload": {"contact": safe[0]}}
        creates.take()
        data = contact_object(
            await upstream(
                "POST",
                "/contacts",
                body={
                    "inbox_id": cfg.chatwoot_relay_inbox_id,
                    "phone_number": number,
                    "name": "Contacto demo",
                },
            )
        )
        # Re-read actual membership; POST success alone does not grant access to an ID.
        linked = await associated(identifier(data.get("id")))
        safe = sanitized_contact(linked, cfg.chatwoot_relay_inbox_id)
        if safe is None or safe["phone_number"] != number:
            raise RelayError("channel_preparation_required", 409)
        return JSONResponse({"payload": {"contact": safe}}, status_code=201)

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"],
    )
    async def deny(path: str):
        raise RelayError("relay_route_denied", 404)

    return app
