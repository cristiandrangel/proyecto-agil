#!/bin/sh
set -eu
# The runner needs the Docker socket, but generated private files should belong
# to the invoking Unix user. Windows bind mounts use ACLs instead of these IDs.
finish() {
  if [ -n "${EC2_HOST_UID:-}" ] && [ -d /workspace/.local/ec2-emulation ]; then
    chown -R "$EC2_HOST_UID:${EC2_HOST_GID:-$EC2_HOST_UID}" /workspace/.local/ec2-emulation
  fi
}
trap finish EXIT
# Git protects against foreign repository ownership; trust only this explicit bind.
git config --global --add safe.directory /workspace
# CRLF checkouts must not affect the shell scripts sent into Linux guests.
python3 -m scripts.ec2_emulation "$@"
