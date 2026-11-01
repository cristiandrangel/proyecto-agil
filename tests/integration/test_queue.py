import os
import runpy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from agil_shared.errors import DomainError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.persistence.checkpoints import thread_config
from backend.persistence.models import (
    ConversationJob,
    HumanCase,
    InboxEvent,
    Outbox,
    VerifiedContext,
    utcnow,
)
from backend.persistence.outbox import OutboxStore
from backend.persistence.queue import Queue, thread_lock
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def queue_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL queue tests")
    schema = "queue_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    versions = Path(__file__).parents[2] / "migrations/backend/versions"
    with scoped.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for path in sorted(versions.glob("*.py")):
                runpy.run_path(str(path))["upgrade"]()
    sessions = sessionmaker(scoped, expire_on_commit=False)
    yield sessions
    scoped.dispose()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


def enqueue(queue, message="1", source="  +opaque:00009  ", conversation="c1"):
    return queue.enqueue(
        account_id="a",
        inbox_id="i",
        message_id=message,
        conversation_id=conversation,
        source_id=source,
        content="Fictional message",
    )


def test_durable_duplicate_delivery_has_one_job_and_original_destination(queue_store):
    def attempt(number):
        return enqueue(Queue(queue_store), conversation=f"c{number}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert sum(inserted for _, inserted in results) == 1
    assert len({event.id for event, _ in results}) == 1
    with queue_store() as session:
        assert len(session.scalars(select(ConversationJob)).all()) == 1
        original = session.scalar(select(InboxEvent))
        assert original.thread_id == "  +opaque:00009  "
    assert thread_config(original.thread_id)["configurable"]["thread_id"] == original.thread_id


def test_multiple_conversations_share_serial_thread_but_keep_destination(queue_store):
    queue = Queue(queue_store)
    first, _ = enqueue(queue, "1", conversation="c1")
    second, _ = enqueue(queue, "2", conversation="c2")
    one = queue.claim("worker-one")
    assert one.event_id == first.id
    assert queue.claim("worker-two") is None
    queue.complete(one.id, one.claim_token)
    two = queue.claim("worker-two")
    assert two.event_id == second.id
    outbox = OutboxStore(queue_store)
    row = outbox.enqueue(
        event_id=two.event_id,
        identity_revision=0,
        kind="message",
        payload={"content": "hello"},
        operation_key="reply-2",
    )
    assert (row.thread_id, row.account_id, row.inbox_id, row.conversation_id) == (
        second.thread_id,
        "a",
        "i",
        "c2",
    )


def test_expired_worker_claim_is_fenced_and_retries_are_bounded(queue_store):
    queue = Queue(queue_store, max_attempts=2)
    enqueue(queue)
    first = queue.claim("crashed")
    with queue_store.begin() as session:
        session.get(ConversationJob, first.id).lease_until = utcnow() - timedelta(seconds=1)
    recovered = queue.claim("replacement")
    assert recovered.id == first.id
    assert recovered.attempts == 2
    assert recovered.claim_token != first.claim_token
    with pytest.raises(DomainError) as error:
        queue.complete(first.id, first.claim_token)
    assert error.value.code == "stale_claim"
    with queue_store.begin() as session:
        session.get(ConversationJob, recovered.id).lease_until = utcnow() - timedelta(seconds=1)
    assert queue.claim("third") is None
    with queue_store() as session:
        assert session.get(ConversationJob, first.id).state == "failed"


def test_session_thread_lock_prevents_recovery_while_original_worker_alive(queue_store):
    queue = Queue(queue_store)
    event, _ = enqueue(queue)
    original = queue.claim("one")
    with queue_store() as lock_session:
        with thread_lock(lock_session, event.thread_id):
            with queue_store.begin() as session:
                session.get(ConversationJob, original.id).lease_until = utcnow() - timedelta(
                    seconds=1
                )
            assert queue.claim("two") is None
    assert queue.claim("two").id == original.id


def test_outbox_uncertain_is_never_blindly_resent(queue_store):
    event, _ = enqueue(Queue(queue_store))
    store = OutboxStore(queue_store)
    row = store.enqueue(
        event_id=event.id,
        identity_revision=0,
        kind="message",
        payload={"content": "hello"},
        operation_key="reply",
    )
    sending = store.prepare(row.id, pending=True, identity_revision=0)
    assert sending.state == "sending"
    store.mark_uncertain(row.id, claim_token=sending.claim_token)
    assert store.prepare(row.id, pending=True, identity_revision=0) is None
    assert store.queued() == []
    reconciled = store.mark_sent(row.id, "channel-confirmation", claim_token=sending.claim_token)
    assert reconciled.state == "sent"


def test_human_control_or_changed_identity_cancels_pending_output(queue_store):
    event, _ = enqueue(Queue(queue_store))
    store = OutboxStore(queue_store)
    with queue_store.begin() as session:
        session.add(VerifiedContext(thread_id=event.thread_id, identity_revision=1))
    old = store.enqueue(
        event_id=event.id, identity_revision=0, kind="message", payload={}, operation_key="old"
    )
    assert store.prepare(old.id, pending=True, identity_revision=0) is None
    with queue_store.begin() as session:
        session.add(
            HumanCase(
                thread_id=event.thread_id,
                account_id="a",
                inbox_id="i",
                conversation_id="c1",
                source_event_id=event.id,
                reason="human_requested",
                origin="test",
            )
        )
    current = store.enqueue(
        event_id=event.id, identity_revision=1, kind="message", payload={}, operation_key="current"
    )
    assert store.prepare(current.id, pending=True, identity_revision=1) is None
    with queue_store() as session:
        assert session.get(Outbox, current.id).state == "cancelled"


def test_outbox_key_reuse_cannot_change_destination_or_payload(queue_store):
    event, _ = enqueue(Queue(queue_store))
    store = OutboxStore(queue_store)
    values = dict(event_id=event.id, identity_revision=0, kind="message", operation_key="same")
    store.enqueue(**values, payload={"content": "first"})
    with pytest.raises(DomainError) as error:
        store.enqueue(**values, payload={"content": "different"})
    assert error.value.code == "outbox_conflict"


def test_destination_is_immutable_even_via_direct_sql(queue_store):
    event, _ = enqueue(Queue(queue_store))
    row = OutboxStore(queue_store).enqueue(
        event_id=event.id,
        identity_revision=0,
        kind="message",
        payload={},
        operation_key="immutable",
    )
    for table, identity in [("inbox_event", event.id), ("outbox", row.id)]:
        with pytest.raises(DBAPIError, match="destination or identity revision is immutable"):
            with queue_store.begin() as session:
                session.execute(
                    text(f"UPDATE {table} SET conversation_id='different' WHERE id=:id"),
                    {"id": identity},
                )


@pytest.mark.asyncio
async def test_checkpointer_setup_restart_and_delete_keep_literal_key(queue_store):
    from backend.persistence.checkpoints import checkpointer, delete_thread_checkpoints
    from langgraph.checkpoint.base import empty_checkpoint
    from psycopg.conninfo import make_conninfo
    from sqlalchemy.engine import make_url

    with queue_store() as session:
        schema = session.scalar(text("SELECT current_schema()"))
    url = make_url(os.getenv("TEST_MEMORY_DATABASE_URL") or os.environ["TEST_DATABASE_URL"])
    conninfo = make_conninfo(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        options=f"-csearch_path={schema}",
    )
    source_id = "  +opaque:00009  "
    config = thread_config(source_id)
    config["configurable"]["checkpoint_ns"] = ""
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": ["fictional"]}
    checkpoint["channel_versions"] = {"messages": "1"}
    async with checkpointer(conninfo, setup=True) as saver:
        saved = await saver.aput(config, checkpoint, {}, {"messages": "1"})
        await saver.aput_writes(saved, [("messages", "fictional")], "task")
    async with checkpointer(conninfo) as restarted:
        result = await restarted.aget_tuple(config)
        assert result.config["configurable"]["thread_id"] == source_id
        assert result.checkpoint["channel_values"]["messages"] == ["fictional"]
        assert await restarted.aget(thread_config(source_id.strip())) is None
    await delete_thread_checkpoints(source_id, conninfo)
    async with checkpointer(conninfo) as saver:
        assert await saver.aget(config) is None
    with queue_store() as session:
        assert session.scalar(text("SELECT count(*) FROM checkpoint_writes")) == 0


def test_incoming_identity_revision_is_persisted_and_immutable(queue_store):
    queue = Queue(queue_store)
    event, inserted = queue.enqueue(
        account_id="a",
        inbox_id="i",
        message_id="revision",
        conversation_id="c",
        source_id="source-literal",
        content="safe",
        identity_revision=7,
    )
    assert inserted and event.identity_revision == 7
    assert queue.claim("worker").event.identity_revision == 7
    with pytest.raises(DBAPIError, match="identity revision is immutable"):
        with queue_store.begin() as session:
            session.execute(
                text("UPDATE inbox_event SET identity_revision=8 WHERE id=:id"), {"id": event.id}
            )


def test_maintenance_blocks_new_claims_and_outbox_send_without_losing_work(queue_store):
    from backend.persistence.models import ResetMetadata
    from backend.services.budget import BudgetService

    queue = Queue(queue_store)
    event, _ = enqueue(queue)
    store = OutboxStore(queue_store)
    row = store.enqueue(
        event_id=event.id,
        identity_revision=0,
        kind="message",
        payload={},
        operation_key="maintenance-output",
    )
    with queue_store.begin() as session:
        session.add(ResetMetadata(key="demo", maintenance_mode=True))
    assert queue.claim("worker") is None
    assert store.prepare(row.id, pending=True, identity_revision=0) is None
    with pytest.raises(DomainError) as error:
        BudgetService(queue_store).reserve(
            turn_id="turn",
            modality="text",
            model="fixture",
            price_version="test",
            reserved_usd="0.1",
        )
    assert error.value.code == "maintenance"
    with queue_store() as session:
        assert session.get(Outbox, row.id).state == "queued"
        assert session.scalar(select(ConversationJob)).state == "queued"
