#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"
python_image='python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
# Python runs inside Docker. Never source the private environment as shell code.
docker run --rm --user "$(id -u):$(id -g)" -v "$repo_dir:/workspace" -w /workspace \
  "$python_image" python scripts/configure_env.py
startup_info="$(
  docker run --rm -i --user "$(id -u):$(id -g)" -v "$repo_dir:/workspace:ro" -w /workspace \
    "$python_image" python - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
import re

values = {}
for line in Path(".env").read_text().splitlines():
    if "=" not in line or line.lstrip().startswith("#"):
        continue
    key, value = line.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    values[key.strip()] = value
origin = values.get("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
try:
    parsed = urlsplit(origin)
    valid = (
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
        and not parsed.username and not parsed.password
        and not parsed.query and not parsed.fragment
        and not parsed.path
        and (parsed.port is None or 1 <= parsed.port <= 65535)
        and not any(character.isspace() for character in origin)
    )
except ValueError:
    valid = False
if not valid:
    raise SystemExit("PUBLIC_BASE_URL debe ser un origen HTTP(S) sin ruta, credenciales, query ni fragmento.")
print(origin)
print("public" if parsed.scheme == "https" and values.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip() else "local")
PY
)"
public_base_url="${startup_info%%$'\n'*}"
startup_profile="${startup_info##*$'\n'}"
compose_args=(--env-file .env -f infra/compose.yaml)
if [[ "$startup_profile" == public ]]; then
  compose_args+=(--profile public)
  printf '%s\n' 'Conector público habilitado para el origen HTTPS configurado.'
fi
docker compose "${compose_args[@]}" up -d --build --wait "$@"
printf '%s\n' "Aplicación: $public_base_url/central" 'Credenciales privadas: OPERATOR_USERNAME y OPERATOR_PASSWORD en .env'
