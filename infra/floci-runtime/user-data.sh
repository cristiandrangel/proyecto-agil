#!/bin/sh
set -eu
# Exercise the real Floci UserData path. Guest image starts Docker on every boot.
i=0
until docker info >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -lt 120 ] || exit 1
  sleep 1
done
install -d -m 700 /srv/proyecto-agil
printf 'Floci UserData completed\n' > /srv/proyecto-agil/user-data-ready
