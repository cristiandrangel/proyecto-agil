from datetime import timedelta

from sqlalchemy import select

from central.auth import CentralError, check_pin, digest, grant_token, role
from central.models import Customer, IdentityAttempt, IdentityCandidate, IdentitySession, utcnow


def masked_identity_hint(name, document_type, document_number):
    def edges(value):
        if len(value) < 3:
            return "*" * max(1, len(value))
        return value[0] + "*" * (len(value) - 2) + value[-1]

    first_name = name.split(maxsplit=1)[0] if name.split() else ""
    return f"{edges(first_name)} · {document_type} {edges(document_number)}"


def locate(request, db, body):
    if role(request) != "agent":
        raise CentralError("forbidden", "Agent permission required", 403)
    query = select(Customer)
    if body.phone_e164:
        query = query.where(Customer.phone_e164 == body.phone_e164)
    else:
        query = query.where(
            Customer.document_type == body.document_type,
            Customer.document_number == body.document_number,
        )
    candidates = []
    for person in db.scalars(query.limit(20)):
        candidate = IdentityCandidate(
            customer_id=person.id, expires_at=utcnow() + timedelta(minutes=15)
        )
        db.add(candidate)
        db.flush()
        hint = masked_identity_hint(person.display_name, person.document_type, person.document_number)
        candidates.append({"candidate_reference": str(candidate.id), "masked_hint": hint})
    result = {"candidate_count": len(candidates), "candidates": candidates}
    if len(candidates) == 1:
        result.update(candidates[0])
    return result


def verify(request, db, body):
    if role(request) != "agent":
        raise CentralError("forbidden", "Agent permission required", 403)
    if not body.confirmed:
        raise CentralError("candidate_unconfirmed", "Confirm the candidate first", 409)
    candidate = db.get(IdentityCandidate, body.candidate_reference)
    if candidate is None or candidate.expires_at <= utcnow():
        raise CentralError("candidate_unavailable", "Candidate unavailable; locate again", 404)
    # Customer lock serializes every binding and makes rotating binding UUIDs unable to bypass limits.
    person = db.scalar(
        select(Customer).where(Customer.id == candidate.customer_id).with_for_update()
    )
    settings = request.app.state.settings
    sessions = list(
        db.scalars(
            select(IdentitySession)
            .where(IdentitySession.customer_id == person.id)
            .with_for_update()
        )
    )
    now = utcnow()
    if any(s.locked_until and s.locked_until > now for s in sessions):
        raise CentralError("identity_locked", "Identity temporarily locked", 423)
    session = next((s for s in sessions if s.binding_ref == body.binding_ref), None)
    if session is None:
        session = IdentitySession(customer_id=person.id, binding_ref=body.binding_ref)
        db.add(session)
        db.flush()
    prior = db.scalar(
        select(IdentityAttempt).where(
            IdentityAttempt.session_id == session.id,
            IdentityAttempt.source_message_id == body.source_message_id,
        )
    )
    if prior:
        if not prior.success or not check_pin(body.pin, person.pin_hash):
            raise CentralError("invalid_pin", "PIN verification failed", 401)
        if session.expires_at is None or session.expires_at <= now or session.token_hash is None:
            raise CentralError("grant_expired", "Customer authorization expired", 410)
        token = grant_token(settings, session)
        return {
            "customer_id": str(person.id),
            "display_name": person.display_name,
            "grant_token": token,
            "expires_at": session.expires_at.isoformat(),
        }
    # Reset expired lock counters together; count failures across bindings.
    if any(existing.locked_until and existing.locked_until <= now for existing in sessions):
        for existing in sessions:
            existing.failed_attempts = 0
            existing.locked_until = None
    success = check_pin(body.pin, person.pin_hash)
    db.add(
        IdentityAttempt(
            session_id=session.id, source_message_id=body.source_message_id, success=success
        )
    )
    if not success:
        session.failed_attempts += 1
        failures = (
            sum(s.failed_attempts for s in sessions if s.id != session.id) + session.failed_attempts
        )
        if failures >= settings.pin_max_attempts:
            session.locked_until = now + timedelta(seconds=settings.pin_lock_seconds)
        locked = session.locked_until is not None
        db.commit()  # A failed challenge is durable even though HTTP returns an error.
        raise CentralError(
            "identity_locked" if locked else "invalid_pin",
            "Identity temporarily locked" if locked else "PIN verification failed",
            423 if locked else 401,
        )
    # Switching client invalidates all previous grants on this opaque backend binding.
    for old in db.scalars(
        select(IdentitySession)
        .where(IdentitySession.binding_ref == body.binding_ref)
        .with_for_update()
    ):
        old.token_hash = None
        old.expires_at = None
    for existing in sessions:
        existing.failed_attempts = 0
    session.failed_attempts = 0
    session.expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    token = grant_token(settings, session)
    session.token_hash = digest(token)
    return {
        "customer_id": str(person.id),
        "display_name": person.display_name,
        "grant_token": token,
        "expires_at": session.expires_at.isoformat(),
    }


def revoke(request, db, body):
    if role(request) != "agent":
        raise CentralError("forbidden", "Agent permission required", 403)
    for session in db.scalars(
        select(IdentitySession)
        .where(IdentitySession.binding_ref == body.binding_ref)
        .with_for_update()
    ):
        session.token_hash = None
        session.expires_at = None
    return {"revoked": True}
