"""Capability-scoped public simulated checkout; amounts always come from central."""

from __future__ import annotations

from agil_shared.errors import DomainError
from backend.api.operator import check_origin, idempotency, object_body, settings_for, templates
from backend.integrations.central import CentralClient
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()
SAFE_ORDER_FIELDS = {
    "id",
    "order_id",
    "status",
    "service",
    "service_name",
    "service_type",
    "currency",
    "base_cents",
    "payable_cents",
    "discount_cents",
    "expires_at",
    "payment_reference",
    "received_cents",
    "forgiven_cents",
    "applied_at",
    "created_at",
    "paid_at",
    "simulated",
    "balance_cents",
    "debt_status",
}


def central_for(request):
    return getattr(request.app.state, "payment_central", None) or CentralClient(
        settings_for(request), role="agent"
    )


def capability(token):
    if not isinstance(token, str) or not token or len(token) > 4096:
        raise DomainError("invalid_capability", "El enlace de pago no es válido.", status=404)
    return token


def safe_order(data):
    # Explicit allowlist keeps customer identification/contact out of public pages.
    public = {key: value for key, value in data.items() if key in SAFE_ORDER_FIELDS}
    payment = data.get("payment")
    if isinstance(payment, dict):
        public.update({key: value for key, value in payment.items() if key in SAFE_ORDER_FIELDS})
    return public


async def render_payment(request, order_id, token, receipt=False):
    try:
        token = capability(token)
        order = safe_order(
            await central_for(request).request(
                "GET", f"/orders/{order_id}", params={"capability": token}
            )
        )
    except DomainError as exc:
        return templates.TemplateResponse(
            request=request,
            name="payment_error.html",
            context={"message": exc.message, "retryable": exc.retryable},
            status_code=exc.status,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )
    return templates.TemplateResponse(
        request=request,
        name="payment.html",
        context={"order": order, "order_id": order_id, "token": token, "receipt": receipt},
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@router.get("/p/{order_id}")
async def payment_page(order_id: str, request: Request, token: str = ""):
    return await render_payment(request, order_id, token)


@router.get("/p/{order_id}/receipt")
async def payment_receipt(order_id: str, request: Request, token: str = ""):
    return await render_payment(request, order_id, token, receipt=True)


@router.post("/api/payments/{order_id}/attempts")
async def payment_attempt(order_id: str, request: Request):
    check_origin(request)
    body = await object_body(request)
    if set(body) - {"capability", "decision"}:
        raise DomainError(
            "invalid_payment_fields",
            "Solo se admite el token del enlace y la decisión de simulación.",
            status=422,
        )
    token = capability(body.get("capability"))
    if body.get("decision") not in {"approved", "rejected"}:
        raise DomainError("invalid_decision", "Selecciona aprobar o rechazar.", status=422)
    result = await central_for(request).request(
        "POST",
        f"/orders/{order_id}/attempts",
        json={"capability": token, "decision": body["decision"]},
        idempotency_key=idempotency(request),
    )
    return JSONResponse(
        safe_order(result), headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )
