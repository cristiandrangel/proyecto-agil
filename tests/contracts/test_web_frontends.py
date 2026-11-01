"""Web security/financial boundaries exercised without providers or real customer data."""

import re
from types import SimpleNamespace

import httpx
import pytest
from agil_shared.errors import DomainError
from backend.api import operator, payments
from backend.integrations.central import CentralClient
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import SecretStr


class FakeCentral:
    def __init__(self):
        self.calls = []
        self.order = {
            "id": "order-demo",
            "status": "vigente",
            "service_type": "Internet ficticio",
            "base_cents": 10000,
            "payable_cents": 8000,
            "discount_cents": 2000,
            "currency": "USD",
            "expires_at": "2026-11-01T18:00:00Z",
            "document_number": "DO-NOT-EXPOSE-DOCUMENT",
            "phone_e164": "DO-NOT-EXPOSE-PHONE",
            "display_name": "DO-NOT-EXPOSE-NAME",
        }

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/catalogs":
            return {
                "service_types": ["Internet", "Telefonía fuera de página"],
                "document_types": ["CC", "NIT"],
            }
        if path == "/debts":
            return {"items": [], "total": 0, "page": 1, "page_size": 20}
        if path.endswith("attempts"):
            return {
                "status": "applied",
                "received_cents": 8000,
                "forgiven_cents": 2000,
                "payment_reference": "DEMO-0001",
                "document_number": "DO-NOT-EXPOSE-DOCUMENT",
            }
        return self.order


@pytest.fixture
def web():
    settings = SimpleNamespace(
        operator_username="demo",
        operator_password=SecretStr("fictional-password"),
        session_secret=SecretStr("s" * 48),
        public_base_url="http://testserver",
        app_env="test",
        demo_mode=True,
        central_api_url="http://central",
        central_agent_token=SecretStr("agent-only"),
        central_operator_token=SecretStr("operator-only"),
        chatwoot_template_name="recordatorio_factura_demo",
        chatwoot_template_language="es",
    )
    app = FastAPI()
    app.state.settings = settings
    app.state.operator_central = app.state.payment_central = FakeCentral()
    operator.configure_operator(app, settings)
    app.include_router(operator.router)
    app.include_router(payments.router)

    @app.exception_handler(DomainError)
    async def error_handler(request, exc):
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    with TestClient(app) as client:
        yield client, app


