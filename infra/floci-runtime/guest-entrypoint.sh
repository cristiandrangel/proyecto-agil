#!/bin/sh
set -eu
mkdir -p /run/sshd
rm -f /var/run/docker.pid
# Only an internal Unix socket; neither a host socket nor a TCP Docker API.
dockerd --host=unix:///var/run/docker.sock --storage-driver=overlay2 \
  >> /var/log/agil-dockerd.log 2>&1 &
/usr/sbin/sshd
exec "$@"
