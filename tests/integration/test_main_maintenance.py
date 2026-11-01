"""ASGI recovery surface remains authenticated while durable maintenance is active."""

import importlib
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agil_shared.errors import DomainError
from backend import config
from backend.config import BackendSettings
from fastapi.testclient import TestClient


class SuspendedCentral:
    async def request(self, method, path, **kwargs):
        if method == "GET" and path == "/catalogs":
            return {"service_types": [], "document_types": []}
        assert method == "GET" and path == "/debts"
        raise DomainError(
            "maintenance",
            "Escenario en restauración; cartera temporalmente no disponible.",
            status=503,
            retryable=True,
        )


class SuspendedCampaigns:
    async def preview(self, *args, **kwargs):
        pytest.fail("Maintenance must stop campaign mutations before the service")

    async def create(self, *args, **kwargs):
        pytest.fail("Maintenance must stop campaign mutations before the service")


class ResumeDemo:
    """Service double retaining a previously persisted operation across HTTP retries."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.operation = str(uuid4())
        self.stage = "central_reset"
        self.calls = []

    async def reset(self, payload):
        self.calls.append(payload)
        assert payload == {"confirmation": "RESET_DEMO", "operation_key": self.operation}
        if len(self.calls) == 1:
            raise DomainError(
                "reset_busy",
                "El trabajo anterior sigue finalizando. Reintenta la misma operación.",
                status=409,
                retryable=True,
            )
        self.stage = "completed"
        self.runtime.maintenance_active = False
        return {
            "status": "complete",
            "operation_key": self.operation,
            "epoch": 2,
            "event_cutoff": 20,
        }


@pytest.fixture
def maintenance_app(monkeypatch):
    # Every required/private value is fictional and passed explicitly. No dotenv or
    # cached private get_settings values are refreshed by this regression suite.
    settings = BackendSettings(
        _env_file=None,
        app_env="test",
        public_base_url="http://testserver",
        operator_username="fixture",
        operator_password="fictional-operator-password",
        session_secret="fictional-session-" * 3,
        central_operator_token="fictional-operator-token-" * 2,
        central_agent_token="fictional-agent-token-" * 2,
        memory_db_password="fictional-db-password",
        openai_api_key="",
        langfuse_enabled=False,
        enable_local_message_endpoint=False,
    )
    original_loader = config.get_settings
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    main = importlib.import_module("backend.main")
    # Import-time app creation sees only fixture settings; restore the module alias
    # without calling it so later tests do not inherit this fixture's loader.
    main.get_settings = original_loader

    class Runtime:
        def __init__(self, supplied):
            assert supplied is settings
            self.settings = supplied
            self.maintenance_active = True
            self.operator_central = SuspendedCentral()
            self.campaigns = SuspendedCampaigns()
            self.identity = SimpleNamespace()
            self.demo = ResumeDemo(self)
            self.closed = False

        def maintenance(self):
            return self.maintenance_active

        async def close(self):
            self.closed = True

    monkeypatch.setattr(main, "Runtime", Runtime)
    monkeypatch.setattr(main, "configure_logging", lambda: None)
    app = main.create_app(settings)
    with TestClient(app) as client:
        yield client, app.state.runtime
    assert app.state.runtime.closed


def login(client):
    response = client.get("/login")
    assert response.status_code == 200
    token = re.search(r'name="csrf" value="([^"]+)"', response.text)[1]
    response = client.post(
        "/login",
        data={"username": "fixture", "password": "fictional-operator-password", "csrf": token},
        headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    response = client.get("/central")
    assert response.status_code == 200
    assert "Escenario en restauración" in response.text
    assert "Traceback" not in response.text and "fictional-db-password" not in response.text
    return re.search(r'name="csrf-token" content="([^"]+)"', response.text)[1]


def test_fresh_operator_can_login_and_logout_during_maintenance_with_csrf(maintenance_app):
    client, runtime = maintenance_app
    assert runtime.maintenance_active
    assert (
        client.post(
            "/login",
            data={"username": "fixture", "password": "fictional-operator-password"},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 403
    )
    token = login(client)
    assert runtime.maintenance_active
    assert client.post("/logout", headers={"Origin": "http://testserver"}).status_code == 403
    response = client.post(
        "/logout", headers={"Origin": "http://testserver", "X-CSRF-Token": token}
    )
    assert response.status_code == 200 and response.json()["redirect"] == "/login"
    assert client.get("/central", follow_redirects=False).status_code == 303
    assert runtime.maintenance_active


def test_mutations_stay_suspended_but_same_reset_operation_can_resume(maintenance_app):
    client, runtime = maintenance_app
    token = login(client)
    headers = {"Origin": "http://testserver", "X-CSRF-Token": token}
    for path, body in [
        (
            "/api/payments/fixture-order/attempts",
            {"capability": "fixture-capability", "decision": "approved"},
        ),
        ("/api/campaigns/preview", {}),
        ("/api/campaigns", {}),
        ("/webhooks/chatwoot", {"event": "message_created"}),
    ]:
        response = client.post(path, json=body, headers=headers)
        assert (
            response.status_code == (429 if path == "/webhooks/chatwoot" else 503)
            and response.json()["code"] == "maintenance"
        )
        assert response.json()["retryable"] and response.json()["correlation_id"]
    # Exempting reset from maintenance does not exempt operator auth or CSRF.
    assert (
        client.post(
            "/api/demo/reset",
            json={"confirmation": "REINICIAR DEMO"},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 403
    )
    reset_headers = {**headers, "Idempotency-Key": runtime.demo.operation}
    first = client.post(
        "/api/demo/reset", json={"confirmation": "REINICIAR DEMO"}, headers=reset_headers
    )
    assert first.status_code == 409 and runtime.demo.stage == "central_reset"
    assert runtime.maintenance_active
    resumed = client.post(
        "/api/demo/reset", json={"confirmation": "REINICIAR DEMO"}, headers=reset_headers
    )
    assert resumed.status_code == 200 and resumed.json()["status"] == "complete"
    assert runtime.demo.calls[0] == runtime.demo.calls[1]
    assert runtime.demo.stage == "completed" and not runtime.maintenance_active


def test_login_form_policy_preserves_origin_without_relaxing_csrf(maintenance_app):
    client, _ = maintenance_app
    page = client.get("/login")
    assert page.headers["referrer-policy"] == "same-origin"
    token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    fields = {"username": "fixture", "password": "fictional-operator-password", "csrf": token}
    denied = client.post("/login", data=fields, headers={"Origin": "null"}, follow_redirects=False)
    assert denied.status_code == 403 and denied.json()["code"] == "origin_denied"
    legitimate = client.post(
        "/login", data=fields, headers={"Origin": "http://testserver"}, follow_redirects=False
    )
    assert legitimate.status_code == 303
    assert client.get("/central").headers["referrer-policy"] == "no-referrer"


def test_main_keeps_payment_capability_pages_no_referrer(maintenance_app):
    client, _ = maintenance_app

    class PaymentCentral:
        async def request(self, method, path, **kwargs):
            assert method == "GET" and path == "/orders/fixture-order"
            assert kwargs["params"] == {"capability": "fictional-capability"}
            return {
                "id": "fixture-order",
                "status": "vigente",
                "base_cents": 10000,
                "payable_cents": 10000,
                "discount_cents": 0,
                "currency": "USD",
                "expires_at": "2026-11-02T12:00:00Z",
                "service_type": "Internet ficticio",
            }

    client.app.state.payment_central = PaymentCentral()
    page = client.get("/p/fixture-order?token=fictional-capability")
    assert page.status_code == 200
    assert page.headers["referrer-policy"] == "no-referrer"
    assert client.get("/p/fixture-order").headers["referrer-policy"] == "no-referrer"
