# Host VPN: AmneziaWG

The Pi already uses `awg-quick@awg0.service`, enabled at boot and observed as
`active (exited)`, which is normal for its `Type=oneshot` / `RemainAfterExit=yes`
unit. That state only means the setup command completed; it does not prove a
recent handshake or working Internet access.

[awg-quick@awg0.service.d/override.conf](awg-quick@awg0.service.d/override.conf)
matches `/etc/systemd/system/awg-quick@awg0.service.d/override.conf` on the host.
It selects `/usr/local/bin/amneziawg-go` as the userspace implementation and retries
failed setup after 10 seconds. `Restart=on-failure` is not tunnel health monitoring
and does not automatically restart a tunnel whose peer stops responding.

## Installed components

- [`amneziawg-go`](https://github.com/amnezia-vpn/amneziawg-go), module version
  `v3.1.20260828`, source commit `b5928efb6ca19f0153958460c3d141f04abc5c2e`.
  The installed ARM64 binary's Go build metadata reports Go `1.25.0` and an
  unmodified source tree. Executable: `/usr/local/bin/amneziawg-go`.
- [`amneziawg-tools`](https://github.com/amnezia-vpn/amneziawg-tools), source
  checkout `ee0f0a9aa34ff0a0da4b3433b9512781cfe02843`, with version header
  `3.1.20260812`. The checkout under
  `~/.local/src/openalbert-vpn/amneziawg-tools` had no tracked changes.
  Installed commands: `/usr/bin/awg` and `/usr/bin/awg-quick`, with the systemd
  template at `/usr/lib/systemd/system/awg-quick@.service`. The installed commands
  match that checkout's compiled `src/wg` and `src/wg-quick/linux.bash` respectively.
- These commands are installed outside dpkg package ownership. `apt upgrade`
  therefore does not manage their updates.
- Required host facilities include TUN, `iproute2`, firewall tools and `openresolv`.
  The installed `awg-quick` reads `awg0` from
  `/etc/amnezia/amneziawg/awg0.conf`, a protected directory that was not read.

No private key, peer endpoint or VPN profile is stored here. Back up the original
profile privately before replacing the machine; it cannot be reconstructed from
the interface addresses and routing table.

## Manual recovery on a replacement machine

First restore LAN/SSH access and keep a console available. Obtain the source
revisions above from their official repositories and follow their build/install
instructions. Build `amneziawg-go` for ARM64; install it at the path used by the
drop-in. Build/install `amneziawg-tools` with `WITH_WGQUICK=yes` and
`WITH_SYSTEMDUNITS=yes` to include the helper and service. Restore the original
private `awg0.conf` with root ownership and mode `0600` in its protected directory.
Do not regenerate the profile from a generic WireGuard example: AmneziaWG options
must match the server.

From this repository on the replacement Pi, install the existing public drop-in:

```sh
sudo install -d -m 0755 /etc/systemd/system/awg-quick@awg0.service.d
sudo install -m 0644 hosts/pi/vpn/awg-quick@awg0.service.d/override.conf \
    /etc/systemd/system/awg-quick@awg0.service.d/override.conf
sudo systemctl daemon-reload
```

These commands do not start the tunnel. Test starting it from the console before
enabling boot startup; confirm LAN SSH still works, external traffic follows the
intended route, DNS resolves, and the peer has a recent handshake. Verify the
application's outbound traffic separately. Do not run recovery commands against
the working Pi just to adopt this directory.

## Existing rescue artifacts

The host also has `openalbert-vpn-boot-rollback.service` and `.timer`. The timer
is **disabled and inactive**, with `OnActiveSec=5min`; its descriptions mark it
as a temporary VPN boot test rescue. It is not an active failover system.
It invokes `/usr/local/sbin/openalbert-vpn-rollback`, a root-only script which was
not inspected. Related backups exist in `/var/backups/openalbert-vpn`.

The rescue units and an invented replacement script are deliberately not installed
by this repository. Inspect the original script and its saved network state with
root access before deciding whether to preserve, replace or remove that mechanism.
