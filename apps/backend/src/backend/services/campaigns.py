"""Snapshot campaigns: one durable recipient per person, sequential dispatch."""

from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from agil_shared.errors import DomainError
from backend.persistence.database import get_session_factory
from backend.persistence.models import (
    Campaign,
    CampaignRecipient,
    ChannelBinding,
    HumanCase,
    Outbox,
    ResetMetadata,
    VerifiedContext,
    utcnow,
)
from backend.persistence.outbox import OutboxStore
from backend.persistence.queue import thread_lock
from backend.services.metrics import MetricsService
from sqlalchemy import select, text

BUCKETS = {
    "0": (0, 0),
    "0-29": (0, 29),
    "1-29": (1, 29),
    "30-59": (30, 59),
    "60-89": (60, 89),
    "90-119": (90, 119),
    "120+": (120, None),
}


def normalize_filters(filters):
    if not isinstance(filters, dict):
        raise DomainError("invalid_filters", "Filtros inválidos.", status=422)
    allowed = {
        "service_type",
        "customer_type",
        "document_number",
        "document_type",
        "dias_mora_min",
        "dias_mora_max",
        "debt_status",
    }
    result = {k: v for k, v in filters.items() if k in allowed and v not in (None, "")}
    bucket = filters.get("overdue_bucket")
    if bucket:
        if bucket not in BUCKETS:
            raise DomainError("invalid_bucket", "Rango de mora inválido.", status=422)
        lower, upper = BUCKETS[bucket]
        result["dias_mora_min"] = lower
        if upper is not None:
            result["dias_mora_max"] = upper
        else:
            result.pop("dias_mora_max", None)
    for key in ("dias_mora_min", "dias_mora_max"):
        if key in result:
            try:
                if isinstance(result[key], bool) or not str(result[key]).isdigit():
                    raise ValueError()
                value = int(result[key])
                if value < 0:
                    raise ValueError()
                result[key] = value
            except (TypeError, ValueError):
                raise DomainError(
                    "invalid_mora", "La mora debe ser un entero no negativo.", status=422
                ) from None
    if result.get("dias_mora_min", 0) > result.get("dias_mora_max", 2**31):
        raise DomainError("invalid_mora", "El mínimo supera el máximo de mora.", status=422)
    return result


def matches_filters(debt, filters):
    customer = debt.get("customer", debt)
    for field, expected in filters.items():
        if field == "dias_mora_min" and int(debt.get("dias_mora", 0)) < expected:
            return False
        if field == "dias_mora_max" and int(debt.get("dias_mora", 0)) > expected:
            return False
        if field not in {"dias_mora_min", "dias_mora_max"} and str(
            debt.get(field, customer.get(field))
        ) != str(expected):
            return False
    return True


