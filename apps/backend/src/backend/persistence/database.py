from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@lru_cache
def get_engine():
    from backend.config import get_settings

    return create_engine(get_settings().memory_database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory():
    return sessionmaker(get_engine(), expire_on_commit=False)


@contextmanager
def session_scope():
    with get_session_factory().begin() as session:
        yield session
