#!/usr/bin/env bash
set -euo pipefail
umask 077

if (( EUID != 0 )); then
    echo "Run openalbert/install.sh to prepare keys and ownership with sudo." >&2
    exit 1
fi
if ! command -v ssh-keygen > /dev/null 2>&1; then
    echo "Install openssh-client on this host before running the installer." >&2
    exit 1
fi

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPUTER_DIR="$SCRIPT_DIR/../container_data/computer"
readonly CLIENT_KEY="$COMPUTER_DIR/client/id_ed25519"
readonly SERVER_KEY="$COMPUTER_DIR/server/ssh_host_ed25519_key"
readonly AUTHORIZED_KEYS="$COMPUTER_DIR/server/authorized_keys"

echo "Prepare computer directories"
install -d -o 10001 -g 10001 -m 0700 "$COMPUTER_DIR/client"
install -d -o 0 -g 0 -m 0755 "$COMPUTER_DIR/server"
install -d -o 10001 -g 10001 -m 0755 "$COMPUTER_DIR/home" "$COMPUTER_DIR/workspace"

echo "Prepare SSH keys"
if [[ ! -f "$CLIENT_KEY" ]]; then
    ssh-keygen -q -t ed25519 -N '' -f "$CLIENT_KEY"
fi
if [[ ! -f "$SERVER_KEY" ]]; then
    ssh-keygen -q -t ed25519 -N '' -f "$SERVER_KEY"
fi

echo "Set SSH key permissions"
chown 10001:10001 "$CLIENT_KEY"
chown 0:0 "$SERVER_KEY"
chmod 0600 "$CLIENT_KEY" "$SERVER_KEY"
if [[ -f "$CLIENT_KEY.pub" ]]; then
    chown 10001:10001 "$CLIENT_KEY.pub"
    chmod 0644 "$CLIENT_KEY.pub"
fi

# Validate existing unencrypted keys before changing authorized_keys.
client_public_key=$(ssh-keygen -y -P '' -f "$CLIENT_KEY")
ssh-keygen -y -P '' -f "$SERVER_KEY" > /dev/null
touch "$AUTHORIZED_KEYS"
if ! grep -Fqx -- "$client_public_key" "$AUTHORIZED_KEYS"; then
    if [[ -s "$AUTHORIZED_KEYS" ]]; then
        printf '\n' >> "$AUTHORIZED_KEYS"
    fi
    printf '%s\n' "$client_public_key" >> "$AUTHORIZED_KEYS"
fi

chown 0:0 "$AUTHORIZED_KEYS"
chmod 0644 "$AUTHORIZED_KEYS"

echo "Computer SSH access is ready"
