#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

if [[ "$(uname -s)" != Linux ]]; then
  printf '%s\n' 'La entrega EC2 emulada está validada para Linux con Docker Engine.' >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Se requieren Docker Engine y Docker Compose v2.' >&2
  exit 2
fi
docker compose version >/dev/null
docker_endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
if [[ "$docker_endpoint" != unix:///var/run/docker.sock || ! -S /var/run/docker.sock || -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
  printf '%s\n' 'Usa el contexto local de Docker Engine (unix:///var/run/docker.sock), sin DOCKER_HOST ni DOCKER_CONTEXT definidos.' >&2
  exit 2
fi

docker build -t agil-ec2-runner:local \
  -f infra/floci-runtime/Dockerfile.runner infra/floci-runtime

if [[ "$#" -eq 0 ]]; then
  set -- up
fi

# The helper controls only the dedicated outer Compose project. Floci receives
# that project's isolated socket; neither Floci nor the guest sees the host socket.
# Host identity files allow OpenSSH to resolve the invoking UID without root-owned
# private files or additional Python/SSH/Git installations on the evaluator's PC.
docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  --group-add "$(stat -c '%g' /var/run/docker.sock)" \
  --mount "type=bind,src=$repo_dir,dst=$repo_dir" \
  --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
  --mount type=bind,src=/etc/passwd,dst=/etc/passwd,readonly \
  --mount type=bind,src=/etc/group,dst=/etc/group,readonly \
  --workdir "$repo_dir" \
  agil-ec2-runner:local "$@"
