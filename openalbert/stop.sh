#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Also stop STT if its profile has since been disabled in the environment.
exec "$script_dir/compose.sh" --profile '*' stop