def sign_in(client):
    page = client.get("/login")
    token = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post(
        "/login",
        data={"username": "demo", "password": "fictional-password", "csrf": token},
        headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    console = client.get("/central")
    return re.search('name="csrf-token" content="([^"]+)"', console.text)[1]


def test_private_console_login_and_csrf_rotation(web):
    client, app = web
    assert client.get("/central", follow_redirects=False).status_code == 303
    assert client.get("/api/debts").status_code == 401
    page = client.get("/login")
    old_token = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    csrf = sign_in(client)
    assert csrf != old_token
    assert client.get("/api/debts").json()["items"] == []
    assert (
        client.post(
            "/logout", headers={"Origin": "http://evil.invalid", "X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    assert client.post("/logout", headers={"Origin": "http://testserver"}).status_code == 403
    assert (
        client.post(
            "/logout", headers={"Origin": "http://testserver", "X-CSRF-Token": csrf}
        ).status_code
        == 200
    )
    assert client.get("/api/debts").status_code == 401
    assert not any("password" in str(call) for call in app.state.operator_central.calls)


def test_local_cookie_httponly_and_production_secure(web):
    client, _ = web
    cookie = client.get("/login").headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    app = FastAPI()
    settings = SimpleNamespace(
        public_base_url="https://demo.invalid",
        app_env="production",
        session_secret=SecretStr("x" * 48),
    )
    operator.configure_operator(app, settings)
    assert app.user_middleware[0].kwargs["https_only"] is True
    settings.public_base_url = "http://demo.invalid"
    with pytest.raises(ValueError):
        operator.configure_operator(FastAPI(), settings)


def test_login_mutation_requires_original_origin_and_csrf(web):
    client, _ = web
    response = client.post(
        "/login",
        data={"username": "demo", "password": "fictional-password"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 403


def test_exact_mora_bucket_and_service_filters(web):
    client, app = web
    sign_in(client)
    response = client.get(
        "/api/debts?overdue_bucket=1-29&service_type=Internet&document_type=CC&document_number=10000001&debt_status=pendiente"
    )
    assert response.status_code == 200
    params = app.state.operator_central.calls[-1][2]["params"]
    assert params == {
        "dias_mora_min": 1,
        "dias_mora_max": 29,
        "service_type": "Internet",
        "document_type": "CC",
        "document_number": "10000001",
        "debt_status": "pendiente",
    }


def test_customer_edit_is_private_versioned_and_server_owned(web):
    client, app = web
    csrf = sign_in(client)
    body = {
        "phone_e164": "+573000000001",
        "delivery_mode": "simulated",
        "test_contact_enabled": False,
        "expected_contact_version": 2,
    }
    response = client.patch(
        "/api/customers/customer-demo",
        json=body,
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "edit-key",
        },
    )
    assert response.status_code == 200
    method, path, args = app.state.operator_central.calls[-1]
    assert (method, path) == ("PATCH", "/customers/customer-demo")
    assert args["json"] == body and args["idempotency_key"] == "edit-key"


def test_public_payment_never_exposes_customer_identification(web):
    client, app = web
    response = client.get("/p/order-demo?token=fictional-capability")
    assert response.status_code == 200
    assert "80.00" in response.text and "Internet ficticio" in response.text
    assert "DO-NOT-EXPOSE" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert app.state.payment_central.calls[-1][2]["params"] == {
        "capability": "fictional-capability"
    }
    assert client.get("/p/order-demo").status_code == 404


def test_payment_accepts_intent_only_and_forwards_same_idempotency_key(web):
    client, app = web
    payload = {"capability": "fictional-capability", "decision": "approved"}
    headers = {"Origin": "http://testserver", "Idempotency-Key": "stable-attempt"}
    assert (
        client.post(
            "/api/payments/order-demo/attempts", json={**payload, "amount": 1}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/payments/order-demo/attempts",
            json=payload,
            headers={"Origin": "http://testserver"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/payments/order-demo/attempts",
            json=payload,
            headers={**headers, "Origin": "http://evil.invalid"},
        ).status_code
        == 403
    )
    for _ in range(2):
        response = client.post("/api/payments/order-demo/attempts", json=payload, headers=headers)
        assert response.status_code == 200
        assert "document_number" not in response.json()
        assert app.state.payment_central.calls[-1][2] == {
            "json": payload,
            "idempotency_key": "stable-attempt",
        }


def test_receipt_after_paid_is_capture_ready(web):
    client, app = web
    app.state.payment_central.order.update(
        status="pagada",
        payment_reference="DEMO-0001",
        received_cents=8000,
        forgiven_cents=2000,
        applied_at="2026-11-01T18:00:00Z",
    )
    response = client.get("/p/order-demo/receipt?token=fictional-capability")
    assert response.status_code == 200
    assert "DEMO-0001" in response.text and "Comprobante de pago" in response.text
    assert 'id="approve"' not in response.text
    assert "DO-NOT-EXPOSE" not in response.text


def test_campaigns_do_not_fake_success_and_reset_requires_confirmation(web):
    client, _ = web
    csrf = sign_in(client)
    headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf}
    assert client.post("/api/campaigns/preview", json={}, headers=headers).status_code == 503
    assert client.post("/api/demo/reset", json={}, headers=headers).status_code == 422
    assert (
        client.post(
            "/api/demo/reset", json={"confirmation": "REINICIAR DEMO"}, headers=headers
        ).status_code
        == 503
    )


@pytest.mark.asyncio
async def test_central_client_role_grant_and_transport_boundary(web):
    _, app = web
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    central = CentralClient(
        app.state.settings, role="agent", transport=httpx.MockTransport(handler)
    )
    await central.request(
        "GET", "/debts", grant="customer-only", headers={"Authorization": "Bearer browser-injected"}
    )
    assert seen[0].url.path == "/internal/v1/debts"
    assert seen[0].headers["Authorization"] == "Bearer agent-only"
    assert seen[0].headers["X-Customer-Grant"] == "customer-only"
    with pytest.raises(ValueError):
        await central.request("GET", "https://evil.invalid/token")
    failing = CentralClient(
        app.state.settings,
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="secret traceback")),
    )
    with pytest.raises(DomainError) as caught:
        await failing.request("GET", "/debts")
    assert caught.value.status == 503 and "traceback" not in caught.value.message


def test_private_global_catalogs_populate_simple_filters_without_customer_type(web):
    client, app = web
    assert client.get("/api/catalogs").status_code == 401
    sign_in(client)
    page = client.get("/central")
    assert page.status_code == 200
    service = re.search(r'<select name="service_type">(.*?)</select>', page.text)[1]
    documents = re.search(r'<select name="document_type">(.*?)</select>', page.text)[1]
    assert 'value="Internet"' in service and 'value="Telefonía fuera de página"' in service
    assert 'value="CC"' in documents and 'value="NIT"' in documents
    assert "Número de documento" in page.text and 'name="document_number"' in page.text
    assert "Tipo de cliente" not in page.text and 'name="customer_type"' not in page.text
    result = client.get("/api/catalogs?service_type=Internet&page=999")
    assert result.status_code == 200
    assert result.json() == {
        "service_types": ["Internet", "Telefonía fuera de página"],
        "document_types": ["CC", "NIT"],
    }
    assert app.state.operator_central.calls[-1] == ("GET", "/catalogs", {})


def test_campaign_template_uses_configured_defaults_without_meta_knowledge(web):
    client, _ = web
    sign_in(client)
    page = client.get("/central")
    template = re.search(r'<input name="template_name"[^>]*>', page.text)[0]
    language = re.search(r'<input name="template_language"[^>]*>', page.text)[0]
    assert 'value="recordatorio_factura_demo"' in template and "readonly" in template
    assert 'value="es"' in language and "readonly" in language
