import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from agil_shared.errors import DomainError as CentralError
from fastapi import Request
from sqlalchemy import select

from central.models import IdentitySession


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def pin_hash(pin: str):
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2_sha256$200000${salt}${hashed}"


def check_pin(pin, encoded):
    _, iterations, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(actual, expected)


def secret(settings):
    value = settings.payment_signing_key.get_secret_value()
    if not value:
        raise CentralError("configuration_unavailable", "Signing service unavailable", 503)
    return value.encode()


def sign(settings, value):
    return hmac.new(secret(settings), value.encode(), hashlib.sha256).hexdigest()


def grant_token(settings, session):
    return f"{session.id}.{sign(settings, f'grant:{session.id}:{session.binding_ref}:{session.expires_at.isoformat()}')}"


def role(request: Request):
    header = request.headers.get("authorization", "")
    given = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    settings = request.app.state.settings
    for name, expected in [
        ("operator", settings.central_operator_token),
        ("agent", settings.central_agent_token),
    ]:
        value = expected.get_secret_value()
        if value and given and hmac.compare_digest(given, value):
            return name
    raise CentralError("unauthorized", "Service authentication required", 401)


def operator(request):
    if role(request) != "operator":
        raise CentralError("forbidden", "Operator permission required", 403)


def customer_id(request, db):
    if role(request) != "agent":
        raise CentralError("forbidden", "Customer grant required", 403)
    token = request.headers.get("x-customer-grant", "")
    session = (
        db.scalar(select(IdentitySession).where(IdentitySession.token_hash == digest(token)))
        if token
        else None
    )
    if session is None:
        raise CentralError("invalid_grant", "Customer grant required", 401)
    if session.expires_at <= datetime.now(timezone.utc):
        raise CentralError("grant_expired", "Customer authorization expired", 410)
    return session.customer_id
