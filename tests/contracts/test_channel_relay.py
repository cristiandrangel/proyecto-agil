"""Restricted owner-side relay contracts; all upstream Chatwoot traffic is mocked."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

MODULE_PATH = Path(__file__).parents[2] / "infra/chatwoot-relay/main.py"
SPEC = importlib.util.spec_from_file_location("channel_relay", MODULE_PATH)
relay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relay
SPEC.loader.exec_module(relay)
ACCOUNT, INBOX = 77, 88
RELAY_TOKEN = "relay-fixture-" + "r" * 40
USER_TOKEN = "owner-user-token-fixture-" + "s" * 40
BOT_TOKEN = "owner-bot-token-fixture-" + "b" * 40
NUMBER = "+15551234567"
RAW_SOURCE = "  +opaque:0019  "
PRIVATE = "owner-private-data-and-provider-secret"


def contact(identifier=12, *, number=NUMBER, inbox=INBOX):
    return {
        "id": identifier,
        "phone_number": number,
        "name": PRIVATE,
        "email": PRIVATE,
        "identifier": PRIVATE,
        "custom_attributes": {"token": PRIVATE},
        "contact_inboxes": [
            {
                "source_id": RAW_SOURCE,
                "inbox": {"id": inbox, "provider_config": {"api_key": PRIVATE}},
                "token": PRIVATE,
            },
            {"source_id": PRIVATE, "inbox": {"id": 999}},
        ],
    }


class Upstream:
    def __init__(self):
        self.contacts = {12: contact()}
        self.calls = []
        self.redirect = False
        self.fail_create = False
        self.search_override = None
        self.conversations = {401: self.conversation()}
        self.fail_send = False
        self.message_counter = 600
        self.contactable_source = RAW_SOURCE

    def conversation(self, identifier=401, *, inbox=INBOX, contact_id=12, status="pending"):
        return {
            "id": identifier,
            "account_id": ACCOUNT,
            "inbox_id": inbox,
            "status": status,
            "can_reply": True,
            "meta": {"sender": {"id": contact_id, "name": PRIVATE}, "secret": PRIVATE},
            "messages": [{"content": PRIVATE}],
            "last_non_activity_message": PRIVATE,
            "custom_attributes": {"secret": PRIVATE},
        }

    async def __call__(self, request):
        self.calls.append(request)
        assert request.url.host == "chatwoot.internal"
        assert request.url.path.startswith(f"/api/v1/accounts/{ACCOUNT}/")
        suffix = request.url.path.split(f"/api/v1/accounts/{ACCOUNT}")[1]
        expected_token = (
            BOT_TOKEN
            if request.method == "POST" and suffix.startswith("/conversations")
            else USER_TOKEN
        )
        assert request.headers.get("api_access_token") == expected_token
        assert request.headers.get("authorization") is None
        assert request.headers.get("cookie") is None
        assert request.headers.get("x-source-account") is None
        if self.redirect:
            return httpx.Response(
                307, headers={"Location": "https://outside.invalid/steal"}, json={"token": PRIVATE}
            )
        suffix = request.url.path.split(f"/api/v1/accounts/{ACCOUNT}")[1]
        if suffix == f"/inboxes/{INBOX}":
            return httpx.Response(
                200,
                json={
                    "id": INBOX,
                    "name": PRIVATE,
                    "channel_type": "Channel::Whatsapp",
                    "provider_config": {"api_key": PRIVATE},
                    "api_access_token": PRIVATE,
                    "message_templates": [
                        {
                            "id": "template",
                            "name": "demo_notice",
                            "language": "es",
                            "status": "APPROVED",
                            "category": "UTILITY",
                            "provider_config": {"token": PRIVATE},
                            "components": [{"type": "BODY", "text": PRIVATE}],
                        }
                    ],
                },
            )
        if suffix == "/contacts/search":
            assert set(request.url.params) == {"q", "page"}
            payload = (
                self.search_override
                if self.search_override is not None
                else [
                    item
                    for item in self.contacts.values()
                    if item["phone_number"] == request.url.params["q"]
                ]
            )
            return httpx.Response(
                200, json={"payload": payload, "meta": {"count": 10000, "secret": PRIVATE}}
            )
        if suffix == "/contacts" and request.method == "POST":
            if self.fail_create:
                raise httpx.ReadTimeout(PRIVATE, request=request)
            body = json.loads(request.content)
            assert body == {
                "inbox_id": INBOX,
                "phone_number": body["phone_number"],
                "name": "Contacto demo",
            }
            identifier = 300 + len(self.contacts)
            self.contacts[identifier] = contact(identifier, number=body["phone_number"])
            return httpx.Response(
                200,
                json={"payload": {"contact": self.contacts[identifier]}, "owner_secret": PRIVATE},
            )
        parts = suffix.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "contacts":
            identifier = int(parts[1])
            if identifier not in self.contacts:
                return httpx.Response(404, json={"error": PRIVATE})
            if len(parts) == 2:
                return httpx.Response(200, json={"payload": self.contacts[identifier]})
            if parts[2] == "contactable_inboxes":
                return httpx.Response(
                    200,
                    json={
                        "payload": [{"inbox": {"id": INBOX}, "source_id": self.contactable_source}]
                    },
                )
            if parts[2] == "conversations":
                return httpx.Response(
                    200,
                    json={
                        "payload": [
                            conv
                            for conv in self.conversations.values()
                            if conv["meta"]["sender"]["id"] == identifier
                        ]
                        + [self.conversation(402, inbox=999)]
                    },
                )
        if suffix == "/conversations" and request.method == "POST":
            body = json.loads(request.content)
            assert set(body) == {"contact_id", "inbox_id", "source_id", "status"}
            assert body["inbox_id"] == INBOX and body["source_id"] == RAW_SOURCE
            created = self.conversation(450, contact_id=body["contact_id"])
            self.conversations[450] = created
            return httpx.Response(200, json=created)
        if len(parts) >= 2 and parts[0] == "conversations":
            conversation_id = int(parts[1])
            if conversation_id not in self.conversations:
                return httpx.Response(404, json={"secret": PRIVATE})
            if len(parts) == 2 and request.method == "GET":
                return httpx.Response(200, json=self.conversations[conversation_id])
            if parts[2] == "messages" and request.method == "POST":
                if self.fail_send:
                    raise httpx.ReadTimeout(PRIVATE, request=request)
                self.message_counter += 1
                return httpx.Response(
                    200,
                    json={
                        "id": self.message_counter,
                        "inbox_id": INBOX,
                        "conversation_id": conversation_id,
                        "content": PRIVATE,
                        "sender": {"token": PRIVATE},
                    },
                )
            if parts[2] == "toggle_status" and request.method == "POST":
                assert json.loads(request.content) == {"status": "open"}
                self.conversations[conversation_id]["status"] = "open"
                return httpx.Response(
                    200,
                    json={
                        "payload": {
                            "conversation_id": conversation_id,
                            "current_status": "open",
                            "secret": PRIVATE,
                        }
                    },
                )
        raise AssertionError("Unexpected upstream path")


def build(
    tmp_path, *, request_limit=60, create_limit=10, send_limit=100, clock=None, upstream=None
):
    settings = relay.RelaySettings(
        _env_file=None,
        chatwoot_upstream_base_url="http://chatwoot.internal:3000",
        chatwoot_upstream_api_token=USER_TOKEN,
        chatwoot_upstream_bot_token=BOT_TOKEN,
        chatwoot_relay_shared_token=RELAY_TOKEN,
        chatwoot_relay_account_id=ACCOUNT,
        chatwoot_relay_inbox_id=INBOX,
        chatwoot_relay_quota_path=str(tmp_path / "quota.sqlite3"),
        chatwoot_relay_requests_per_minute=request_limit,
        chatwoot_relay_creates_per_day=create_limit,
        chatwoot_relay_sends_per_day=send_limit,
    )
    mock = upstream or Upstream()
    kwargs = {"clock": clock} if clock else {}
    app = relay.create_app(settings, transport=httpx.MockTransport(mock), **kwargs)
    return app, mock


def client(app, *, authenticated=True):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://relay.test",
        headers={"Authorization": "Bearer " + RELAY_TOKEN} if authenticated else {},
    )


def assert_private_absent(response):
    assert PRIVATE not in response.text
    assert USER_TOKEN not in response.text
    assert BOT_TOKEN not in response.text
    assert RELAY_TOKEN not in response.text


@pytest.mark.asyncio
async def test_authentication_scopes_and_all_other_routes_fail_closed(tmp_path):
    app, upstream = build(tmp_path)
    async with client(app, authenticated=False) as api:
        assert (
            await api.get(f"/api/v1/accounts/{ACCOUNT}/contacts/search", params={"q": NUMBER})
        ).status_code == 401
        response = await api.get(
            f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}", headers={"api_access_token": RELAY_TOKEN}
        )
        assert response.status_code == 200
        assert (
            await api.get(
                f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}",
                headers={"Authorization": "Bearer wrong", "api_access_token": RELAY_TOKEN},
            )
        ).status_code == 401
    upstream.calls.clear()
    async with client(app) as api:
        for method, path in [
            ("GET", f"/api/v1/accounts/{ACCOUNT + 1}/contacts/search?q={NUMBER}"),
            ("GET", f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX + 1}"),
        ]:
            assert (await api.request(method, path)).status_code == 403
        for method, path in [
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
            ("GET", f"/api/v1/accounts/{ACCOUNT}/contacts/12"),
            ("DELETE", f"/api/v1/accounts/{ACCOUNT}/contacts/12"),
            ("PATCH", f"/api/v1/accounts/{ACCOUNT}/contacts/12"),
            ("GET", f"/api/v1/accounts/{ACCOUNT}/contacts/export"),
            ("GET", f"/api/v1/accounts/{ACCOUNT}/conversations/401/messages"),
            ("PUT", f"/api/v1/accounts/{ACCOUNT}/conversations/401"),
            ("POST", f"/api/v1/accounts/{ACCOUNT}/conversations/401/assignments"),
            ("GET", "/proxy/http://outside.invalid"),
        ]:
            response = await api.request(method, path)
            assert response.status_code == 404
            assert_private_absent(response)
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_search_requires_exact_e164_and_bounded_page_and_filters_membership(tmp_path):
    app, upstream = build(tmp_path)
    upstream.search_override = [
        contact(),
        contact(13, inbox=999),
        contact(14, number="+15550000000"),
    ]
    async with client(app) as api:
        for params in [
            {},
            {"q": "555"},
            {"q": "example@example.test"},
            {"q": NUMBER + "*"},
            {"q": NUMBER, "page": 0},
            {"q": NUMBER, "page": 21},
            {"q": NUMBER, "sort": "email"},
        ]:
            assert (
                await api.get(f"/api/v1/accounts/{ACCOUNT}/contacts/search", params=params)
            ).status_code == 422
        assert upstream.calls == []
        response = await api.get(
            f"/api/v1/accounts/{ACCOUNT}/contacts/search",
            params={"q": NUMBER, "page": 1},
            headers={"Cookie": "session=private", "X-Source-Account": "outside"},
        )
        assert response.status_code == 200
        contacts = response.json()["payload"]
        assert len(contacts) == 1
        assert contacts[0] == {
            "id": 12,
            "phone_number": NUMBER,
            "name": "Contacto demo",
            "contact_inboxes": [{"source_id": RAW_SOURCE, "inbox_id": INBOX}],
        }
        assert_private_absent(response)


@pytest.mark.asyncio
async def test_inbox_bindings_and_conversations_are_minimal_and_inbox_restricted(tmp_path):
    app, upstream = build(tmp_path)
    async with client(app) as api:
        inbox = await api.get(f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}")
        assert set(inbox.json()) == {"id", "name", "channel_type", "message_templates"}
        assert inbox.json()["message_templates"] == [
            {
                "id": "template",
                "name": "demo_notice",
                "language": "es",
                "status": "APPROVED",
                "category": "UTILITY",
            }
        ]
        assert_private_absent(inbox)
        binding = await api.get(f"/api/v1/accounts/{ACCOUNT}/contacts/12/contactable_inboxes")
        assert binding.json() == {"payload": [{"inbox_id": INBOX, "source_id": RAW_SOURCE}]}
        conversations = await api.get(f"/api/v1/accounts/{ACCOUNT}/contacts/12/conversations")
        assert conversations.json() == {
            "payload": [
                {
                    "id": 401,
                    "inbox_id": INBOX,
                    "status": "pending",
                    "can_reply": True,
                }
            ]
        }
        assert_private_absent(binding)
        assert_private_absent(conversations)
        upstream.contacts[13] = contact(13, inbox=999)
        upstream.calls.clear()
        for suffix in ("contactable_inboxes", "conversations"):
            response = await api.get(f"/api/v1/accounts/{ACCOUNT}/contacts/13/{suffix}")
            assert response.status_code == 404
            assert_private_absent(response)
        assert all(call.url.path.endswith("/contacts/13") for call in upstream.calls)


@pytest.mark.asyncio
async def test_create_whitelist_fixed_name_and_duplicate_elsewhere_does_not_expose_contact(
    tmp_path,
):
    app, upstream = build(tmp_path)
    async with client(app) as api:
        for body in [
            {"inbox_id": INBOX + 1, "phone_number": NUMBER},
            {"inbox_id": None, "phone_number": NUMBER},
            {"inbox_id": INBOX, "phone_number": "bad"},
            {"inbox_id": INBOX, "phone_number": NUMBER, "custom_attributes": {"owner": True}},
            {"inbox_id": INBOX, "phone_number": NUMBER, "email": "owner@example.test"},
        ]:
            assert (
                await api.post(f"/api/v1/accounts/{ACCOUNT}/contacts", json=body)
            ).status_code in {403, 422}
        assert upstream.calls == []
        existing = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/contacts",
            json={"inbox_id": INBOX, "phone_number": NUMBER, "name": "Someone's real name"},
        )
        assert existing.status_code == 200
        assert existing.json()["payload"]["contact"]["name"] == "Contacto demo"
        assert all(call.method == "GET" for call in upstream.calls)
        upstream.contacts[12] = contact(12, inbox=999)
        response = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/contacts", json={"inbox_id": INBOX, "phone_number": NUMBER}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "channel_preparation_required"
        assert "12" not in response.text
        assert_private_absent(response)
        new_phone = "+15550000199"
        created = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/contacts",
            json={"inbox_id": INBOX, "phone_number": new_phone, "name": "Private real name"},
        )
        assert created.status_code == 201
        assert created.json()["payload"]["contact"]["phone_number"] == new_phone
        assert "Private real name" not in created.text
        assert_private_absent(created)


@pytest.mark.asyncio
async def test_redirects_are_not_followed_and_upstream_bodies_stay_private(tmp_path):
    app, upstream = build(tmp_path)
    upstream.redirect = True
    async with client(app) as api:
        response = await api.get(f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}")
        assert response.status_code == 503
        assert len(upstream.calls) == 1
        assert_private_absent(response)


@pytest.mark.asyncio
async def test_global_rate_limit_is_bounded_and_recovers_after_window(tmp_path):
    now = [100.0]
    app, upstream = build(tmp_path, request_limit=2, clock=lambda: now[0])
    async with client(app) as one, client(app) as two:
        assert (await one.get(f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}")).status_code == 200
        assert (await two.get(f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}")).status_code == 200
        blocked = await one.get(f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert len(upstream.calls) == 2
        now[0] += 61
        assert (await two.get(f"/api/v1/accounts/{ACCOUNT}/inboxes/{INBOX}")).status_code == 200


@pytest.mark.asyncio
async def test_create_daily_quota_persists_across_restarts_and_holds_uncertain_attempt(tmp_path):
    app, upstream = build(tmp_path, create_limit=2)
    async with client(app) as api:
        for number in ("+15550000031", "+15550000032"):
            assert (
                await api.post(
                    f"/api/v1/accounts/{ACCOUNT}/contacts",
                    json={"inbox_id": INBOX, "phone_number": number},
                )
            ).status_code == 201
    restarted, _ = build(tmp_path, create_limit=2, upstream=upstream)
    async with client(restarted) as api:
        denied = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/contacts",
            json={"inbox_id": INBOX, "phone_number": "+15550000033"},
        )
        assert denied.status_code == 429
        assert denied.json()["code"] == "relay_create_limit"
    assert len([r for r in upstream.calls if r.method == "POST"]) == 2
    uncertain_app, failing = build(tmp_path / "uncertain", create_limit=1)
    failing.fail_create = True
    async with client(uncertain_app) as api:
        body = {"inbox_id": INBOX, "phone_number": "+15550000034"}
        assert (
            await api.post(f"/api/v1/accounts/{ACCOUNT}/contacts", json=body)
        ).status_code == 503
        assert (
            await api.post(f"/api/v1/accounts/{ACCOUNT}/contacts", json=body)
        ).status_code == 429
    assert len([r for r in failing.calls if r.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_body_size_query_duplicates_and_source_injection_do_not_reach_upstream(tmp_path):
    app, upstream = build(tmp_path)
    async with client(app) as api:
        response = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/contacts",
            content=b"x" * 4096,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        response = await api.get(
            f"/api/v1/accounts/{ACCOUNT}/contacts/search",
            params=[("q", NUMBER), ("q", "+15550000000")],
        )
        assert response.status_code == 422
        response = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/contacts",
            json={"inbox_id": INBOX, "phone_number": NUMBER, "source_id": "arbitrary-source"},
        )
        assert response.status_code == 422
    assert upstream.calls == []


def message(**overrides):
    return {
        "content": "Texto ficticio de prueba.",
        "message_type": "outgoing",
        "private": False,
        **overrides,
    }


def new_conversation(**overrides):
    return {
        "inbox_id": INBOX,
        "contact_id": 12,
        "source_id": RAW_SOURCE,
        "status": "pending",
        **overrides,
    }


@pytest.mark.asyncio
async def test_conversation_reads_strip_messages_and_writes_preserve_bot_actor(tmp_path):
    app, upstream = build(tmp_path)
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401"
    async with client(app) as api:
        response = await api.get(
            path, headers={"Cookie": "private", "X-Source-Account": "elsewhere"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": 401,
            "inbox_id": INBOX,
            "status": "pending",
            "can_reply": True,
        }
        assert_private_absent(response)
        sent = await api.post(path + "/messages", json=message())
        assert sent.status_code == 200 and sent.json() == {"id": 601}
        assert_private_absent(sent)
        private = await api.post(path + "/messages", json=message(private=True))
        assert private.status_code == 200
        opened = await api.post(path + "/toggle_status", json={"status": "open"})
        assert opened.status_code == 200 and opened.json() == {"id": 401, "status": "open"}
        assert_private_absent(opened)
    writes = [call for call in upstream.calls if call.method == "POST"]
    assert len(writes) == 3
    assert all(call.headers["api_access_token"] == BOT_TOKEN for call in writes)
    assert all(
        call.headers["api_access_token"] == USER_TOKEN
        for call in upstream.calls
        if call.method == "GET"
    )


@pytest.mark.asyncio
async def test_wrong_account_inbox_contact_and_binding_never_reach_bot_mutation(tmp_path):
    app, upstream = build(tmp_path)
    upstream.conversations[402] = upstream.conversation(402, inbox=999)
    upstream.conversations[403] = upstream.conversation(403, contact_id=13)
    upstream.contacts[13] = contact(13, inbox=999)
    upstream.conversations[404] = upstream.conversation(404)
    upstream.conversations[404]["contact_inbox"] = {
        "id": 112,
        "inbox_id": INBOX,
        "source_id": RAW_SOURCE.strip(),
    }
    upstream.conversations[405] = upstream.conversation(405)
    upstream.conversations[405]["account_id"] = ACCOUNT + 1
    async with client(app) as api:
        for conv in (402, 403, 404, 405, 999):
            path = f"/api/v1/accounts/{ACCOUNT}/conversations/{conv}"
            for method, suffix, body in (
                ("GET", "", None),
                ("POST", "/messages", message()),
                ("POST", "/toggle_status", {"status": "open"}),
            ):
                response = await api.request(
                    method, path + suffix, **({"json": body} if body else {})
                )
                assert response.status_code == 404
                assert_private_absent(response)
        for suffix, body in (("/messages", message()), ("/toggle_status", {"status": "open"})):
            response = await api.post(
                f"/api/v1/accounts/{ACCOUNT + 1}/conversations/401" + suffix, json=body
            )
            assert response.status_code == 403
    assert all(call.method == "GET" for call in upstream.calls)


@pytest.mark.asyncio
async def test_create_requires_exact_existing_source_and_only_pending_without_active_human(
    tmp_path,
):
    app, upstream = build(tmp_path)
    path = f"/api/v1/accounts/{ACCOUNT}/conversations"
    async with client(app) as api:
        for body in (
            new_conversation(inbox_id=999),
            new_conversation(source_id=RAW_SOURCE.strip()),
            new_conversation(status="open"),
            new_conversation(message=message()),
            new_conversation(contact_id=13),
            new_conversation(assignee_id=123),
        ):
            response = await api.post(path, json=body)
            assert response.status_code in {403, 404, 409, 422}
            assert_private_absent(response)
        for status in ("open", "pending"):
            upstream.conversations[401]["status"] = status
            assert (await api.post(path, json=new_conversation())).status_code == 409
        assert all(call.method == "GET" for call in upstream.calls)
        upstream.conversations[401]["status"] = "resolved"
        response = await api.post(path, json=new_conversation())
        assert response.status_code == 201
        assert response.json()["id"] == 450 and response.json()["status"] == "pending"
        assert "contact_inbox" not in response.json()
        assert_private_absent(response)
        assert (await api.post(path, json=new_conversation())).status_code == 409
    writes = [call for call in upstream.calls if call.method == "POST"]
    assert len(writes) == 1 and writes[0].headers["api_access_token"] == BOT_TOKEN
    assert json.loads(writes[0].content) == new_conversation()


@pytest.mark.asyncio
async def test_message_whitelist_open_control_and_open_only_status(tmp_path):
    app, upstream = build(tmp_path)
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401"
    async with client(app) as api:
        for body in (
            message(message_type="incoming"),
            message(private="false"),
            message(sender_id=12),
            message(attachments=["https://outside.invalid"]),
            message(content_type="input_select"),
            message(source_id="spoof"),
            message(content=""),
            message(content="x" * 20001),
        ):
            response = await api.post(path + "/messages", json=body)
            assert response.status_code == 422
            assert_private_absent(response)
        for body in (
            {},
            {"status": "pending"},
            {"status": "resolved"},
            {"status": "open", "assignee_id": 12},
        ):
            assert (await api.post(path + "/toggle_status", json=body)).status_code == 422
        assert upstream.calls == []
        upstream.conversations[401]["status"] = "open"
        for private in (False, True):
            assert (
                await api.post(path + "/messages", json=message(private=private))
            ).status_code == 409
        upstream.conversations[401]["status"] = "pending"
        upstream.conversations[401]["can_reply"] = False
        assert (await api.post(path + "/messages", json=message())).status_code == 409
        assert (await api.post(path + "/messages", json=message(private=True))).status_code == 200
    assert len([call for call in upstream.calls if call.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_template_matches_current_approved_catalog_and_has_no_parameter_override(tmp_path):
    app, upstream = build(tmp_path)
    upstream.conversations[401]["can_reply"] = False
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401/messages"
    template = {
        "name": "demo_notice",
        "language": "es",
        "category": "UTILITY",
        "processed_params": {},
    }
    async with client(app) as api:
        for params in (
            {**template, "name": "not_approved"},
            {**template, "category": "MARKETING"},
            {**template, "processed_params": {"buttons": ["https://outside.invalid"]}},
            {**template, "url": "https://outside.invalid"},
        ):
            response = await api.post(path, json=message(template_params=params))
            assert response.status_code == 422
            assert_private_absent(response)
        assert (
            await api.post(path, json=message(private=True, template_params=template))
        ).status_code == 422
        assert all(call.method == "GET" for call in upstream.calls)
        response = await api.post(path, json=message(template_params=template))
        assert response.status_code == 200 and response.json() == {"id": 601}
    writes = [call for call in upstream.calls if call.method == "POST"]
    assert len(writes) == 1 and json.loads(writes[0].content)["template_params"] == template


@pytest.mark.asyncio
async def test_twenty_thousand_unicode_characters_fit_bounded_json_but_contacts_stay_small(
    tmp_path,
):
    app, upstream = build(tmp_path)
    async with client(app) as api:
        body = message(content="\U0001f4ac" * 20000)
        # Worst-case JSON surrogate escaping is larger than ordinary UTF-8 JSON.
        response = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/conversations/401/messages",
            content=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert_private_absent(response)
        assert len(json.loads(upstream.calls[-1].content)["content"]) == 20000
        too_big = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/conversations/401/messages",
            content=b"x" * (relay.MAX_MESSAGE_BODY + 1),
            headers={"Content-Type": "application/json"},
        )
        assert too_big.status_code == 413
        contact_body = {"inbox_id": INBOX, "phone_number": NUMBER, "name": "x" * 3000}
        assert (
            await api.post(f"/api/v1/accounts/{ACCOUNT}/contacts", json=contact_body)
        ).status_code == 413
    assert len([call for call in upstream.calls if call.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_send_quota_persists_independently_of_contacts_and_holds_timeout(tmp_path):
    app, upstream = build(tmp_path, create_limit=1, send_limit=1)
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401/messages"
    async with client(app) as api:
        assert (
            await api.post(
                f"/api/v1/accounts/{ACCOUNT}/contacts",
                json={"inbox_id": INBOX, "phone_number": "+15550000701"},
            )
        ).status_code == 201
        upstream.fail_send = True
        assert (await api.post(path, json=message())).status_code == 503
        assert (await api.post(path, json=message())).status_code == 429
    assert (
        len(
            [
                call
                for call in upstream.calls
                if call.method == "POST" and call.url.path.endswith("/messages")
            ]
        )
        == 1
    )
    restarted, _ = build(tmp_path, create_limit=1, send_limit=1, upstream=upstream)
    async with client(restarted) as api:
        response = await api.post(path, json=message())
        assert response.status_code == 429 and response.json()["code"] == "relay_send_limit"
        assert_private_absent(response)
    other, other_upstream = build(tmp_path / "independent", create_limit=1, send_limit=1)
    async with client(other) as api:
        assert (await api.post(path, json=message())).status_code == 200
        assert (
            await api.post(
                f"/api/v1/accounts/{ACCOUNT}/contacts",
                json={"inbox_id": INBOX, "phone_number": "+15550000702"},
            )
        ).status_code == 201


@pytest.mark.asyncio
async def test_send_quota_is_atomic_across_relay_instances(tmp_path):
    import asyncio

    app, upstream = build(tmp_path, send_limit=1)
    other, _ = build(tmp_path, send_limit=1, upstream=upstream)
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401/messages"
    async with client(app) as one, client(other) as two:
        responses = await asyncio.gather(
            one.post(path, json=message()), two.post(path, json=message())
        )
    assert sorted(response.status_code for response in responses) == [200, 429]
    assert len([call for call in upstream.calls if call.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_existing_backend_client_uses_only_relay_credentials_without_adapter_changes(
    tmp_path,
):
    from types import SimpleNamespace

    from backend.integrations.chatwoot import ChatwootClient
    from pydantic import SecretStr

    app, upstream = build(tmp_path)
    cfg = SimpleNamespace(
        chatwoot_base_url="http://relay.test",
        chatwoot_contacts_base_url="http://relay.test",
        chatwoot_api_token=SecretStr(RELAY_TOKEN),
        chatwoot_contacts_api_token=SecretStr(RELAY_TOKEN),
        chatwoot_auth_scheme="api_access_token",
        chatwoot_account_id=ACCOUNT,
        chatwoot_inbox_id=INBOX,
    )
    adapter = ChatwootClient(cfg, transport=httpx.ASGITransport(app))
    binding = await adapter.resolve_contact(
        {
            "phone_e164": NUMBER,
            "test_contact_enabled": True,
            "delivery_mode": "live",
        }
    )
    assert binding == {
        "account_id": str(ACCOUNT),
        "inbox_id": str(INBOX),
        "contact_id": "12",
        "source_id": RAW_SOURCE,
        "conversation_id": "401",
    }
    assert await adapter.send_template(
        binding, {"name": "demo_notice", "language": "es", "category": "UTILITY"}, "fixture-op"
    ) == {"message_id": "601"}
    assert (await adapter.send_message("401", "Texto ficticio."))["id"] == 602
    assert (await adapter.send_message("401", "Nota ficticia.", private=True))["id"] == 603
    assert await adapter.set_open("401") == {"id": 401, "status": "open"}
    assert all(
        call.headers["api_access_token"] in {USER_TOKEN, BOT_TOKEN} for call in upstream.calls
    )


@pytest.mark.asyncio
async def test_installed_shape_multiple_aliases_without_binding_ids_never_invents_conversation_source(
    tmp_path,
):
    app, upstream = build(tmp_path)
    # Installed serializer: contact_inboxes have only inbox/source_id, and the
    # conversation exposes meta.sender but no contact_inbox. Both aliases belong
    # to the same contact/inbox; the canonical contactable destination is distinct.
    upstream.contacts[12]["contact_inboxes"].insert(
        0, {"source_id": "fictional-older-alias", "inbox": {"id": INBOX}}
    )
    upstream.contacts[12]["contact_inboxes"].append(
        {"source_id": "fictional-other-inbox-older-alias", "inbox": {"id": 999}}
    )
    persisted = upstream.contacts[12]["contact_inboxes"]
    assert len(persisted) == 4
    assert all("id" not in item for item in persisted)
    assert sum(item["inbox"]["id"] == INBOX for item in persisted) == 2
    assert sum(item["inbox"]["id"] == 999 for item in persisted) == 2
    upstream.conversations[401]["status"] = "open"
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401"
    async with client(app) as api:
        response = await api.get(path)
        assert response.status_code == 200
        assert response.json() == {
            "id": 401,
            "inbox_id": INBOX,
            "status": "open",
            "can_reply": True,
        }
        assert "source_id" not in response.text and "contact_inbox" not in response.text
        assert_private_absent(response)
        assert (await api.post(path + "/messages", json=message())).status_code == 409
        upstream.conversations[401]["status"] = "pending"
        # Exact conversation target remains authorized without selecting an alias.
        assert (await api.post(path + "/messages", json=message())).status_code == 200
        upstream.conversations[401]["status"] = "resolved"
        created = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/conversations", json=new_conversation()
        )
        assert created.status_code == 201
    writes = [call for call in upstream.calls if call.method == "POST"]
    assert json.loads(writes[-1].content)["source_id"] == RAW_SOURCE
    assert all(call.headers["api_access_token"] == BOT_TOKEN for call in writes)


@pytest.mark.asyncio
async def test_explicit_conversation_binding_is_checked_against_exact_persisted_alias(tmp_path):
    app, upstream = build(tmp_path)
    alias = "fictional-specific-conversation-alias"
    upstream.contacts[12]["contact_inboxes"].append({"source_id": alias, "inbox": {"id": INBOX}})
    upstream.conversations[401]["contact_inbox"] = {"source_id": alias, "inbox_id": INBOX}
    path = f"/api/v1/accounts/{ACCOUNT}/conversations/401"
    async with client(app) as api:
        response = await api.get(path)
        assert response.status_code == 200
        assert response.json()["contact_inbox"] == {"source_id": alias, "inbox_id": INBOX}
        upstream.conversations[401]["contact_inbox"]["source_id"] = "unlinked-alias"
        assert (await api.get(path)).status_code == 404
        assert (await api.post(path + "/messages", json=message())).status_code == 404
    assert all(call.method == "GET" for call in upstream.calls)


@pytest.mark.asyncio
async def test_new_conversation_canonical_source_must_already_belong_to_same_contact_and_inbox(
    tmp_path,
):
    app, upstream = build(tmp_path)
    upstream.conversations[401]["status"] = "resolved"
    upstream.contactable_source = "canonical-not-persisted-in-this-inbox"
    async with client(app) as api:
        response = await api.post(
            f"/api/v1/accounts/{ACCOUNT}/conversations",
            json=new_conversation(source_id=upstream.contactable_source),
        )
        assert response.status_code == 409
        assert response.json()["code"] == "channel_preparation_required"
        assert_private_absent(response)
    assert all(call.method == "GET" for call in upstream.calls)
