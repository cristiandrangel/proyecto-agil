"""Private integration provisioning; no network calls or application data copy."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED = frozenset(
    """
OPENAI_API_KEY OPENAI_AGENT_MODEL OPENAI_AGENT_REASONING_EFFORT
OPENAI_VISION_MODEL OPENAI_VISION_REASONING_EFFORT OPENAI_TRANSCRIPTION_MODEL
OPENAI_TIMEOUT_SECONDS OPENAI_MAX_RETRIES
AI_TOTAL_BUDGET_USD AI_LOCAL_SPEND_LIMIT_USD AI_MAX_CONCURRENT_REQUESTS
AI_MAX_CALLS_PER_TURN AI_MAX_INPUT_TOKENS AI_MAX_OUTPUT_TOKENS AI_VISION_MAX_OUTPUT_TOKENS
CHATWOOT_BASE_URL CHATWOOT_API_TOKEN CHATWOOT_CONTACTS_API_TOKEN CHATWOOT_CONTACTS_BASE_URL
CHATWOOT_ACCOUNT_ID CHATWOOT_INBOX_ID CHATWOOT_WEBHOOK_SECRET CHATWOOT_TEMPLATE_NAME
CHATWOOT_TEMPLATE_LANGUAGE CHATWOOT_TEMPLATE_CATEGORY CHATWOOT_AUTH_SCHEME
CHATWOOT_WEBHOOK_AUTH_MODE CHATWOOT_RELAY_TOKEN CHATWOOT_WEBHOOK_TOLERANCE_SECONDS
CHATWOOT_UI_URL CHATWOOT_UI_EMAIL CHATWOOT_UI_PASSWORD MEDIA_ALLOWED_HOSTS
PUBLIC_BASE_URL PUBLIC_DOMAIN APP_ENV DEMO_MODE ENABLE_LOCAL_MESSAGE_ENDPOINT
CLOUDFLARE_TUNNEL_TOKEN LANGFUSE_CAPTURE_CONTENT LANGFUSE_MEDIA_PUBLIC_ENDPOINT
MEDIA_MAX_BYTES AUDIO_MAX_SECONDS IMAGE_MAX_DIMENSION
OPERATOR_USERNAME OPERATOR_PASSWORD LANGFUSE_INIT_USER_EMAIL LANGFUSE_INIT_USER_NAME LANGFUSE_INIT_USER_PASSWORD
""".split()
)
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def validate(values):
    if not values or set(values) - ALLOWED:
        raise ValueError("Delivery contains unsupported configuration keys or is empty")
    for value in values.values():
        if not isinstance(value, str) or any(char in value for char in "\r\n\x00"):
            raise ValueError("Delivery values must be single-line strings")
    for key in (
        "PUBLIC_BASE_URL",
        "CHATWOOT_BASE_URL",
        "CHATWOOT_CONTACTS_BASE_URL",
        "CHATWOOT_UI_URL",
    ):
        if key in values and values[key]:
            parsed = urlsplit(values[key])
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
            ):
                raise ValueError("Delivery origins must be HTTPS without credentials or paths")
    if values.get("ENABLE_LOCAL_MESSAGE_ENDPOINT", "false").lower() != "false":
        raise ValueError("Live delivery must keep the local message endpoint disabled")
    if "DEMO_MODE" in values and values["DEMO_MODE"].lower() != "true":
        raise ValueError("This delivery requires DEMO_MODE=true for simulated payments")
    if "APP_ENV" in values and values["APP_ENV"] != "production":
        raise ValueError("Live delivery requires APP_ENV=production")
    for key, maximum in [
        ("AI_TOTAL_BUDGET_USD", Decimal("5")),
        ("AI_LOCAL_SPEND_LIMIT_USD", Decimal("4.50")),
    ]:
        if key in values:
            try:
                amount = Decimal(values[key])
            except InvalidOperation as exc:
                raise ValueError("Invalid inference budget") from exc
            if not amount.is_finite() or not Decimal("0") < amount <= maximum:
                raise ValueError("Inference budget exceeds this demo limit or is not positive")
    if (
        "LANGFUSE_MEDIA_PUBLIC_ENDPOINT" in values
        and values["LANGFUSE_MEDIA_PUBLIC_ENDPOINT"] != "http://localhost:19090"
    ):
        raise ValueError("The emulated media public endpoint must use localhost:19090")
    return values


def parse_delivery(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid delivery dotenv syntax")
        key, value = line.split("=", 1)
        key = key.strip()
        if not KEY.fullmatch(key) or key in values:
            raise ValueError("Invalid or duplicate delivery configuration key")
        value = value.strip()
        try:
            value = decode_env_value(value)
        except ValueError:
            raise ValueError("Invalid quoted delivery value") from None
        values[key] = value
    return validate(values)


def decode_env_value(value, *, compose_escaped=False):
    """Decode the literal quoting emitted by this helper, without interpolation."""
    value = value.strip()
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError("Invalid quoted environment value")
        # Compose preserves ordinary backslashes in single quotes. Only an
        # escaped quote is decoded; Python string-literal rules differ here.
        return value[1:-1].replace("\\'", "'")
    if value.startswith('"'):
        try:
            decoded = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            raise ValueError("Invalid quoted environment value") from None
        if not isinstance(decoded, str):
            raise ValueError("Environment values must be strings")
        # The serializer doubles dollar signs only in its double-quoted fallback
        # to suppress Compose interpolation. Delivery input itself is literal.
        return decoded.replace("$$", "$") if compose_escaped else decoded
    return value


def quote_env(value):
    # Compose single quotes preserve dollar signs and ordinary backslashes.
    # A trailing backslash or backslash-before-quote makes that delimiter
    # ambiguous; JSON double quotes handle those cases, with literal dollars.
    if value.endswith("\\") or "\\'" in value:
        return json.dumps(value.replace("$", "$$"), ensure_ascii=False)
    return "'" + value.replace("'", "\\'") + "'"


def merge_environment(original, updates):
    validate(updates)
    lines = []
    seen = set()
    for line in original.splitlines():
        key = (
            line.split("=", 1)[0].strip()
            if "=" in line and not line.lstrip().startswith("#")
            else None
        )
        if key in updates:
            if key in seen:
                raise ValueError("Guest environment contains duplicate integration keys")
            lines.append(key + "=" + quote_env(updates[key]))
            seen.add(key)
        else:
            lines.append(line)
    missing = set(updates) - seen
    if missing:
        # Never append after the established evaluator access section.
        lines = (
            ["# Explicit live integration overrides"]
            + [key + "=" + quote_env(updates[key]) for key in sorted(missing)]
            + [""]
            + lines
        )
    return "\n".join(lines) + "\n"


LANGFUSE_INITIAL_UI = frozenset(
    {"LANGFUSE_INIT_USER_EMAIL", "LANGFUSE_INIT_USER_NAME", "LANGFUSE_INIT_USER_PASSWORD"}
)


def read_environment(text):
    """Decode single-line dotenv values without interpolation or shell execution."""
    values = {}
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        value = decode_env_value(value, compose_escaped=True)
        values[key.strip()] = value
    return values


def runtime_initialized():
    # Volumes survive removed containers. Either means Langfuse may already have
    # initialized its database; INIT_* is not a password reset mechanism.
    for kind in ("ps", "volume"):
        command = ["docker", kind]
        command += ["-aq"] if kind == "ps" else ["ls", "-q"]
        command += ["--filter", "label=com.docker.compose.project=agil-ec2-fixture"]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if result.stdout.strip():
            return True
    return False


def provision(env_path, payload, *, initialized=False):
    updates = validate(payload)
    if not env_path.is_file() or env_path.is_symlink():
        raise ValueError("A regular existing guest environment is required")
    original = env_path.read_text()
    if initialized:
        existing = read_environment(original)
        if any(key in updates and updates[key] != existing.get(key) for key in LANGFUSE_INITIAL_UI):
            raise ValueError(
                "Langfuse is already initialized; INIT user credentials cannot be changed by provisioning"
            )
    output = merge_environment(original, updates)
    temporary = env_path.with_name(".env.live.pending")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(output)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, env_path)
    env_path.chmod(0o600)
    return {
        "updated_keys": sorted(updates),
        "application_restarted": False,
        "tunnel_started": False,
    }


def main():
    # Values arrive only on stdin, never in argv or diagnostic output.
    result = provision(
        Path("/srv/proyecto-agil/app/.env"), json.load(sys.stdin), initialized=runtime_initialized()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
