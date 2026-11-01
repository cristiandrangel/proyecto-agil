import hmac
import secrets
from datetime import timedelta

from agil_shared.money import parse_usd
from sqlalchemy import select

from central.auth import CentralError, customer_id, role, sign
from central.debts import assert_version, get_debt
from central.models import Agreement, CentralEvent, Debt, PaymentOrder, Settlement, utcnow


def capability(settings, order):
    return sign(settings, f"payment:{order.id}:{order.token_nonce}:{order.expires_at.isoformat()}")


def validate_capability(settings, order, token, action="read"):
    if not token or not hmac.compare_digest(token, capability(settings, order)):
        raise CentralError("not_found", "Order unavailable", 404)
    now = utcnow()
    if (
        action == "read"
        and order.status == "pagada"
        and order.receipt_expires_at
        and order.receipt_expires_at > now
    ):
        return
    if order.expires_at <= now or order.status == "vencida":
        raise CentralError("order_expired", "Payment order expired", 410)


def receipt_view(settlement, debt):
    return {
        "payment_reference": f"DEMO-PAY-{settlement.id}",
        "status": "applied",
        "currency": "USD",
        "received_cents": settlement.received_cents,
        "forgiven_cents": settlement.forgiven_cents,
        "balance_cents": debt.balance_cents,
        "debt_status": debt.debt_status,
        "simulated": True,
        "applied_at": settlement.applied_at.isoformat(),
        "order_id": str(settlement.order_id),
        "debt_id": str(debt.id),
    }


def order_view(settings, order, db=None, include_capability=True):
    result = {
        "id": str(order.id),
        "order_id": str(order.id),
        "debt_id": str(order.debt_id),
        "agreement_id": str(order.agreement_id) if order.agreement_id else None,
        "status": "vencida"
        if order.status == "vigente" and order.expires_at <= utcnow()
        else order.status,
        "base_cents": order.base_cents,
        "payable_cents": order.payable_cents,
        "discount_cents": order.discount_cents,
        "currency": "USD",
        "expires_at": order.expires_at.isoformat(),
    }
    if include_capability:
        result["capability"] = capability(settings, order)
    if db is not None:
        debt = db.get(Debt, order.debt_id)
        result["service_type"] = debt.service_type
        settlement = db.scalar(select(Settlement).where(Settlement.order_id == order.id))
        if settlement:
            receipt = receipt_view(settlement, debt)
            result["receipt"] = receipt
            result.update({k: v for k, v in receipt.items() if k != "status"})
    return result


def make_order(request, db, debt, key, agreement=None):
    order = PaymentOrder(
        customer_id=debt.customer_id,
        debt_id=debt.id,
        agreement_id=agreement.id if agreement else None,
        base_version=debt.version,
        base_cents=debt.balance_cents,
        payable_cents=agreement.offer_cents if agreement else debt.balance_cents,
        discount_cents=agreement.expected_discount_cents if agreement else 0,
        token_nonce=secrets.token_hex(24),
        expires_at=utcnow() + timedelta(seconds=request.app.state.settings.order_ttl_seconds),
        idempotency_key=key,
    )
    if agreement:
        order.expires_at = min(order.expires_at, agreement.expires_at)
    db.add(order)
    db.flush()
    return order


def create_order(request, db, body, key):
    customer_id(request, db)
    debt = get_debt(request, db, body.debt_id, lock=True)
    assert_version(debt, body.expected_version)
    return order_view(request.app.state.settings, make_order(request, db, debt, key), db)


