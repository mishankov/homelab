#!/bin/sh
set -eu
umask 077
: "${COMPUTER_AUTHORIZED_KEY:?Set the public SSH key for this instance}"
mkdir -p /data/home /data/workspace /data/ssh /run/sshd
if [ ! -e /data/home/.railway-initialized ]; then
    cp -an /etc/albert-home/. /data/home/
    chown 10001:10001 /data/home /data/workspace
    touch /data/home/.railway-initialized
fi
chmod 0755 /data /data/ssh
printf '%s\n' "$COMPUTER_AUTHORIZED_KEY" > /data/ssh/authorized_keys
chmod 0644 /data/ssh/authorized_keys
if [ ! -f /data/ssh/ssh_host_ed25519_key ]; then
    ssh-keygen -q -t ed25519 -N '' -f /data/ssh/ssh_host_ed25519_key
fi
chmod 0600 /data/ssh/ssh_host_ed25519_key
unset COMPUTER_AUTHORIZED_KEY
exec /usr/sbin/sshd -D -e