def campaign_uuid(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise DomainError("campaign_not_found", "Campaña no encontrada.", status=404) from None


@contextmanager
def dispatch_lock(sessions):
    with sessions().get_bind().engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(74210003)"))
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(74210003)"))
                    connection.commit()
                except Exception:
                    connection.invalidate()
                    raise


class CampaignService:
    def __init__(self, central_client, session_factory=None, *, channel=None, followup_hours=24):
        self.central = central_client
        self.sessions = session_factory or get_session_factory()
        self.channel = channel
        self.followup_hours = followup_hours
        self.outbox = OutboxStore(self.sessions)

    @staticmethod
    def _expire_followups(session):
        for campaign in session.scalars(
            select(Campaign).where(
                Campaign.status.in_(["running", "completed"]), Campaign.followup_until <= utcnow()
            )
        ):
            campaign.status = "closed"
            campaign.closed_at = campaign.followup_until
            for recipient in session.scalars(
                select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)
            ):
                recipient.active = False
                if recipient.send_status == "queued":
                    recipient.send_status = "skipped"
                    recipient.reason = "followup_expired"
                    recipient.processed_at = utcnow()
        session.flush()

    async def _debts(self, filters):
        items, page = [], 1
        while True:
            response = await self.central.request(
                "GET", "/debts", params={**filters, "page": page, "page_size": 200}
            )
            batch = response.get("items", [])
            items.extend(batch)
            if len(items) >= int(response.get("total", len(items))) or not batch:
                return items
            page += 1

    @staticmethod
    def _recipient_view(recipient):
        binding = recipient.destination_binding or {}
        phone = binding.get("phone_e164", "")
        return {
            "id": str(recipient.id),
            "customer_id": str(recipient.customer_id),
            "position": recipient.position,
            "debt_ids": recipient.selected_debt_ids,
            "delivery_mode": recipient.delivery_mode,
            "masked_destination": "***" + phone[-4:] if phone else "Sin celular",
            "status": recipient.send_status,
            "send_status": recipient.send_status,
            "reason": recipient.reason,
            "exclusion_reason": recipient.reason,
        }

    async def preview(self, filters):
        filters = normalize_filters(filters)
        debts = await self._debts(filters)
        people = {}
        for debt in debts:
            if (
                debt.get("debt_status", "pendiente") != "pendiente"
                or int(debt.get("balance_cents", 0)) <= 0
            ):
                continue
            customer = debt.get("customer", debt)
            customer_id = str(debt["customer_id"])
            entry = people.setdefault(
                customer_id, {"customer": customer, "debt_ids": [], "debt_balances": {}}
            )
            entry["debt_ids"].append(str(debt["id"]))
            entry["debt_balances"][str(debt["id"])] = int(debt["balance_cents"])
        with self.sessions.begin() as session:
            self._expire_followups(session)
            campaign = Campaign(filter_snapshot=filters, template_snapshot={"preview": True})
            session.add(campaign)
            session.flush()
            recipients = []
            for position, (customer_id, entry) in enumerate(sorted(people.items())):
                customer = entry["customer"]
                mode = customer.get("delivery_mode", "simulated")
                reason = None
                if mode == "live" and not customer.get("test_contact_enabled", False):
                    reason = "live_contact_not_enabled"
                if mode == "live" and not customer.get("phone_e164"):
                    reason = "missing_phone"
                if session.scalar(
                    select(CampaignRecipient.id)
                    .where(
                        CampaignRecipient.customer_id == UUID(customer_id),
                        CampaignRecipient.active.is_(True),
                    )
                    .limit(1)
                ):
                    reason = "active_campaign"
                recipient = CampaignRecipient(
                    campaign_id=campaign.id,
                    customer_id=UUID(customer_id),
                    selected_debt_ids=sorted(set(entry["debt_ids"])),
                    contact_version=int(customer.get("contact_version", 1)),
                    position=position,
                    delivery_mode=mode,
                    active=False,
                    send_status="skipped" if reason else "queued",
                    reason=reason,
                    destination_binding={
                        "phone_e164": customer.get("phone_e164", ""),
                        "test_contact_enabled": customer.get("test_contact_enabled", False),
                        "debt_balances": entry["debt_balances"],
                    },
                )
                session.add(recipient)
                session.flush()
                recipients.append(self._recipient_view(recipient))
            return {
                "preview_id": str(campaign.id),
                "recipients_total": len(recipients),
                "eligible_total": sum(not r["reason"] for r in recipients),
                "recipients": recipients,
                "filters": filters,
            }

    async def create(self, payload):
        filters = normalize_filters(payload.get("filters", {}))
        preview_id = payload.get("preview_id")
        if not preview_id:
            preview_id = (await self.preview(filters))["preview_id"]
        with self.sessions.begin() as session:
            campaign = session.get(Campaign, campaign_uuid(preview_id), with_for_update=True)
            if campaign is None or campaign.status != "draft":
                raise DomainError("preview_expired", "Genera otra previsualización.", status=409)
            if campaign.filter_snapshot != filters:
                raise DomainError(
                    "preview_changed", "Los filtros cambiaron. Previsualiza de nuevo.", status=409
                )
            name = str(payload.get("name", "Campaña demo")).strip()[:120]
            template = str(payload.get("template_name", "")).strip()
            language = str(payload.get("template_language", "es")).strip()
            if not template or not language:
                raise DomainError(
                    "template_required",
                    "Selecciona una plantilla aprobada y su idioma.",
                    status=422,
                )
            snapshot = {"name": name, "template_name": template, "template_language": language}
            if (
                campaign.template_snapshot.get("preview") is not True
                and campaign.template_snapshot != snapshot
            ):
                raise DomainError(
                    "campaign_exists",
                    "La previsualización ya tiene otra configuración.",
                    status=409,
                )
            campaign.template_snapshot = snapshot
        return await self.get(preview_id)

    async def launch(self, campaign_id, idempotency_key):
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key
            or len(idempotency_key) > 200
        ):
            raise DomainError("idempotency_required", "Falta la clave de lanzamiento.", status=422)
        ident = campaign_uuid(campaign_id)
        with self.sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(74210004)"))
            self._expire_followups(session)
            campaign = session.get(Campaign, ident, with_for_update=True)
            if campaign is None:
                raise DomainError("campaign_not_found", "Campaña no encontrada.", status=404)
            other = session.scalar(select(Campaign).where(Campaign.launch_key == idempotency_key))
            if other is not None and other.id != ident:
                raise DomainError(
                    "launch_conflict", "La clave pertenece a otra campaña.", status=409
                )
            if campaign.launch_key:
                if campaign.launch_key != idempotency_key:
                    raise DomainError("already_launched", "La campaña ya fue lanzada.", status=409)
            else:
                if campaign.status != "draft" or campaign.template_snapshot.get("preview"):
                    raise DomainError(
                        "campaign_not_ready",
                        "Guarda la configuración de campaña primero.",
                        status=409,
                    )
                recipients = list(
                    session.scalars(
                        select(CampaignRecipient)
                        .where(CampaignRecipient.campaign_id == ident)
                        .order_by(CampaignRecipient.position)
                    )
                )
                for recipient in recipients:
                    if recipient.send_status != "queued":
                        continue
                    other_recipient = session.scalar(
                        select(CampaignRecipient.id)
                        .where(
                            CampaignRecipient.customer_id == recipient.customer_id,
                            CampaignRecipient.active.is_(True),
                        )
                        .limit(1)
                    )
                    if other_recipient:
                        recipient.send_status = "skipped"
                        recipient.reason = "active_campaign"
                        recipient.processed_at = utcnow()
                    else:
                        recipient.active = True
                campaign.launch_key = idempotency_key
                campaign.launched_at = utcnow()
                campaign.followup_until = utcnow() + timedelta(hours=self.followup_hours)
                campaign.status = (
                    "running" if any(r.send_status == "queued" for r in recipients) else "completed"
                )
        return await self.get(ident)

    async def close(self, campaign_id):
        ident = campaign_uuid(campaign_id)
        with self.sessions.begin() as session:
            campaign = session.get(Campaign, ident, with_for_update=True)
            if campaign is None:
                raise DomainError("campaign_not_found", "Campaña no encontrada.", status=404)
            if campaign.closed_at is None:
                campaign.closed_at = utcnow()
            campaign.status = "closed"
            for recipient in session.scalars(
                select(CampaignRecipient).where(CampaignRecipient.campaign_id == ident)
            ):
                recipient.active = False
                if recipient.send_status == "queued":
                    recipient.send_status = "skipped"
                    recipient.reason = "campaign_closed"
                    recipient.processed_at = utcnow()
        return await self.get(ident)

    async def get(self, campaign_id):
        ident = campaign_uuid(campaign_id)
        with self.sessions() as session:
            campaign = session.get(Campaign, ident)
            if campaign is None:
                raise DomainError("campaign_not_found", "Campaña no encontrada.", status=404)
            recipients = list(
                session.scalars(
                    select(CampaignRecipient)
                    .where(CampaignRecipient.campaign_id == ident)
                    .order_by(CampaignRecipient.position)
                )
            )
            processed = sum(r.send_status != "queued" for r in recipients)
            return {
                "id": str(ident),
                "campaign_id": str(ident),
                "name": campaign.template_snapshot.get("name", "Previsualización"),
                "status": campaign.status,
                "filters": campaign.filter_snapshot,
                "template": campaign.template_snapshot,
                "recipients_total": len(recipients),
                "recipients_processed": processed,
                "recipients_pending": len(recipients) - processed,
                "recipients": [self._recipient_view(r) for r in recipients],
                "followup_until": campaign.followup_until.isoformat()
                if campaign.followup_until
                else None,
            }

    async def metrics(self, campaign_id):
        return await MetricsService(self.sessions).get(campaign_id)

    def _finish(self, recipient_id, status, reason=None, *, sent_at=None):
        with self.sessions.begin() as session:
            recipient = session.get(CampaignRecipient, recipient_id, with_for_update=True)
            if recipient is None:
                return
            recipient.send_status = status
            recipient.reason = reason
            recipient.processed_at = utcnow()
            if status == "sent":
                recipient.sent_at = sent_at or utcnow()
            session.flush()
            campaign = session.get(Campaign, recipient.campaign_id)
            if campaign.status == "running" and not session.scalar(
                select(CampaignRecipient.id)
                .where(
                    CampaignRecipient.campaign_id == campaign.id,
                    CampaignRecipient.send_status == "queued",
                )
                .limit(1)
            ):
                campaign.status = "completed"

    async def dispatch_one(self):
        with dispatch_lock(self.sessions) as acquired:
            if not acquired:
                return None
            with self.sessions.begin() as session:
                for uncertain in session.scalars(
                    select(CampaignRecipient).where(CampaignRecipient.send_status == "uncertain")
                ):
                    confirmed = session.scalar(
                        select(Outbox).where(
                            Outbox.operation_key
                            == f"campaign:{uncertain.campaign_id}:recipient:{uncertain.id}",
                            Outbox.state == "sent",
                        )
                    )
                    if confirmed is not None:
                        uncertain.send_status = "sent"
                        uncertain.sent_at = confirmed.created_at
                        uncertain.reason = None
                session.execute(text("SELECT pg_advisory_xact_lock(74210001)"))
                maintenance = session.get(ResetMetadata, "demo")
                if maintenance and maintenance.maintenance_mode:
                    return None
                now = utcnow()
                for expired in session.scalars(
                    select(Campaign).where(
                        Campaign.status.in_(["running", "completed"]),
                        Campaign.followup_until <= now,
                    )
                ):
                    expired.status = "closed"
                    expired.closed_at = expired.followup_until
                    for row in session.scalars(
                        select(CampaignRecipient).where(CampaignRecipient.campaign_id == expired.id)
                    ):
                        row.active = False
                        if row.send_status == "queued":
                            row.send_status = "skipped"
                            row.reason = "followup_expired"
                            row.processed_at = now
                recipient = session.scalar(
                    select(CampaignRecipient)
                    .join(Campaign)
                    .where(Campaign.status == "running", CampaignRecipient.send_status == "queued")
                    .order_by(Campaign.launched_at, CampaignRecipient.position)
                    .limit(1)
                    .with_for_update(of=CampaignRecipient)
                )
                if recipient is None:
                    for finished in session.scalars(
                        select(Campaign).where(Campaign.status == "running")
                    ):
                        if not session.scalar(
                            select(CampaignRecipient.id)
                            .where(
                                CampaignRecipient.campaign_id == finished.id,
                                CampaignRecipient.send_status == "queued",
                            )
                            .limit(1)
                        ):
                            finished.status = "completed"
                    return None
                campaign = session.get(Campaign, recipient.campaign_id)
                recipient_id, campaign_id = recipient.id, campaign.id
                template = dict(campaign.template_snapshot)
                customer_id, contact_version, mode = (
                    recipient.customer_id,
                    recipient.contact_version,
                    recipient.delivery_mode,
                )
                debt_ids = list(recipient.selected_debt_ids)
                filters = dict(campaign.filter_snapshot)
            # Re-read central eligibility; simulations still never access the channel.
            latest = []
            try:
                for debt_id in debt_ids:
                    latest.append(await self.central.request("GET", f"/debts/{debt_id}"))
                eligible = [
                    d
                    for d in latest
                    if d.get("debt_status") == "pendiente"
                    and int(d.get("balance_cents", 0)) > 0
                    and str(d.get("customer_id")) == str(customer_id)
                    and matches_filters(d, filters)
                ]
                if not eligible:
                    self._finish(recipient_id, "skipped", "no_eligible_debt")
                    return {"recipient_id": str(recipient_id), "status": "skipped"}
                customer = eligible[0].get("customer", eligible[0])
                if (
                    int(customer.get("contact_version", 0)) != contact_version
                    or customer.get("delivery_mode") != mode
                    or (mode == "live" and not customer.get("test_contact_enabled", False))
                ):
                    self._finish(recipient_id, "skipped", "contact_changed")
                    return {"recipient_id": str(recipient_id), "status": "skipped"}
                if mode == "simulated":
                    self._finish(recipient_id, "simulated")
                    return {"recipient_id": str(recipient_id), "status": "simulated"}
                if self.channel is None:
                    raise DomainError(
                        "channel_unavailable", "Canal real no configurado.", status=503
                    )
                binding = await self.channel.resolve_contact(customer)
                if (
                    not isinstance(binding.get("source_id"), str)
                    or not binding["source_id"]
                    or any(
                        binding.get(key) is None
                        for key in ("account_id", "inbox_id", "contact_id", "conversation_id")
                    )
                ):
                    raise DomainError(
                        "invalid_source_id", "El canal no devolvió source_id literal."
                    )
            except DomainError as error:
                self._finish(recipient_id, "failed", error.code)
                return {"recipient_id": str(recipient_id), "status": "failed"}
            try:
                with (
                    self.sessions() as lock_session,
                    thread_lock(lock_session, binding["source_id"]),
                ):
                    return await self._send_bound(
                        recipient_id,
                        campaign_id,
                        binding,
                        template,
                        customer_id,
                        contact_version,
                        mode,
                        debt_ids,
                        filters,
                    )
            except DomainError as error:
                if error.code == "thread_busy":
                    return {"recipient_id": str(recipient_id), "status": "deferred"}
                self._finish(recipient_id, "failed", error.code)
                return {"recipient_id": str(recipient_id), "status": "failed"}

    async def _send_bound(
        self,
        recipient_id,
        campaign_id,
        binding,
        template,
        customer_id,
        contact_version,
        mode,
        debt_ids,
        filters,
    ):
        # The literal-source lock serializes this template against identity turns and
        # human takeover. Re-read central AFTER the potentially slow contact lookup.
        current = await self.channel.conversation(binding["conversation_id"])
        if current.get("status") != "pending":
            self._finish(recipient_id, "skipped", "human_control")
            return {"recipient_id": str(recipient_id), "status": "skipped"}
        latest = [await self.central.request("GET", f"/debts/{debt_id}") for debt_id in debt_ids]
        eligible = [
            debt
            for debt in latest
            if debt.get("debt_status") == "pendiente"
            and int(debt.get("balance_cents", 0)) > 0
            and str(debt.get("customer_id")) == str(customer_id)
            and matches_filters(debt, filters)
        ]
        if not eligible:
            self._finish(recipient_id, "skipped", "no_eligible_debt")
            return {"recipient_id": str(recipient_id), "status": "skipped"}
        customer = eligible[0].get("customer", eligible[0])
        if (
            int(customer.get("contact_version", 0)) != contact_version
            or customer.get("delivery_mode") != mode
            or not customer.get("test_contact_enabled", False)
        ):
            self._finish(recipient_id, "skipped", "contact_changed")
            return {"recipient_id": str(recipient_id), "status": "skipped"}
        with self.sessions() as session:
            controlled = (
                session.scalar(
                    select(HumanCase.id)
                    .where(
                        HumanCase.thread_id == binding["source_id"],
                        HumanCase.status.in_(["open", "transferred"]),
                    )
                    .limit(1)
                )
                is not None
            )
            context = session.get(VerifiedContext, binding["source_id"])
            identity_revision = context.identity_revision if context else 0
        if controlled:
            self._finish(recipient_id, "skipped", "human_control")
            return {"recipient_id": str(recipient_id), "status": "skipped"}
        operation_key = f"campaign:{campaign_id}:recipient:{recipient_id}"
        with self.sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(74210001)"))
            maintenance = session.get(ResetMetadata, "demo")
            if maintenance is not None and maintenance.maintenance_mode:
                return None
            recipient = session.get(CampaignRecipient, recipient_id, with_for_update=True)
            campaign = session.get(Campaign, campaign_id)
            if (
                campaign is None
                or recipient is None
                or campaign.status != "running"
                or recipient.send_status != "queued"
            ):
                return None
            recipient.destination_binding = {
                **(recipient.destination_binding or {}),
                **binding,
                "debt_balances": {str(d["id"]): int(d["balance_cents"]) for d in latest},
            }
            recipient.account_id = str(binding["account_id"])
            recipient.inbox_id = str(binding["inbox_id"])
            recipient.conversation_id = str(binding["conversation_id"])
            recipient.thread_id = binding["source_id"]
            existing_binding = session.scalar(
                select(ChannelBinding).where(
                    ChannelBinding.customer_id == customer_id,
                    ChannelBinding.contact_version == contact_version,
                    ChannelBinding.account_id == recipient.account_id,
                    ChannelBinding.inbox_id == recipient.inbox_id,
                )
            )
            if existing_binding is None:
                session.add(
                    ChannelBinding(
                        customer_id=customer_id,
                        contact_version=contact_version,
                        account_id=recipient.account_id,
                        inbox_id=recipient.inbox_id,
                        contact_id=str(binding["contact_id"]),
                        source_id=binding["source_id"],
                        conversation_id=recipient.conversation_id,
                    )
                )
            recipient.send_status = "uncertain"
            recipient.processed_at = utcnow()
            outbox = Outbox(
                operation_key=operation_key,
                thread_id=binding["source_id"],
                identity_revision=identity_revision,
                account_id=recipient.account_id,
                inbox_id=recipient.inbox_id,
                conversation_id=recipient.conversation_id,
                kind="template",
                payload_private=template,
                state="sending",
                attempts=1,
                claim_token=uuid4(),
                lease_until=utcnow() + timedelta(seconds=120),
            )
            session.add(outbox)
            session.flush()
            outbox_id, claim_token = outbox.id, outbox.claim_token
        try:
            result = await self.channel.send_template(binding, template, operation_key)
            message_id = result.get("message_id") or result.get("id")
            if message_id is None:
                raise DomainError(
                    "channel_uncertain", "El canal no confirmó el mensaje.", status=503
                )
            self.outbox.mark_sent(outbox_id, str(message_id), claim_token=claim_token)
            self._finish(recipient_id, "sent")
            return {"recipient_id": str(recipient_id), "status": "sent"}
        except Exception:
            self.outbox.mark_uncertain(outbox_id, claim_token=claim_token)
            self._finish(recipient_id, "uncertain", "channel_result_uncertain")
            return {"recipient_id": str(recipient_id), "status": "uncertain"}
