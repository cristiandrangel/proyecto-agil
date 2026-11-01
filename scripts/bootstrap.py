"""Migración, fixtures limpios idempotentes y arranque de un servicio propio."""
import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent


def main():
    role = sys.argv[1]
    if role == "central":
        cfg = Config(str(ROOT / "apps/central/alembic.ini"))
        command.upgrade(cfg, "head")
        from central.config import get_settings
        from central.db import session_factory
        from central.seed import seed
        settings = get_settings()
        engine, sessions = session_factory(settings)
        if settings.demo_mode:
            with sessions.begin() as session:
                seed(session, settings.demo_pin.get_secret_value())
        engine.dispose()
        port = "8001"
    elif role == "backend":
        cfg = Config(str(ROOT / "migrations/backend/alembic.ini"))
        command.upgrade(cfg, "head")
        from backend.persistence.checkpoints import setup_checkpoints
        asyncio.run(setup_checkpoints())
        port = "8000"
    else:
        raise SystemExit("Servicio inválido")
    os.execvp("uvicorn", ["uvicorn", f"{role}.main:app", "--host", "0.0.0.0",
                         "--port", port, "--no-access-log"])


if __name__ == "__main__":
    main()
