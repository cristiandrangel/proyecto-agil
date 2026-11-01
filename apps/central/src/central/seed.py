"""Public fictitious fixtures; never overwrite contacts on startup."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select

from central.auth import pin_hash
from central.models import Customer, Debt


def fixture_id(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://demo.invalid/proyecto-agil/{name}")


def seed(db, pin="2468"):
    # All core data must be empty: a partial/restored database is not a seed target.
    from central.models import Base

    if any(
        db.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables
    ):
        return {"seeded": False, "reason": "database_not_empty"}
    customers = [
        ("ana", "Ana Martínez López", "+15550001001", "10000001"),
        ("bruno", "Bruno Torres Gómez", "+15550001002", "10000002"),
        ("pagado", "Carla Rojas Díaz", "+15550001003", "10000003"),
        ("cambiado", "Diego Castro Ruiz", "+15550001004", "10000004"),
    ]
    for key, name, phone, document in customers:
        db.add(
            Customer(
                id=fixture_id(key),
                document_type="CC",
                document_number=document,
                display_name=name,
                phone_e164=phone,
                email=f"{key}@example.test",
                pin_hash=pin_hash(pin),
            )
        )
    mora_people = (
        (0, "Mariana Vargas Ruiz"),
        (29, "Pablo Herrera León"),
        (30, "Lucía Mendoza Ríos"),
        (59, "Santiago Ramírez Soto"),
        (60, "Valentina Suárez Gil"),
        (89, "Andrés Morales Vega"),
        (90, "Camila Ortiz Peña"),
        (119, "Daniel Navarro Cruz"),
        (120, "Sofía Medina Lara"),
    )
    for days, name in mora_people:
        key = f"mora-{days}"
        db.add(
            Customer(
                id=fixture_id(key),
                document_type="CC",
                document_number=str(20000000 + days),
                display_name=name,
                phone_e164=f"+15550002{days:03}",
                email=f"{key}@example.test",
                pin_hash=pin_hash(pin),
            )
        )
    db.flush()
    fixtures = [
        ("ana-hogar", "ana", "hogar", 10000, 45, 1),
        ("ana-telefonia", "ana", "telefonia", 6000, 75, 1),
        ("bruno-hogar", "bruno", "hogar", 20000, 35, 1),
        ("pagado-hogar", "pagado", "hogar", 0, 0, 2),
        ("cambiado-hogar", "cambiado", "hogar", 8500, 65, 2),
    ]
    fixtures += [
        (f"mora-{d}", f"mora-{d}", "television", 10000, d, 1)
        for d in (0, 29, 30, 59, 60, 89, 90, 119, 120)
    ]
    for key, owner, service, balance, days, version in fixtures:
        db.add(
            Debt(
                id=fixture_id(key),
                customer_id=fixture_id(owner),
                contract_reference=f"DEMO-{key.upper()}",
                service_type=service,
                original_cents=10000 if owner in ("pagado", "cambiado") else balance,
                balance_cents=balance,
                due_date=date.today() - timedelta(days=days),
                dias_mora=days,
                debt_status="pendiente" if balance else "liquidada",
                version=version,
            )
        )
    db.flush()
    return {"seeded": True, "customers": len(customers) + 9, "debts": len(fixtures)}
