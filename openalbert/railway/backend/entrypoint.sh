#!/bin/sh
set -eu
umask 077
: "${COMPUTER_SSH_PRIVATE_KEY:?Set the private key for this instance}"
mkdir -p /data/knowledge /data/computer
printf '%s\n' "$COMPUTER_SSH_PRIVATE_KEY" > /data/computer/id_ed25519
chmod 0600 /data/computer/id_ed25519
chown 10001:10001 /data /data/knowledge /data/computer /data/computer/id_ed25519
unset COMPUTER_SSH_PRIVATE_KEY
ssh_host=${COMPUTER_SSH_ADDRESS%:*}
ssh_port=${COMPUTER_SSH_ADDRESS##*:}
attempt=0
until ssh -i /data/computer/id_ed25519 -p "$ssh_port" \
    -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/data/computer/known_hosts \
    "${COMPUTER_SSH_USER:-albert}@$ssh_host" \
    'test "$(id -u)" = 10001 && command -v python3 >/dev/null && test -w "$HOME"' \
    2>/tmp/computer-ssh-check.err; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 20 ]; then
        cat /tmp/computer-ssh-check.err >&2
        echo 'Computer SSH readiness check failed' >&2
        exit 1
    fi
    sleep 1
done
echo 'Computer SSH readiness check passed'
export HOME=/home/openalbert USER=openalbert LOGNAME=openalbert
exec su-exec openalbert /usr/local/bin/openalbert
