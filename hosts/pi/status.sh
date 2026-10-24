#!/bin/sh
# Read-only host overview over SSH. Does not read application or VPN credentials.
set -eu

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [ssh-destination] (default: mishankov@pi)" >&2
    exit 2
fi

exec ssh -o BatchMode=yes -o ConnectTimeout=10 -- "${1:-mishankov@pi}" 'sh -s' <<'REMOTE'
set -u
section() { printf '\n%s\n' "$1"; }
run() {
    "$@" || printf 'Unavailable or failed (exit %s): %s\n' "$?" "$*" >&2
}

section 'System'
run uname -srmo
run uptime
run free -h
run timedatectl show -p Timezone -p NTPSynchronized

section 'Storage and USB link speeds'
run lsblk -o NAME,SIZE,FSTYPE,FSAVAIL,FSUSE%,MOUNTPOINTS,MODEL
run df -hT / /boot/firmware
run lsusb -t

section 'Raspberry Pi temperature, power flags and boot order'
run vcgencmd measure_temp
run vcgencmd get_throttled
run vcgencmd bootloader_config

section 'Network and VPN routing (interface state does not prove a healthy tunnel)'
run ip -brief address
run ip -4 route show table main
run ip rule show
run ip -4 route show table 51820
run systemctl show awg-quick@awg0.service openalbert-vpn-boot-rollback.timer \
    -p Id -p ActiveState -p SubState -p UnitFileState

section 'Failed services and scheduled maintenance'
run systemctl --failed --no-pager
run systemctl list-timers --all --no-pager

section 'Listening TCP ports'
run ss -lnt

section 'Containers'
run docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
REMOTE
