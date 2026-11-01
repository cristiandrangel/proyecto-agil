from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from central.models import CentralEvent


def ordered_events(session, flush_context, instances):
    if any(isinstance(item, CentralEvent) for item in session.new):
        # Sequence values alone do not follow commit order. Serialize publication
        # until commit so a consumer cannot skip an earlier uncommitted event.
        session.execute(text("SELECT pg_advisory_xact_lock(3718021049921)"))


def session_factory(settings):
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        raise ValueError("Central requires PostgreSQL; SQLite is not supported")
    factory = sessionmaker(engine, expire_on_commit=False)
    event.listen(factory, "before_flush", ordered_events)
    return engine, factory
