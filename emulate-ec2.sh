#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"
command -v docker >/dev/null || { echo 'Instala Docker Desktop o Docker Engine y Compose v2.' >&2; exit 2; }
docker compose version >/dev/null
engine_info="$(docker info --format '{{.OSType}}|{{.OperatingSystem}}')"
[[ "$engine_info" == linux\|* ]] || { echo 'Activa Linux containers en Docker Desktop.' >&2; exit 2; }
if [[ -n "${DOCKER_CONTEXT:-}" ]]; then
  endpoint="$(docker context inspect "$DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}')"
else
  endpoint="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
fi
case "$endpoint" in
  unix://*|npipe://*) ;;
  *) echo 'Usa un contexto Docker local; SSH/TCP remoto no comparte este checkout.' >&2; exit 2 ;;
esac
# Desktop exposes this socket inside its Linux VM, independently of the client pipe/socket.
if [[ "$engine_info" == *'Docker Desktop'* ]]; then
  socket_source="${EC2_DOCKER_SOCKET:-/var/run/docker.sock}"
elif [[ "$endpoint" == unix://* ]]; then
  socket_source="${EC2_DOCKER_SOCKET:-${endpoint#unix://}}"
else
  echo 'Se requiere un contexto Docker local; SSH/TCP remotos no comparten la carpeta del repo.' >&2; exit 2
fi
network=agil-ec2-control
if ! docker network inspect "$network" >/dev/null 2>&1; then
  docker network create --label io.proyecto-agil.emulation=control "$network" >/dev/null
elif [[ "$(docker network inspect --format '{{index .Labels "io.proyecto-agil.emulation"}}' "$network")" != control ]]; then
  echo 'El nombre de red agil-ec2-control pertenece a otro recurso; no se modificó.' >&2; exit 2
fi
docker build -t agil-ec2-runner:local -f infra/floci-runtime/Dockerfile.runner infra/floci-runtime
[[ "$#" -gt 0 ]] || set -- up
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[i]}" == --delivery-file ]]; then
    ((i+1 < ${#args[@]})) || { echo '--delivery-file requiere una ruta.' >&2; exit 2; }
    delivery="${args[i+1]}"
    if [[ "$delivery" == /* ]]; then
      [[ "$delivery" == "$repo_dir/"* ]] || { echo 'Guarda el archivo de entrega dentro del checkout.' >&2; exit 2; }
      args[i+1]="/workspace/${delivery#"$repo_dir/"}"
    fi
  elif [[ "${args[i]}" == --delivery-file=* ]]; then
    echo 'Pasa --delivery-file y su ruta como argumentos separados.' >&2; exit 2
  fi
done
# No host networking, host identity files, host Python, SSH or Git installations.
docker run --rm --network "$network" \
  --env EC2_CONTROL_HOST=engine --env EC2_CONTROL_NETWORK="$network" \
  --env EC2_HOST_UID="$(id -u)" --env EC2_HOST_GID="$(id -g)" \
  --mount "type=bind,src=$repo_dir,dst=/workspace" \
  --mount "type=bind,src=$socket_source,dst=/var/run/docker.sock" \
  --workdir /workspace agil-ec2-runner:local "${args[@]}"
