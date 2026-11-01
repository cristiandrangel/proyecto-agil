from sqlalchemy import select

from central.auth import CentralError, customer_id, operator, role
from central.models import Agreement, CentralEvent, Customer, Debt, PaymentOrder


def customer_view(person):
    return {
        field: (str(getattr(person, field)) if field == "id" else getattr(person, field))
        for field in (
            "id",
            "document_type",
            "document_number",
            "display_name",
            "phone_e164",
            "email",
            "customer_type",
            "delivery_mode",
            "test_contact_enabled",
            "contact_version",
        )
    }


def debt_view(debt, person=None):
    fields = (
        "id",
        "customer_id",
        "contract_reference",
        "service_type",
        "original_cents",
        "balance_cents",
        "due_date",
        "dias_mora",
        "debt_status",
        "service_status",
        "version",
    )
    result = {field: getattr(debt, field) for field in fields}
    for field in ("id", "customer_id", "due_date"):
        result[field] = str(result[field])
    result["currency"] = "USD"
    if person:
        result["customer"] = customer_view(person)
        result.update({key: value for key, value in result["customer"].items() if key != "id"})
    return result


def get_debt(request, db, debt_id, lock=False):
    query = select(Debt).where(Debt.id == debt_id)
    actor = role(request)
    if actor == "agent":
        query = query.where(Debt.customer_id == customer_id(request, db))
    if lock:
        query = query.with_for_update()
    debt = db.scalar(query)
    if debt is None:
        raise CentralError("not_found", "Debt unavailable", 404)
    return debt


def assert_version(debt, version):
    if debt.version != version:
        raise CentralError("version_conflict", "Debt changed; refresh before continuing", 409)
    if debt.debt_status != "pendiente" or debt.balance_cents <= 0:
        raise CentralError("debt_settled", "Debt is already settled", 409)


def edit_customer(request, db, ident, body):
    operator(request)
    person = db.scalar(select(Customer).where(Customer.id == ident).with_for_update())
    if person is None:
        raise CentralError("not_found", "Customer unavailable", 404)
    if person.contact_version != body.expected_contact_version:
        raise CentralError("version_conflict", "Contact changed; refresh before continuing", 409)
    updates = body.model_dump(exclude_unset=True, exclude={"expected_contact_version"})
    for key, value in updates.items():
        if value is None and key != "email":
            raise CentralError("invalid_field", "Field cannot be null", 422)
        setattr(person, key, value)
    person.contact_version += 1
    db.add(
        CentralEvent(
            event_type="contact_changed",
            customer_id=person.id,
            payload={"contact_version": person.contact_version},
        )
    )
    return customer_view(person)


def edit_debt(request, db, ident, body):
    operator(request)
    if not request.app.state.settings.demo_mode:
        raise CentralError("demo_disabled", "Fixture editing is disabled", 403)
    debt = get_debt(request, db, ident, lock=True)
    if debt.version != body.expected_version:
        raise CentralError("version_conflict", "Debt changed; refresh before continuing", 409)
    updates = body.model_dump(exclude_unset=True, exclude={"expected_version"})
    if any(value is None for value in updates.values()):
        raise CentralError("invalid_field", "Field cannot be null", 422)
    if debt.debt_status == "liquidada" and updates.get("balance_cents", 0) > 0:
        raise CentralError("reset_required", "Use coordinated reset to restore settled debt", 409)
    old = debt.balance_cents
    for key, value in updates.items():
        setattr(debt, key, value)
    debt.debt_status = "pendiente" if debt.balance_cents else "liquidada"
    debt.version += 1
    for order in db.scalars(
        select(PaymentOrder)
        .where(PaymentOrder.debt_id == debt.id, PaymentOrder.status == "vigente")
        .with_for_update()
    ):
        order.status = "vencida"
    for agreement in db.scalars(
        select(Agreement).where(
            Agreement.debt_id == debt.id, Agreement.status.in_(["propuesto", "aceptado"])
        )
    ):
        agreement.status = "vencido"
    db.add(
        CentralEvent(
            event_type="debt_adjusted",
            customer_id=debt.customer_id,
            debt_id=debt.id,
            payload={
                "previous_balance_cents": old,
                "balance_cents": debt.balance_cents,
                "version": debt.version,
                "adjustment": True,
            },
        )
    )
    return debt_view(debt)
