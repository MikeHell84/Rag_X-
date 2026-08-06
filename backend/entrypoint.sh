#!/bin/sh
set -e

echo "[entrypoint] Iniciando comando: $@"
exec "$@"
