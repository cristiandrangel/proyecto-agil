"""Private operator console and authenticated same-origin JSON endpoints."""

from __future__ import annotations

import hmac
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from agil_shared.errors import DomainError
from backend.integrations.central import CentralClient
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def settings_for(request: Request):
    if hasattr(request.app.state, "settings"):
        return request.app.state.settings
    from backend.config import get_settings

    return get_settings()


def secret(value):
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def configure_operator(app, settings):
    """Call once before startup; HTTP is accepted only in explicitly local environments."""
    parsed = urlsplit(str(settings.public_base_url))
    local = settings.app_env in {"local", "development", "test"} and parsed.scheme == "http"
    if parsed.scheme != "https" and not local:
        raise ValueError("The public operator console requires HTTPS; local HTTP must be explicit")
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret(settings.session_secret),
        session_cookie="agil_operator",
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=not local,
    )


def csrf_token(request):
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def check_origin(request):
    expected = urlsplit(str(settings_for(request).public_base_url))
    origin = urlsplit(request.headers.get("origin", ""))
    if (origin.scheme, origin.netloc) != (expected.scheme, expected.netloc) or origin.path not in {
        "",
        "/",
    }:
        raise DomainError("origin_denied", "Origen no permitido.", status=403)


def check_csrf(request, token):
    check_origin(request)
    stored = request.session.get("csrf", "")
    if not stored or not token or not hmac.compare_digest(stored.encode(), token.encode()):
        raise DomainError(
            "csrf_invalid", "La sesión del formulario venció. Recarga la página.", status=403
        )


async def require_operator(request: Request):
    if request.session.get("operator") is not True:
        raise DomainError("operator_required", "Inicia sesión como operador.", status=401)
    if request.method not in {"GET", "HEAD"}:
        check_csrf(request, request.headers.get("x-csrf-token", ""))


def central_for(request):
    return getattr(request.app.state, "operator_central", None) or CentralClient(
        settings_for(request), role="operator"
    )


async def object_body(request):
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        raise DomainError("invalid_json", "Envía un objeto JSON válido.", status=422) from None
    if not isinstance(body, dict):
        raise DomainError("invalid_json", "Envía un objeto JSON válido.", status=422)
    return body


def idempotency(request):
    key = request.headers.get("idempotency-key", "")
    if not key or len(key) > 200:
        raise DomainError("idempotency_required", "Falta la clave de la operación.", status=422)
    return key


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"csrf": csrf_token(request), "error": None}
    )


@router.post("/login")
async def login(request: Request):
    fields = parse_qs((await request.body()).decode("utf-8", errors="replace"))

    def field(name):
        return fields.get(name, [""])[0]

    check_csrf(request, field("csrf"))
    settings = settings_for(request)
    valid_user = hmac.compare_digest(
        field("username").encode(), str(settings.operator_username).encode()
    )
    valid_password = hmac.compare_digest(
        field("password").encode(), secret(settings.operator_password).encode()
    )
    if not (valid_user and valid_password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"csrf": csrf_token(request), "error": "Usuario o contraseña incorrectos."},
            status_code=401,
        )
    request.session.clear()
    request.session.update(operator=True, csrf=secrets.token_urlsafe(32))
    return RedirectResponse("/central", status_code=303)


@router.post("/logout", dependencies=[Depends(require_operator)])
async def logout(request: Request):
    request.session.clear()
    return {"redirect": "/login"}


@router.get("/")
async def home():
    return RedirectResponse("/central", status_code=303)