def quote(request, db, body, key):
    customer_id(request, db)
    debt = get_debt(request, db, body.debt_id, lock=True)
    assert_version(debt, body.expected_version)
    try:
        amount = parse_usd(body.offer_amount_usd)
    except (ValueError, TypeError) as exc:
        raise CentralError(
            "invalid_amount", "Use a positive USD amount with at most two decimals", 422
        ) from exc
    if amount <= 0 or amount >= debt.balance_cents:
        raise CentralError(
            "invalid_offer", "Discount offer must be positive and below current balance", 422
        )
    if amount * 100 < debt.balance_cents * 80:
        return {
            "status": "requires_human",
            "requires_human": True,
            "debt_id": str(debt.id),
            "base_cents": debt.balance_cents,
            "offer_cents": amount,
            "currency": "USD",
        }
    agreement = Agreement(
        customer_id=debt.customer_id,
        debt_id=debt.id,
        debt_version=debt.version,
        base_cents=debt.balance_cents,
        offer_cents=amount,
        expected_discount_cents=debt.balance_cents - amount,
        source_message_id=body.source_message_id,
        expires_at=utcnow() + timedelta(seconds=request.app.state.settings.order_ttl_seconds),
    )
    db.add(agreement)
    db.flush()
    db.add(
        CentralEvent(
            event_type="agreement_quoted",
            customer_id=debt.customer_id,
            debt_id=debt.id,
            payload={
                "agreement_id": str(agreement.id),
                "offer_cents": amount,
                "discount_cents": agreement.expected_discount_cents,
                "expires_at": agreement.expires_at.isoformat(),
            },
        )
    )
    return {
        "id": str(agreement.id),
        "agreement_id": str(agreement.id),
        "debt_id": str(debt.id),
        "status": agreement.status,
        "base_cents": agreement.base_cents,
        "offer_cents": amount,
        "discount_cents": agreement.expected_discount_cents,
        "percentage": str(amount * 10000 // agreement.base_cents / 100),
        "currency": "USD",
        "expected_version": debt.version,
        "expires_at": agreement.expires_at.isoformat(),
    }


def accept(request, db, agreement_id, body, key):
    owner = customer_id(request, db)
    agreement = db.get(Agreement, agreement_id)
    if agreement is None or agreement.customer_id != owner:
        raise CentralError("not_found", "Agreement unavailable", 404)
    debt = get_debt(request, db, agreement.debt_id, lock=True)
    agreement = db.scalar(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert_version(debt, body.expected_version)
    if agreement.debt_version != debt.version or agreement.base_cents != debt.balance_cents:
        raise CentralError("version_conflict", "Debt changed; request a new quote", 409)
    if agreement.expires_at <= utcnow() or agreement.status == "vencido":
        raise CentralError("quote_expired", "Agreement quote expired", 410)
    if agreement.source_message_id == body.source_message_id:
        raise CentralError(
            "later_confirmation_required", "Confirm the proposal in a subsequent message", 409
        )
    if agreement.status == "aceptado":
        order = db.scalar(
            select(PaymentOrder).where(
                PaymentOrder.agreement_id == agreement.id, PaymentOrder.status == "vigente"
            )
        )
        if order:
            return order_view(request.app.state.settings, order, db)
    if agreement.status != "propuesto":
        raise CentralError("agreement_state_conflict", "Agreement cannot be accepted", 409)
    agreement.status = "aceptado"
    agreement.accepted_at = utcnow()
    order = make_order(request, db, debt, key, agreement)
    db.add(
        CentralEvent(
            event_type="agreement_accepted",
            customer_id=debt.customer_id,
            debt_id=debt.id,
            order_id=order.id,
            payload={
                "agreement_id": str(agreement.id),
                "offer_cents": agreement.offer_cents,
                "discount_cents": agreement.expected_discount_cents,
                "expires_at": agreement.expires_at.isoformat(),
            },
        )
    )
    return order_view(request.app.state.settings, order, db)


def get_order(request, db, order_id, token=None):
    role(request)
    order = db.get(PaymentOrder, order_id)
    if order is None:
        raise CentralError("not_found", "Order unavailable", 404)
    authorized_grant = bool(request.headers.get("x-customer-grant"))
    if authorized_grant:
        if customer_id(request, db) != order.customer_id:
            raise CentralError("not_found", "Order unavailable", 404)
    elif token:
        validate_capability(request.app.state.settings, order, token)
    else:
        customer_id(request, db)  # Raises the uniform missing/invalid-grant error.
    return order_view(request.app.state.settings, order, db, include_capability=authorized_grant)
