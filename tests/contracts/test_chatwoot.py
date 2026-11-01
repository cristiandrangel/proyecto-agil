"""Chatwoot and diagnostic scripts: bytes, scope and no untracked/live side effects."""

import hashlib
import hmac
import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from agil_shared.errors import DomainError
from backend.integrations.chatwoot import ChatwootClient, verify_signature
from pydantic import SecretStr


def load_script(name):
    path = Path(__file__).resolve().parents[2] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = load_script("preflight")
demo_message = load_script("demo_message")
run_preflight = preflight.run_preflight
send_local = demo_message.send_local


@pytest.fixture
def settings():
    return SimpleNamespace(
        chatwoot_webhook_auth_mode="hmac",
        chatwoot_webhook_secret=SecretStr("fictional-webhook-secret"),
        chatwoot_relay_token=SecretStr("fictional-relay-secret"),
        chatwoot_webhook_tolerance_seconds=300,
        chatwoot_base_url="https://channel.example",
        chatwoot_api_token=SecretStr("fictional-channel-token"),
        chatwoot_contacts_api_token=SecretStr("fictional-service-contacts-token"),
        chatwoot_account_id=9,
        chatwoot_inbox_id=7,
        chatwoot_auth_scheme="api_access_token",
        public_base_url="http://demo.example",
        central_api_url="http://central.example",
        openai_api_key=SecretStr("fictional-openai-key"),
        openai_agent_model="agent-fixture",
        openai_vision_model="vision-fixture",
        openai_transcription_model="transcription-fixture",
        langfuse_enabled=False,
        operator_username="fictional-operator",
        operator_password=SecretStr("fictional-private-password"),
        session_secret=SecretStr("fictional-private-session"),
        central_operator_token=SecretStr("fictional-central-operator"),
        central_agent_token=SecretStr("fictional-central-agent"),
    )


def signed(settings, raw, timestamp=None):
    timestamp = str(int(time.time() if timestamp is None else timestamp))
    signature = hmac.new(
        settings.chatwoot_webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return {"x-chatwoot-timestamp": timestamp, "x-chatwoot-signature": "sha256=" + signature}


def test_signature_uses_original_bytes_and_timestamp_without_echoing_secrets(settings):
    raw = '{ "content": "sí", "id": 1 }'.encode()
    headers = signed(settings, raw)
    verify_signature(settings, headers, raw)
    for altered, given in [
        (raw + b" ", headers),
        (raw, signed(settings, raw, time.time() - 301)),
        (raw, signed(settings, raw, time.time() + 301)),
        (raw, {"x-chatwoot-timestamp": "bad", "x-chatwoot-signature": "secret"}),
        (raw, {**headers, "x-chatwoot-signature": "firma-ñ"}),
    ]:
        with pytest.raises(DomainError) as caught:
            verify_signature(settings, given, altered)
        assert caught.value.status == 401 and "fictional-webhook-secret" not in caught.value.message
    settings.chatwoot_webhook_secret = SecretStr("")
    with pytest.raises(DomainError):
        verify_signature(settings, signed(settings, raw), raw)


def test_relay_requires_exact_private_bearer(settings):
    settings.chatwoot_webhook_auth_mode = "relay"
    verify_signature(settings, {"authorization": "Bearer fictional-relay-secret"}, b"fixture")
    for authorization in ("", "Bearer wrong", "Bearer ñ"):
        with pytest.raises(DomainError) as caught:
            verify_signature(settings, {"authorization": authorization}, b"fixture")
        assert caught.value.status == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["api_access_token", "bearer"])
async def test_client_one_auth_scheme_and_account_scoped_path(settings, scheme):
    settings.chatwoot_auth_scheme = scheme
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": 11, "inbox_id": 7, "status": "pending"})

    await ChatwootClient(settings, transport=httpx.MockTransport(handler)).conversation("11")
    assert seen[0].url.path == "/api/v1/accounts/9/conversations/11"
    assert ("api_access_token" in seen[0].headers) != ("authorization" in seen[0].headers)


@pytest.mark.asyncio
async def test_private_note_allowed_open_but_public_message_needs_pending_and_can_reply(settings):
    seen = []
    status, can_reply = "open", True

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200, json={"id": 1, "inbox_id": 7, "status": status, "can_reply": can_reply}
        )

    client = ChatwootClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError) as caught:
        await client.send_message("11", "Demo")
    assert caught.value.code == "human_control" and all(request.method == "GET" for request in seen)
    await client.send_message("11", "Private demo note", private=True)
    assert json.loads(seen[-1].content)["private"] is True
    status, can_reply = "pending", False
    with pytest.raises(DomainError) as caught:
        await client.send_message("11", "Demo")
    assert caught.value.code == "channel_cannot_reply" and seen[-1].method == "GET"


@pytest.mark.asyncio
async def test_wrong_inbox_cannot_write_or_toggle(settings):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": 11, "inbox_id": 999, "status": "pending"})

    client = ChatwootClient(settings, transport=httpx.MockTransport(handler))
    for operation in [client.send_message("11", "demo"), client.set_open("11")]:
        with pytest.raises(DomainError) as caught:
            await operation
        assert caught.value.status == 403
    assert all(request.method == "GET" for request in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (500, "channel_uncertain"),
        (502, "channel_uncertain"),
        (408, "channel_uncertain"),
        (422, "channel_rejected"),
    ],
)
async def test_mutation_server_error_is_uncertain_without_repeating(settings, status, code):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, text="PRIVATE-PROVIDER-BODY")

    with pytest.raises(DomainError) as caught:
        await ChatwootClient(settings, transport=httpx.MockTransport(handler)).request(
            "POST", "/conversations/11/messages", json={"content": "demo"}
        )
    assert caught.value.code == code and not caught.value.retryable and len(seen) == 1
    assert "PRIVATE-PROVIDER-BODY" not in caught.value.message


@pytest.mark.asyncio
async def test_resolve_contact_exact_phone_and_literal_source_from_binding(settings):
    source = " whatsapp:+573000000001 #opaque "
    seen = []
    customer = {
        "phone_e164": "+573000000001",
        "test_contact_enabled": True,
        "delivery_mode": "live",
    }

    def handler(request):
        seen.append(request)
        path = request.url.path
        if path.endswith("/contacts/search"):
            return httpx.Response(
                200,
                json={
                    "payload": [
                        {"id": 1, "phone_number": "+573000000009"},
                        {"id": 2, "phone_number": customer["phone_e164"]},
                    ]
                },
            )
        if path.endswith("/contactable_inboxes"):
            assert "/contacts/2/" in path
            return httpx.Response(
                200, json={"payload": [{"inbox": {"id": 7}, "source_id": source}]}
            )
        if path.endswith("/contacts/2/conversations"):
            return httpx.Response(
                200, json={"payload": [{"id": 11, "inbox_id": 7, "status": "pending"}]}
            )
        raise AssertionError(path)

    binding = await ChatwootClient(
        settings, transport=httpx.MockTransport(handler)
    ).resolve_contact(customer)
    assert binding["source_id"] == source and binding["contact_id"] == "2"
    assert all(request.method == "GET" for request in seen)


@pytest.mark.asyncio
async def test_preflight_default_only_gets_and_no_inference_or_channel_writes(
    settings, monkeypatch
):
    seen = []

    async def forbidden(*args, **kwargs):
        pytest.fail("Default preflight cannot infer")

    monkeypatch.setattr(preflight, "tracked_inference", forbidden)

    def handler(request):
        seen.append(request)
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": model}
                        for model in ["agent-fixture", "vision-fixture", "transcription-fixture"]
                    ]
                },
            )
        if request.url.path.endswith("/inboxes/7"):
            return httpx.Response(200, json={"id": 7, "name": "PRIVATE-INBOX-NAME"})
        return httpx.Response(200, json={"status": "ok"})

    result = await run_preflight(settings, transport=httpx.MockTransport(handler))
    assert (
        result["status"] == "ok"
        and result["channel_writes"] == 0
        and not result["inference_opt_in"]
    )
    assert all(request.method == "GET" for request in seen)
    assert "fictional-" not in json.dumps(result) and "PRIVATE-INBOX-NAME" not in json.dumps(result)


