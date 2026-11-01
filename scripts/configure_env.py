"""Completa solo secretos internos ausentes. No consulta ni llama servicios externos."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERNAL = (
    "OPERATOR_PASSWORD", "SESSION_SECRET", "CENTRAL_OPERATOR_TOKEN", "CENTRAL_AGENT_TOKEN",
    "PAYMENT_SIGNING_KEY", "CENTRAL_DB_PASSWORD", "MEMORY_DB_PASSWORD",
    "LANGFUSE_NEXTAUTH_SECRET", "LANGFUSE_SALT", "LANGFUSE_ENCRYPTION_KEY",
    "LANGFUSE_DB_PASSWORD", "LANGFUSE_CLICKHOUSE_PASSWORD", "LANGFUSE_REDIS_PASSWORD",
    "LANGFUSE_MINIO_ROOT_PASSWORD", "LANGFUSE_INIT_USER_PASSWORD",
    "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
)


def configure(path: Path = ROOT / ".env") -> int:
    example = (ROOT / ".env.example").read_text()
    content = path.read_text() if path.exists() else example
    values = dict(line.split("=", 1) for line in content.splitlines()
                  if "=" in line and not line.lstrip().startswith("#"))
    for key in INTERNAL:
        if not values.get(key):
            value = secrets.token_hex(32)
            if key == "LANGFUSE_PUBLIC_KEY":
                value = "pk-lf-" + value
            if key == "LANGFUSE_SECRET_KEY":
                value = "sk-lf-" + value
            values[key] = value
    lines = []
    seen = set()
    for line in content.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0]
            line = key + "=" + values[key]
            seen.add(key)
        lines.append(line)
    for line in example.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0]
            if key not in seen:
                lines.append(key + "=" + values.get(key, line.split("=", 1)[1]))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write("\n".join(lines) + "\n")
    path.chmod(0o600)
    print("Configuración privada preparada. Las credenciales del operador están en .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(configure())
