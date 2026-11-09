#!/bin/sh
set -eu

# Run install.sh and install-storage.sh once before the first start.
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml build computer
exec docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml up -d --no-build
