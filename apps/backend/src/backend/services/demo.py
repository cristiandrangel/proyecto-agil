"""Recoverable demo reset; the two databases do not share a transaction."""

from __future__ import annotations

import asyncio
import uuid

from agil_shared.errors import DomainError
from backend.persistence.checkpoints import checkpointer
from backend.persistence.database import get_session_factory
from backend.persistence.models import (
    ConversationJob,
    InboxEvent,
    Outbox,
    ResetMetadata,
    VerifiedContext,
    utcnow,
)
from backend.persistence.reset import reset_operational
from sqlalchemy import inspect, select, text


class DemoService:
    def __init__(self, settings, central=None, *, session_factory=None):
        from backend.integrations.central import CentralClient

        self.settings = settings
        self.central = central or CentralClient(settings, role="operator")
        self.sessions = session_factory or get_session_factory()

    async def status(self):
        with self.sessions() as db:
            metadata = db.get(ResetMetadata, "demo")
            return {
                "maintenance_mode": bool(metadata and metadata.maintenance_mode),
                "operation_key": metadata.reset_operation_key if metadata else None,
                "stage": metadata.reset_stage if metadata else None,
                "epoch": metadata.epoch if metadata else 0,
            }

    async def seed(self):
        if not self.settings.demo_mode:
            raise DomainError("demo_disabled", "Modo demo deshabilitado.", status=403)
        return await self.central.request(
            "POST", "/demo/seed", idempotency_key="public-demo-seed-v1"
        )

    def _stage(self, stage, result=None):
        with self.sessions.begin() as db:
            metadata = db.get(ResetMetadata, "demo", with_for_update=True)
            metadata.reset_stage = stage
            if result is not None:
                metadata.reset_result = result

    def _assert_idle(self):
        with self.sessions() as db:
            busy_job = db.scalar(
                select(ConversationJob.id)
                .where(
                    ConversationJob.state == "processing", ConversationJob.lease_until > utcnow()
                )
                .limit(1)
            )
            busy_send = db.scalar(
                select(Outbox.id)
                .where(Outbox.state == "sending", Outbox.lease_until > utcnow())
                .limit(1)
            )
            if busy_job or busy_send:
                raise DomainError(
                    "reset_busy",
                    "Mantenimiento activo. Espera a que termine el trabajo en curso y reintenta la misma operación.",
                    status=409,
                    retryable=True,
                )

    async def _clear_checkpoints(self):
        with self.sessions() as db:
            sources = set(db.scalars(select(InboxEvent.thread_id))) | set(
                db.scalars(select(VerifiedContext.thread_id))
            )
            checkpoint_exists = inspect(db.connection()).has_table("checkpoints")
            if checkpoint_exists:
                sources.update(db.scalars(text("SELECT DISTINCT thread_id FROM checkpoints")))
        if checkpoint_exists:
            async with checkpointer(self.settings.memory_conninfo) as saver:
                for source in sources:
                    await saver.adelete_thread(source)

    async def reset(self, payload):
        if not self.settings.demo_mode:
            raise DomainError("demo_disabled", "Modo demo deshabilitado.", status=403)
        if payload.get("confirmation") != "RESET_DEMO":
            raise DomainError(
                "confirmation_required", "Confirma explícitamente el reinicio.", status=422
            )
        supplied = payload.get("operation_key")
        try:
            operation = str(uuid.UUID(str(supplied))) if supplied else None
        except ValueError:
            raise DomainError(
                "invalid_operation_key", "La operación debe usar una llave UUID.", status=422
            ) from None
        # A session lock spans network/checkpoint work, without keeping a DB transaction open.
        with self.sessions() as bind_session:
            engine = bind_session.get_bind()
        with engine.connect() as lock_session:
            acquired = lock_session.scalar(text("SELECT pg_try_advisory_lock(74219002)"))
            lock_session.commit()
            if not acquired:
                raise DomainError(
                    "reset_busy", "Ya hay un reinicio en curso.", status=409, retryable=True
                )
            try:
                with self.sessions.begin() as db:
                    db.execute(text("SELECT pg_advisory_xact_lock(74210001)"))
                    metadata = db.get(ResetMetadata, "demo", with_for_update=True)
                    if metadata is None:
                        metadata = ResetMetadata(
                            key="demo", epoch=0, event_cutoff=0, maintenance_mode=False
                        )
                        db.add(metadata)
                    if (
                        operation
                        and metadata.reset_operation_key == operation
                        and metadata.reset_stage == "completed"
                    ):
                        return metadata.reset_result
                    if metadata.maintenance_mode:
                        if operation and operation != metadata.reset_operation_key:
                            raise DomainError(
                                "reset_operation_conflict",
                                "Reanuda la operación de mantenimiento pendiente.",
                                status=409,
                            )
                        operation = metadata.reset_operation_key
                    else:
                        operation = operation or str(uuid.uuid4())
                        metadata.maintenance_mode = True
                        metadata.reset_operation_key = operation
                        metadata.reset_stage = "paused"
                        metadata.reset_result = None
                    stage = metadata.reset_stage
                    saved = metadata.reset_result or {}
                self._assert_idle()
                if stage == "paused":
                    await self._clear_checkpoints()
                    self._stage("checkpoints_cleared")
                    stage = "checkpoints_cleared"
                if stage == "checkpoints_cleared":
                    result = await self.central.request(
                        "POST",
                        "/demo/reset",
                        idempotency_key=f"demo-reset:{operation}",
                        json={
                            "confirmation": "RESET_DEMO",
                            "backend_reset_confirmed": True,
                            "epoch": operation,
                        },
                    )
                    saved = {"central": result}
                    self._stage("central_reset", saved)
                    stage = "central_reset"
                if stage == "central_reset":
                    await asyncio.to_thread(
                        reset_operational,
                        event_cutoff=int(saved["central"]["event_cutoff"]),
                        session_factory=self.sessions,
                        operation_key=operation,
                    )
                    stage = "operational_reset"
                if stage != "operational_reset":
                    raise DomainError(
                        "reset_stage_invalid",
                        "El mantenimiento requiere revisión de su etapa persistida.",
                        status=409,
                    )
                with self.sessions.begin() as db:
                    metadata = db.get(ResetMetadata, "demo", with_for_update=True)
                    result = {
                        "status": "complete",
                        "operation_key": operation,
                        "epoch": metadata.epoch,
                        "central_epoch": operation,
                        "event_cutoff": metadata.event_cutoff,
                    }
                    metadata.reset_result = result
                    metadata.reset_stage = "completed"
                    metadata.maintenance_mode = False
                return result
            finally:
                lock_session.execute(text("SELECT pg_advisory_unlock(74219002)"))
                lock_session.commit()
