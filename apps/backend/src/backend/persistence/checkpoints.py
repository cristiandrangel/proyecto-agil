"""LangGraph owns its checkpoint schema; setup is separate from Alembic."""

from contextlib import asynccontextmanager

from backend.persistence.queue import validate_source_id


def thread_config(source_id: str) -> dict:
    return {"configurable": {"thread_id": validate_source_id(source_id)}}


@asynccontextmanager
async def checkpointer(conninfo: str | None = None, *, setup: bool = False):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    if conninfo is None:
        from backend.config import get_settings

        conninfo = get_settings().memory_conninfo
    async with AsyncPostgresSaver.from_conn_string(conninfo) as saver:
        if setup:
            await saver.setup()
        yield saver


async def setup_checkpoints(conninfo: str | None = None):
    async with checkpointer(conninfo, setup=True):
        pass


async def delete_thread_checkpoints(source_id: str, conninfo: str | None = None):
    async with checkpointer(conninfo) as saver:
        await saver.adelete_thread(validate_source_id(source_id))
