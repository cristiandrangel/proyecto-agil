import uuid
from datetime import timedelta

from sqlalchemy import select

from central.auth import CentralError, customer_id, role
from central.models import (
    Agreement,
    CentralEvent,
    Debt,
    PaymentAttempt,
    PaymentOrder,
    Settlement,
    utcnow,
)
from central.orders import receipt_view, validate_capability


def attempt(request, db, order_id, body, key):
    role(request)
    initial = db.get(PaymentOrder, order_id)
    if initial is None:
        raise CentralError("not_found", "Order unavailable", 404)
    # Every financial path locks debt before order, including fixture edits.
    debt = db.scalar(select(Debt).where(Debt.id == initial.debt_id).with_for_update())
    order = db.scalar(
        select(PaymentOrder)
        .where(PaymentOrder.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    validate_capability(request.app.state.settings, order, body.capability, action="attempt")
    if order.status == "pagada":
        existing = db.scalar(select(Settlement).where(Settlement.order_id == order.id))
        if existing:
            return receipt_view(existing, debt)
    if debt.debt_status != "pendiente" or order.status != "vigente":
        raise CentralError("payment_state_conflict", "Debt or order no longer payable", 409)
    if order.base_version != debt.version or order.base_cents != debt.balance_cents:
        raise CentralError("version_conflict", "Balance changed; request a new order", 409)
    if order.customer_id != debt.customer_id:
        raise CentralError("not_found", "Order unavailable", 404)
    agreement = None
    if order.agreement_id:
        agreement = db.scalar(
            select(Agreement).where(Agreement.id == order.agreement_id).with_for_update()
        )
        if (
            agreement is None
            or agreement.status != "aceptado"
            or agreement.expires_at <= utcnow()
            or agreement.debt_version != debt.version
            or agreement.customer_id != debt.customer_id
            or agreement.offer_cents != order.payable_cents
        ):
            raise CentralError(
                "agreement_state_conflict", "Discount authorization no longer valid", 409
            )
    elif order.discount_cents != 0:
        raise CentralError("invalid_discount", "Discount requires an accepted agreement", 409)
    payment_attempt = PaymentAttempt(
        order_id=order.id,
        decision=body.decision,
        applied=body.decision == "approved",
        idempotency_key=key,
    )
    db.add(payment_attempt)
    db.flush()
    if body.decision == "rejected":
        return {
            "status": "rejected",
            "order_id": str(order.id),
            "attempt_id": str(payment_attempt.id),
            "balance_cents": debt.balance_cents,
            "currency": "USD",
            "simulated": True,
        }
    settlement = Settlement(
        debt_id=debt.id,
        order_id=order.id,
        attempt_id=payment_attempt.id,
        received_cents=order.payable_cents,
        forgiven_cents=order.discount_cents,
    )
    db.add(settlement)
    debt.balance_cents = 0
    debt.debt_status = "liquidada"
    debt.version += 1
    order.status = "pagada"
    order.receipt_expires_at = utcnow() + timedelta(
        seconds=request.app.state.settings.receipt_ttl_seconds
    )
    if agreement:
        agreement.status = "cumplido"
    # Invalidate other proposals/orders; all reference the now-obsolete base balance.
    for other in db.scalars(
        select(PaymentOrder)
        .where(
            PaymentOrder.debt_id == debt.id,
            PaymentOrder.id != order.id,
            PaymentOrder.status == "vigente",
        )
        .with_for_update()
    ):
        other.status = "vencida"
    for other in db.scalars(
        select(Agreement).where(
            Agreement.debt_id == debt.id, Agreement.status.in_(["propuesto", "aceptado"])
        )
    ):
        if agreement is None or other.id != agreement.id:
            other.status = "vencido"
    db.flush()
    result = receipt_view(settlement, debt)
    db.add(
        CentralEvent(
            event_type="payment_applied",
            customer_id=debt.customer_id,
            debt_id=debt.id,
            order_id=order.id,
            payload={**result, "agreement_id": str(agreement.id) if agreement else None},
        )
    )
    return result


def verify_payment(request, db, debt_id, payment_reference=None):
    owner = customer_id(request, db)
    debt = db.scalar(select(Debt).where(Debt.id == debt_id, Debt.customer_id == owner))
    if debt is None:
        raise CentralError("not_found", "Debt unavailable", 404)
    query = select(Settlement).where(Settlement.debt_id == debt.id)
    if payment_reference:
        try:
            ident = uuid.UUID(payment_reference.removeprefix("DEMO-PAY-"))
        except ValueError:
            return {"status": "absent", "debt_id": str(debt.id), "currency": "USD"}
        query = query.where(Settlement.id == ident)
    settlement = db.scalar(query)
    if settlement:
        return receipt_view(settlement, debt)
    pending = db.scalar(
        select(PaymentOrder.id)
        .where(
            PaymentOrder.debt_id == debt.id,
            PaymentOrder.status == "vigente",
            PaymentOrder.expires_at > utcnow(),
        )
        .limit(1)
    )
    return {
        "status": "pending" if pending and not payment_reference else "absent",
        "debt_id": str(debt.id),
        "balance_cents": debt.balance_cents,
        "debt_status": debt.debt_status,
        "currency": "USD",
    }
