#!/bin/sh
set -eu

if [ "$(uname -s)" != Linux ]; then
    echo "Run this installer on the Linux host (Pi)." >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(id -u)" -eq 0 ]; then
    exec "$script_dir/installer/install-computer.sh"
fi
exec sudo "$script_dir/installer/install-computer.sh"
