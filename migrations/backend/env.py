from alembic import context
from backend.config import get_settings
from backend.persistence.models import Base
from sqlalchemy import create_engine


def run_migrations_online():
    engine = create_engine(get_settings().memory_database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=get_settings().memory_database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