@pytest.mark.asyncio
async def test_preflight_langfuse_sdk_auth_check_is_read_only(settings, monkeypatch):
    settings.langfuse_enabled = True
    settings.langfuse_base_url = "http://langfuse.example"
    settings.langfuse_public_key = SecretStr("fixture-public")
    settings.langfuse_secret_key = SecretStr("fixture-secret")
    calls = []

    class SDK:
        def __init__(self, **kwargs):
            assert kwargs["tracing_enabled"] is False

        def auth_check(self):
            calls.append("auth_check")
            return True

    monkeypatch.setattr("langfuse.Langfuse", SDK)
    result = await run_preflight(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [], "id": 7})
        ),
    )
    assert calls == ["auth_check"]
    assert any(
        check["check"] == "langfuse_auth" and check["status"] == "ok" for check in result["checks"]
    )
    assert "fixture-secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_demo_script_private_login_csrf_then_poll_sanitized_reply(settings):
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "GET" and request.url.path == "/login":
            return httpx.Response(
                200,
                text='<input name="csrf" value="login-csrf">',
                headers={"Set-Cookie": "session=fictional; Path=/"},
            )
        if request.method == "POST" and request.url.path == "/login":
            assert (
                b"fictional-private-password" in request.content
                and b"login-csrf" in request.content
            )
            return httpx.Response(303)
        if request.url.path == "/central":
            return httpx.Response(200, text='<meta name="csrf-token" content="rotated-csrf">')
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["source_id"] == "literal-source" and payload["live_inference"] is True
            assert (
                request.headers["X-CSRF-Token"] == "rotated-csrf"
                and request.headers["Origin"] == "http://demo.example"
            )
            return httpx.Response(200, json={"event_id": "demo-event"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "responses": [
                    {
                        "content": "Demo literal-source https://demo.example/p/order?token=PRIVATE-CAPABILITY",
                        "state": "sent",
                    }
                ],
            },
        )

    result = await send_local(
        settings,
        source_id="literal-source",
        content="Hola ficticio",
        transport=httpx.MockTransport(handler),
    )
    assert result["status"] == "completed"
    assert "literal-source" not in json.dumps(result) and "PRIVATE-CAPABILITY" not in json.dumps(
        result
    )
    assert "fictional-private-password" not in json.dumps(result)
    assert [request.url.path for request in seen] == [
        "/login",
        "/login",
        "/central",
        "/api/demo/messages",
        "/api/demo/messages/demo-event",
    ]


def test_demo_cli_requires_explicit_live_before_loading_configuration():
    with pytest.raises(SystemExit) as caught:
        demo_message.main(["--source-id", "fixture-source", "--content", "Hola ficticio"])
    assert caught.value.code == 2


@pytest.mark.asyncio
async def test_live_preflight_one_bounded_sdk_call_reserves_budget_first(settings, monkeypatch):
    from contextlib import nullcontext
    from decimal import Decimal
    from uuid import uuid4

    order = []
    settings.memory_database_url = "postgresql+psycopg://fixture:fictional@127.0.0.1:1/none"
    settings.ai_local_spend_limit_usd = Decimal("4.50")
    settings.ai_max_concurrent_requests = 2
    settings.ai_max_output_tokens = 4096
    settings.ai_max_input_tokens = 12000
    settings.ai_max_calls_per_turn = 5
    settings.openai_timeout_seconds = 45
    settings.openai_agent_model = "gpt-5.6-luna"
    settings.openai_agent_reasoning_effort = "high"
    settings.model_copy = lambda update: SimpleNamespace(**(vars(settings) | update))

    class Budget:
        def __init__(self, sessions, **kwargs):
            assert kwargs == {"limit_usd": Decimal("4.50"), "max_active_calls": 2}

        def reserve(self, **kwargs):
            order.append("reserve")
            assert kwargs["reserved_usd"] > 0
            return SimpleNamespace(id=uuid4())

        def settle(self, *args, **kwargs):
            order.append("settle")
            return SimpleNamespace(actual_usd=Decimal("0.0000044"))

        def mark_uncertain(self, *args, **kwargs):
            pytest.fail("Fixture response must settle normally")

    class SDK:
        def __init__(self, **kwargs):
            self.responses = self

        async def create(self, **kwargs):
            order.append("create")
            assert order[0] == "reserve" and kwargs["max_output_tokens"] == 256
            assert kwargs["tools"] == [] and kwargs["store"] is False
            return SimpleNamespace(
                id="fixture-response",
                status="completed",
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=2,
                    input_tokens_details={"cached_tokens": 0, "cache_write_tokens": 0},
                ),
            )

        async def close(self):
            order.append("close")

    class Observability:
        def __init__(self, settings):
            pass

        def span(self, *args, **kwargs):
            return nullcontext()

        def flush(self):
            pass

    monkeypatch.setattr("backend.services.budget.BudgetService", Budget)
    monkeypatch.setattr("backend.integrations.openai.AsyncOpenAI", SDK)
    monkeypatch.setattr("backend.integrations.observability.Observability", Observability)
    report = preflight.Report()
    await preflight.tracked_inference(settings, report)
    assert order == ["reserve", "create", "settle", "close"]
    assert report.result()["status"] == "ok"
    assert report.result()["channel_writes"] == 0


