#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$script_dir"

compose() {
    docker compose --env-file .env --env-file pi.env -f compose.yaml "$@"
}

# Run for a new/empty storage directory or a changed S3_BUCKET, not on startup.
# Existing buckets and objects are preserved by mc mb --ignore-existing.
compose up -d --no-build --wait --wait-timeout 120 minio
compose run --rm --no-deps minio-init
