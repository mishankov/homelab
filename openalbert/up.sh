#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Pull everything successfully before changing any running service.
"$script_dir/compose.sh" pull
exec "$script_dir/compose.sh" up -d
