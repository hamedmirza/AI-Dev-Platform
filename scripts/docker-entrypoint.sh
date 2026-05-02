#!/bin/sh
set -e
# When running as root (container default), ensure /data is writable by appuser then drop privileges.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data/workspace /data/backups
  chown -R appuser:appuser /data /app
  exec gosu appuser "$@"
fi
exec "$@"
