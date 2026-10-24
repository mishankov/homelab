#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
state_dir=${OPENALBERT_STATE_DIR:-"$HOME/openalbert"}
cache_dir="$script_dir/.upstream"

if [ ! -f "$cache_dir/current" ]; then
    echo "Run $script_dir/sync.py first to download upstream configuration." >&2
    exit 1
fi
revision=$(cat "$cache_dir/current")
if ! printf '%s\n' "$revision" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$'; then
    echo "Invalid upstream revision; run $script_dir/sync.py again." >&2
    exit 1
fi
if [ ! -f "$state_dir/.env" ]; then
    echo "Missing $state_dir/.env; see $script_dir/README.md." >&2
    exit 1
fi

# An old .env image tag must not mix new Compose with old application images.
export OPENALBERT_IMAGE_TAG="sha-$revision"
exec docker compose \
    --project-name openalbert \
    --project-directory "$state_dir" \
    --env-file "$state_dir/.env" \
    --env-file "$script_dir/pi.env" \
    -f "$cache_dir/$revision/compose.yaml" \
    -f "$script_dir/compose.override.yaml" \
    "$@"
