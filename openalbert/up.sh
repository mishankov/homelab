#!/bin/sh
set -eu

# Run install.sh once to prepare SSH keys and data-directory permissions first.
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml build computer
exec docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml up -d --no-build
