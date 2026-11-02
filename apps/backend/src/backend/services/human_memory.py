"""Passive channel history. Recording never schedules inference or a response."""

import json
from uuid import uuid4

from backend.persistence.models import InboxEvent, ResetMetadata, VerifiedContext, utcnow
from sqlalchemy import BigInteger, cast, select
from sqlalchemy.dialects.postgresql import insert

PREFIX = "human_context.v1:"


class HumanMemory:
    def __init__(self, sessions):
        self.sessions = sessions

    def record(self, event, *, speaker, content, attachments=None):
        if speaker not in {"advisor", "customer"}:
            raise ValueError("Unknown human conversation speaker")
        with self.sessions.begin() as db:
            context = db.get(VerifiedContext, event.thread_id)
            reset = db.get(ResetMetadata, "demo")
            # Do not collect conversations that never entered this demo's memory.
            known = select(InboxEvent.id).where(
                InboxEvent.account_id == str(event.account_id),
                InboxEvent.inbox_id == str(event.inbox_id),
                InboxEvent.conversation_id == str(event.conversation_id),
                InboxEvent.thread_id == event.thread_id,
                InboxEvent.status != "human_context",
            )
            if reset:
                known = known.where(InboxEvent.received_at >= reset.reset_at)
            if context is None or db.scalar(known.limit(1)) is None:
                return {"accepted": False, "reason": "unknown_human_context"}
            # The active authentication arm never imports its content into history.
            if context.challenge_state == "awaiting_pin":
                content = "[Contenido de autenticación omitido]"
            if attachments:
                content += "\n[Adjunto durante atención humana; no interpretado por el bot]"
            result = db.execute(
                insert(InboxEvent).values(
                    id=uuid4(), account_id=str(event.account_id), inbox_id=str(event.inbox_id),
                    conversation_id=str(event.conversation_id), message_id=str(event.message_id),
                    thread_id=event.thread_id, identity_revision=context.identity_revision,
                    normalized_content=PREFIX + json.dumps(
                        {"speaker": speaker, "text": content}, ensure_ascii=False
                    ),
                    attachments=[], received_at=getattr(event, "received_at", None) or utcnow(),
                    status="human_context",
                ).on_conflict_do_nothing(index_elements=["account_id", "message_id"])
                .returning(InboxEvent.id)
            ).scalar_one_or_none()
            return {"accepted": True, "duplicate": result is None, "reason": "human_context"}

    def groups(self, event, identity_revision):
        if not str(event.message_id).isascii() or not str(event.message_id).isdigit():
            return []  # Local diagnostic events do not have Chatwoot message ordering.
        with self.sessions() as db:
            query = select(InboxEvent).where(
                InboxEvent.status == "human_context",
                InboxEvent.account_id == str(event.account_id),
                InboxEvent.inbox_id == str(event.inbox_id),
                InboxEvent.conversation_id == str(event.conversation_id),
                InboxEvent.thread_id == event.thread_id,
                InboxEvent.identity_revision == identity_revision,
                cast(InboxEvent.message_id, BigInteger) < int(event.message_id),
            )
            reset = db.get(ResetMetadata, "demo")
            if reset:
                query = query.where(InboxEvent.received_at >= reset.reset_at)
            # Enough for the ordinary context window; do not read an unbounded archive.
            rows = list(db.scalars(query.order_by(
                cast(InboxEvent.message_id, BigInteger).desc()
            ).limit(30)))
            groups = []
            for row in reversed(rows):
                data = json.loads(row.normalized_content[len(PREFIX):])
                label = "asesorhumano" if data["speaker"] == "advisor" else "cliente (durante atención humana)"
                groups.append({
                    "id": "human:" + str(row.id),
                    "items": [{"role": "user", "content": label + ": " + data["text"]}],
                    "complete": True,
                })
            return groups