@router.get("/central")
async def central_page(request: Request):
    if request.session.get("operator") is not True:
        return RedirectResponse("/login", status_code=303)
    portfolio, load_error = {"items": [], "total": 0}, None
    catalogs = {"service_types": [], "document_types": []}
    try:
        portfolio = await central_for(request).request(
            "GET", "/debts", params={"page": 1, "page_size": 20}
        )
    except DomainError as exc:
        load_error = exc.message
    try:
        catalogs = await central_for(request).request("GET", "/catalogs")
    except DomainError:
        load_error = (
            load_error or "No se pudieron cargar las opciones de filtros. Recarga la página."
        )
    return templates.TemplateResponse(
        request=request,
        name="central.html",
        context={
            "csrf": csrf_token(request),
            "demo_mode": settings_for(request).demo_mode,
            "portfolio": portfolio,
            "catalogs": catalogs,
            "campaign_template": {
                "name": getattr(settings_for(request), "chatwoot_template_name", ""),
                "language": getattr(settings_for(request), "chatwoot_template_language", "")
                or "es",
            },
            "load_error": load_error,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/catalogs", dependencies=[Depends(require_operator)])
async def catalogs(request: Request):
    return await central_for(request).request("GET", "/catalogs")


@router.get("/api/debts", dependencies=[Depends(require_operator)])
async def debts(request: Request):
    params = dict(request.query_params)
    bucket = params.pop("overdue_bucket", "")
    bounds = {
        "0": (0, 0),
        "1-29": (1, 29),
        "30-59": (30, 59),
        "60-89": (60, 89),
        "90-119": (90, 119),
        "120+": (120, None),
    }
    if bucket:
        if bucket not in bounds:
            raise DomainError("invalid_bucket", "Rango de mora inválido.", status=422)
        lower, upper = bounds[bucket]
        params["dias_mora_min"] = lower
        if upper is not None:
            params["dias_mora_max"] = upper
    return await central_for(request).request("GET", "/debts", params=params)


@router.patch("/api/customers/{customer_id}", dependencies=[Depends(require_operator)])
async def update_customer(customer_id: str, request: Request):
    result = await central_for(request).request(
        "PATCH",
        f"/customers/{customer_id}",
        json=await object_body(request),
        idempotency_key=request.headers.get("idempotency-key") or str(uuid4()),
    )
    identity = getattr(request.app.state, "identity_service", None)
    if identity is not None and hasattr(identity, "contact_changed"):
        await identity.contact_changed(customer_id)
    return result


@router.patch("/api/debts/{debt_id}", dependencies=[Depends(require_operator)])
async def update_debt(debt_id: str, request: Request):
    return await central_for(request).request(
        "PATCH",
        f"/debts/{debt_id}",
        json=await object_body(request),
        idempotency_key=request.headers.get("idempotency-key") or str(uuid4()),
    )


def campaign_service(request):
    service = getattr(request.app.state, "campaign_service", None)
    if service is None:
        raise DomainError(
            "campaigns_unavailable",
            "El servicio de campañas no está disponible.",
            status=503,
            retryable=True,
        )
    return service


@router.post("/api/campaigns/preview", dependencies=[Depends(require_operator)])
async def preview_campaign(request: Request):
    return await campaign_service(request).preview(await object_body(request))


@router.post("/api/campaigns", dependencies=[Depends(require_operator)])
async def create_campaign(request: Request):
    payload = await object_body(request)
    settings = settings_for(request)
    fixed = {
        "template_name": settings.chatwoot_template_name,
        "template_language": settings.chatwoot_template_language,
    }
    if not all(fixed.values()):
        raise DomainError(
            "template_not_configured", "La plantilla de la demo no está configurada.", status=503
        )
    if any(key in payload and payload[key] != value for key, value in fixed.items()):
        raise DomainError(
            "template_fixed", "La demo utiliza únicamente su plantilla preaprobada.", status=422
        )
    payload.update(fixed)
    return await campaign_service(request).create(payload)


@router.post("/api/campaigns/{campaign_id}/launch", dependencies=[Depends(require_operator)])
async def launch_campaign(campaign_id: str, request: Request):
    return await campaign_service(request).launch(campaign_id, idempotency(request))


@router.post("/api/campaigns/{campaign_id}/close", dependencies=[Depends(require_operator)])
async def close_campaign(campaign_id: str, request: Request):
    return await campaign_service(request).close(campaign_id)


@router.get("/api/campaigns/{campaign_id}", dependencies=[Depends(require_operator)])
async def get_campaign(campaign_id: str, request: Request):
    return await campaign_service(request).get(campaign_id)


@router.get("/api/campaigns/{campaign_id}/metrics", dependencies=[Depends(require_operator)])
async def campaign_metrics(campaign_id: str, request: Request):
    return await campaign_service(request).metrics(campaign_id)


@router.post("/api/demo/reset", dependencies=[Depends(require_operator)])
async def reset_demo(request: Request):
    if not settings_for(request).demo_mode:
        raise DomainError(
            "demo_disabled", "El reinicio solo está disponible en modo demo.", status=403
        )
    payload = await object_body(request)
    if payload.get("confirmation") != "REINICIAR DEMO":
        raise DomainError(
            "confirmation_required", "Escribe REINICIAR DEMO para confirmar.", status=422
        )
    service = getattr(request.app.state, "demo_service", None)
    if service is None:
        raise DomainError(
            "reset_unavailable", "El reinicio coordinado no está disponible.", status=503
        )
    return await service.reset(
        {"confirmation": "RESET_DEMO", "operation_key": idempotency(request)}
    )
