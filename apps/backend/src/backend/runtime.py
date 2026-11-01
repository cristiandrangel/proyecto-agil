from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.integrations.central import CentralClient
from backend.integrations.chatwoot import ChatwootClient
from backend.integrations.observability import Observability
from backend.integrations.openai import InferenceClient
from backend.persistence.models import ResetMetadata
from backend.persistence.outbox import OutboxStore
from backend.persistence.queue import Queue
from backend.services.budget import BudgetService
from backend.services.campaigns import CampaignService
from backend.services.demo import DemoService
from backend.services.events import EventService
from backend.services.handoff import HandoffService
from backend.services.identity import IdentityService


class Runtime:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        s = self.settings
        self.engine = create_engine(s.memory_database_url, pool_pre_ping=True)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.central = CentralClient(s)
        self.operator_central = CentralClient(s, role="operator")
        self.channel = ChatwootClient(s)
        self.observability = Observability(s)
        self.budget = BudgetService(self.sessions, limit_usd=s.ai_local_spend_limit_usd,
                                    max_active_calls=s.ai_max_concurrent_requests)
        self.inference = InferenceClient(s, self.budget, self.observability)
        self.queue = Queue(self.sessions)
        self.outbox = OutboxStore(self.sessions)
        self.identity = IdentityService(s, self.sessions, self.central)
        self.handoff = HandoffService(s, self.sessions, self.channel, self.observability)
        self.campaigns = CampaignService(self.operator_central, self.sessions, channel=self.channel,
                                         followup_hours=s.campaign_followup_hours)
        self.events = EventService(self.operator_central, self.sessions)
        self.demo = DemoService(s, self.operator_central, session_factory=self.sessions)

    def maintenance(self):
        with self.sessions() as session:
            metadata = session.get(ResetMetadata, "demo")
            return bool(metadata and metadata.maintenance_mode)

    async def close(self):
        self.observability.flush()
        await self.inference.sdk.close()
        self.engine.dispose()
