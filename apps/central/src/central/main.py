"""Internal HTTP boundary: the only writer of the financial database."""

import hashlib
import json
import uuid
from collections.abc import Callable

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from central import debts, identity, orders, payments
from central.auth import CentralError, customer_id, operator, role
from central.config import Settings, get_settings
from central.db import session_factory
from central.models import (
    Base,
    CentralEvent,
    CommandResult,
    Customer,
    Debt,
    PaymentOrder,
)
from central.schemas import (
    AcceptRequest,
    AttemptRequest,
    CustomerPatch,
    DebtPatch,
    LocateRequest,
    OrderRequest,
    QuoteRequest,
    ResetRequest,
    RevokeRequest,
    VerifyRequest,
)
from central.seed import seed


def database(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def clean_result(result):
    if isinstance(result, dict):
        return {
            key: clean_result(value)
            for key, value in result.items()
            if key not in {"capability", "grant_token", "pin", "pin_hash"}
        }
    if isinstance(result, list):
        return [clean_result(value) for value in result]
    return result


def command(request: Request, db: Session, body, key: str | None, action: Callable, scope):
    if not key or len(key) > 200:
        raise CentralError(
            "idempotency_key_required",
            "A nonempty Idempotency-Key of at most 200 characters is required",
            422,
        )
    payload = body.model_dump(mode="json") if hasattr(body, "model_dump") else body
    encoded = json.dumps(
        {"path": request.url.path, "method": request.method, "scope": str(scope), "body": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    # Serialize identical keys before the uniqueness check; a retry waits for commit.
    lock = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    prior = db.get(CommandResult, key)
    if prior:
        if prior.request_digest != digest:
            raise CentralError(
                "idempotency_conflict", "Idempotency key was used for a different command", 409
            )
        result = dict(prior.result_reference)
        if result.get("order_id") and "payable_cents" in result:
            order = db.get(PaymentOrder, uuid.UUID(result["order_id"]))
            if order:
                result["capability"] = orders.capability(request.app.state.settings, order)
        return result
    result = action()
    db.add(
        CommandResult(
            idempotency_key=key,
            command_type=request.url.path,
            request_digest=digest,
            result_reference=clean_result(result),
        )
    )
    # Commit before an HTTP success can expose any financial receipt.
    db.commit()
    return result


def create_app(settings: Settings | None = None):
    app = FastAPI(title="Proyecto Ágil — Central", version="0.1.0")
    app.state.settings = settings or get_settings()
    app.state.engine, app.state.session_factory = session_factory(app.state.settings)

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        try:
            correlation_id = str(uuid.UUID(request.headers.get("x-correlation-id", "")))
        except ValueError:
            correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(request, code, message, status, retryable=False):
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "retryable": retryable,
                "correlation_id": getattr(request.state, "correlation_id", str(uuid.uuid4())),
            },
        )

    @app.exception_handler(CentralError)
    async def domain_error(request, exc):
        return error_response(request, exc.code, exc.message, exc.status, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic's default errors echo rejected inputs, including a submitted PIN.
        return error_response(request, "invalid_request", "Invalid request parameters", 422)

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return error_response(
            request, "state_conflict", "Concurrent state change; refresh before retrying", 409
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return error_response(
            request, "dependency_unavailable", "Central database unavailable", 503, True
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "central"}

    @app.get("/ready")
    def ready(request: Request, db: Session = Depends(database)):
        settings = request.app.state.settings
        if not all(
            secret.get_secret_value()
            for secret in (
                settings.central_operator_token,
                settings.central_agent_token,
                settings.payment_signing_key,
            )
        ):
            raise CentralError(
                "configuration_unavailable", "Central credentials are not configured", 503
            )
        db.execute(select(Debt.id).limit(1))
        return {"status": "ready", "service": "central"}

    prefix = "/internal/v1"

    @app.post(prefix + "/identity/locate")
    def locate(request: Request, body: LocateRequest, db: Session = Depends(database)):
        return identity.locate(request, db, body)

    @app.post(prefix + "/identity/verify")
    def verify(request: Request, body: VerifyRequest, db: Session = Depends(database)):
        return identity.verify(request, db, body)

    @app.post(prefix + "/identity/revoke")
    def revoke(
        request: Request,
        body: RevokeRequest,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        if role(request) != "agent":
            raise CentralError("forbidden", "Agent permission required", 403)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: identity.revoke(request, db, body),
            body.binding_ref,
        )

    @app.get(prefix + "/catalogs")
    def catalogs(request: Request, db: Session = Depends(database)):
        operator(request)
        return {
            "service_types": list(db.scalars(select(Debt.service_type).distinct().order_by(Debt.service_type))),
            "document_types": list(db.scalars(select(Customer.document_type).distinct().order_by(Customer.document_type))),
        }

    @app.get(prefix + "/debts")
    def list_debts(
        request: Request,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        dias_mora_min: int | None = Query(None, ge=0),
        dias_mora_max: int | None = Query(None, ge=0),
        mora_min: int | None = Query(None, ge=0),
        mora_max: int | None = Query(None, ge=0),
        service_type: str | None = None,
        customer_type: str | None = None,
        document_number: str | None = None,
        document_type: str | None = None,
        debt_status: str | None = None,
        overdue_bucket: str | None = None,
        db: Session = Depends(database),
    ):
        actor = role(request)
        query = select(Debt, Customer).join(Customer, Debt.customer_id == Customer.id)
        if actor == "agent":
            query = query.where(Debt.customer_id == customer_id(request, db))
        lower = dias_mora_min if dias_mora_min is not None else mora_min
        upper = dias_mora_max if dias_mora_max is not None else mora_max
        if overdue_bucket:
            buckets = {
                "0-29": (0, 29),
                "30-59": (30, 59),
                "60-89": (60, 89),
                "90-119": (90, 119),
                "120+": (120, None),
            }
            if overdue_bucket not in buckets:
                raise CentralError("invalid_filter", "Unknown overdue bucket", 422)
            lower, upper = buckets[overdue_bucket]
        if lower is not None:
            query = query.where(Debt.dias_mora >= lower)
        if upper is not None:
            query = query.where(Debt.dias_mora <= upper)
        if lower is not None and upper is not None and lower > upper:
            raise CentralError("invalid_filter", "Minimum overdue days exceeds maximum", 422)
        for column, value in [
            (Debt.service_type, service_type),
            (Customer.customer_type, customer_type),
            (Customer.document_number, document_number),
            (Customer.document_type, document_type),
            (Debt.debt_status, debt_status),
        ]:
            if value is not None:
                query = query.where(column == value)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.execute(
            query.order_by(Customer.display_name, Debt.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        agreements = debts.active_agreements(db, [debt.id for debt, _ in rows])
        return {
            "items": [
                debts.debt_view(debt, person if actor == "operator" else None,
                                agreements.get(debt.id))
                for debt, person in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @app.get(prefix + "/debts/{debt_id}")
    def detail_debt(request: Request, debt_id: uuid.UUID, db: Session = Depends(database)):
        debt = debts.get_debt(request, db, debt_id)
        person = db.get(Customer, debt.customer_id) if role(request) == "operator" else None
        return debts.debt_view(debt, person, debts.active_agreements(db, [debt.id]).get(debt.id))

    @app.patch(prefix + "/customers/{ident}")
    def edit_customer(
        request: Request,
        ident: uuid.UUID,
        body: CustomerPatch,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        operator(request)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: debts.edit_customer(request, db, ident, body),
            "operator",
        )

    @app.patch(prefix + "/debts/{ident}")
    def edit_debt(
        request: Request,
        ident: uuid.UUID,
        body: DebtPatch,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        operator(request)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: debts.edit_debt(request, db, ident, body),
            "operator",
        )

    @app.post(prefix + "/orders")
    def create_order(
        request: Request,
        body: OrderRequest,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        scope = customer_id(request, db)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: orders.create_order(request, db, body, idempotency_key),
            scope,
        )

    @app.get(prefix + "/orders/{order_id}")
    def get_order(
        request: Request,
        order_id: uuid.UUID,
        capability: str | None = Query(None),
        db: Session = Depends(database),
    ):
        return orders.get_order(request, db, order_id, capability)

    @app.post(prefix + "/orders/{order_id}/attempts")
    def create_attempt(
        request: Request,
        order_id: uuid.UUID,
        body: AttemptRequest,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        role(request)
        # Validate capability even when retrieving an idempotent command result.
        orders.get_order(request, db, order_id, body.capability)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: payments.attempt(request, db, order_id, body, idempotency_key),
            order_id,
        )

    @app.post(prefix + "/agreements/quote")
    def quote(
        request: Request,
        body: QuoteRequest,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        scope = customer_id(request, db)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: orders.quote(request, db, body, idempotency_key),
            scope,
        )

    @app.post(prefix + "/agreements/{agreement_id}/accept")
    def accept(
        request: Request,
        agreement_id: uuid.UUID,
        body: AcceptRequest,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        scope = customer_id(request, db)
        return command(
            request,
            db,
            body,
            idempotency_key,
            lambda: orders.accept(request, db, agreement_id, body, idempotency_key),
            scope,
        )

    @app.get(prefix + "/payments/verify")
    def verify_payment(
        request: Request,
        debt_id: uuid.UUID,
        payment_reference: str | None = None,
        db: Session = Depends(database),
    ):
        return payments.verify_payment(request, db, debt_id, payment_reference)

    @app.get(prefix + "/events")
    def events(
        request: Request,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(database),
    ):
        operator(request)
        rows = list(
            db.scalars(
                select(CentralEvent)
                .where(CentralEvent.sequence > after)
                .order_by(CentralEvent.sequence)
                .limit(limit)
            )
        )
        items = [
            {
                "id": str(event.id),
                "sequence": event.sequence,
                "event_type": event.event_type,
                "customer_id": str(event.customer_id) if event.customer_id else None,
                "debt_id": str(event.debt_id) if event.debt_id else None,
                "order_id": str(event.order_id) if event.order_id else None,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
            for event in rows
        ]
        return {"items": items, "next_cursor": rows[-1].sequence if rows else after}

    @app.post(prefix + "/demo/seed")
    def demo_seed(
        request: Request,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        operator(request)
        if not request.app.state.settings.demo_mode:
            raise CentralError("demo_disabled", "Demo mode disabled", 403)
        return command(
            request,
            db,
            {},
            idempotency_key,
            lambda: seed(db, request.app.state.settings.demo_pin.get_secret_value()),
            "operator",
        )

    @app.post(prefix + "/demo/reset")
    def demo_reset(
        request: Request,
        body: ResetRequest,
        idempotency_key: str | None = Header(None),
        db: Session = Depends(database),
    ):
        operator(request)
        if not request.app.state.settings.demo_mode:
            raise CentralError("demo_disabled", "Demo mode disabled", 403)

        def reset():
            # Backend confirms its durable maintenance/reset before central restores fixtures.
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(delete(table))
            result = seed(db, request.app.state.settings.demo_pin.get_secret_value())
            event = CentralEvent(event_type="demo_reset", payload={"epoch": str(body.epoch)})
            db.add(event)
            db.flush()
            return {**result, "epoch": str(body.epoch), "event_cutoff": event.sequence}

        return command(request, db, body, idempotency_key, reset, "operator")

    return app


app = create_app()