@pytest.mark.asyncio
async def test_contacts_and_inboxes_use_service_token_never_bot_or_admin_fallback(settings):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": 7})

    client = ChatwootClient(settings, transport=httpx.MockTransport(handler))
    for path in ("/contacts/search", "/contacts/2/conversations", "/inboxes/7"):
        await client.request("GET", path)
        assert seen[-1].headers["api_access_token"] == "fictional-service-contacts-token"
    for path in ("/conversations/11", "/conversations/11/messages"):
        await client.request("GET", path)
        assert seen[-1].headers["api_access_token"] == "fictional-channel-token"
    settings.chatwoot_contacts_api_token = SecretStr("")
    prior = len(seen)
    with pytest.raises(DomainError) as caught:
        await client.request("GET", "/contacts/search")
    assert caught.value.code == "channel_contacts_not_configured" and len(seen) == prior
    del settings.chatwoot_contacts_api_token
    with pytest.raises(DomainError) as caught:
        await client.request("GET", "/inboxes/7")
    assert caught.value.code == "channel_contacts_not_configured" and len(seen) == prior


@pytest.mark.asyncio
async def test_contact_relay_and_bot_keep_credentials_on_their_own_origins(settings):
    settings.chatwoot_contacts_base_url = "https://contacts-relay.example/"
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": 7})

    client = ChatwootClient(settings, transport=httpx.MockTransport(handler))
    for path in ("/contacts/search", "/contacts/2/conversations", "/inboxes/7"):
        await client.request("GET", path)
    for path in ("/conversations/11", "/conversations/11/messages"):
        await client.request("GET", path)
    for request in seen[:3]:
        assert request.url.host == "contacts-relay.example"
        assert request.headers["api_access_token"] == "fictional-service-contacts-token"
        assert "fictional-channel-token" not in str(request.headers)
    for request in seen[3:]:
        assert request.url.host == "channel.example"
        assert request.headers["api_access_token"] == "fictional-channel-token"
        assert "fictional-service-contacts-token" not in str(request.headers)
    assert [request.url.path for request in seen] == [
        "/api/v1/accounts/9/contacts/search",
        "/api/v1/accounts/9/contacts/2/conversations",
        "/api/v1/accounts/9/inboxes/7",
        "/api/v1/accounts/9/conversations/11",
        "/api/v1/accounts/9/conversations/11/messages",
    ]


@pytest.mark.asyncio
async def test_relay_redirect_and_path_traversal_cannot_move_credentials(settings):
    settings.chatwoot_contacts_base_url = "https://contacts-relay.example"
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://untrusted.example/collect"})

    client = ChatwootClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError):
        await client.request("GET", "/contacts/search")
    assert len(seen) == 1 and seen[0].url.host == "contacts-relay.example"
    for path in (
        "/contacts/../conversations/11",
        "/contacts/%2e%2e/conversations/11",
        "//untrusted.example",
        "https://untrusted.example/contacts",
        "/contacts/search?token=forged",
    ):
        with pytest.raises(DomainError) as caught:
            await client.request("GET", path)
        assert caught.value.code == "invalid_channel_path"
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_preflight_optional_relay_origin_validated_and_redacted(settings):
    settings.chatwoot_contacts_base_url = "https://contacts-relay.example"
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/inboxes/7"):
            assert request.url.host == "contacts-relay.example"
            assert request.headers["api_access_token"] == "fictional-service-contacts-token"
        return httpx.Response(200, json={"id": 7, "data": []})

    result = await run_preflight(settings, transport=httpx.MockTransport(handler))
    assert any(
        check["check"] == "chatwoot_contacts_route" and check["status"] == "ok"
        for check in result["checks"]
    )
    assert "contacts-relay.example" not in json.dumps(
        result
    ) and "fictional-service-contacts-token" not in json.dumps(result)
    settings.chatwoot_contacts_base_url = "https://user:private@untrusted.example?token=private"
    seen.clear()
    result = await run_preflight(settings, transport=httpx.MockTransport(handler))
    assert any(
        check["check"] == "chatwoot_contacts_route" and check["status"] == "fail"
        for check in result["checks"]
    )
    assert not any("/inboxes/" in request.url.path for request in seen)
    assert "private@" not in json.dumps(result)
