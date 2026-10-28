#!/bin/sh
set -eu
umask 077

mkdir -p /run/sshd
exec /usr/sbin/sshd -D -e
