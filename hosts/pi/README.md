# Raspberry Pi host

Observed over SSH on **2026-10-24**. This directory records the host behind the
containers: boot settings, the custom VPN integration and recovery information.
It does not automatically provision the machine or change running services.

## Inventory

- Raspberry Pi 5 Model B Rev 1.0, ARM64, 8 GB RAM.
- Raspberry Pi OS / Debian 13 (trixie), kernel `6.18.50+rpt-rpi-2712`.
- Samsung SSD 850 EVO 250 GB over USB; `/` is ext4 and `/boot/firmware` is FAT.
  About 14 GB was used and 206 GB available. No SD card was listed.
- The SSD's USB link was **480 Mbit/s**, using the `uas` driver. The USB 3 root
  hubs reported 5000 Mbit/s and no attached devices. Check the physical port and
  adapter before expecting SSD performance; a move to a USB 3 link requires
  physical access and a planned shutdown.
- 2 GB zram swap, with the distribution's zram writeback timer.
- Hostname `pi`, timezone `Europe/Moscow`, NTP synchronized.
- Ethernet `eth0`: DHCP address `192.168.1.31/24`, gateway `192.168.1.1`;
  Wi-Fi is down. No persistent NetworkManager connection files were present.
  A router-side DHCP reservation was not verified.

Run from a local checkout to refresh the operational view:

```sh
./hosts/pi/status.sh
./hosts/pi/status.sh mishankov@192.168.1.31
```

The command uses SSH keys/agent and never asks for sudo. It reports unavailable
commands individually, reads no `.env` or VPN profiles, and prints no process
arguments or service logs. SSH connection failures retain SSH's exit status;
individual diagnostic failures do not abort the remaining checks. This is an
overview, not an automated health verdict.

## Network and services

AmneziaWG `awg0` is enabled at boot, using a userspace binary and policy-routing
table `51820` with a default route through the VPN. The main table retains the
Ethernet default and LAN route. This is host-level routing, not a container-only
VPN. DNS was managed by `resolvconf` with `1.1.1.1` and `1.0.0.1`.
See [VPN recovery](vpn/README.md) for the custom systemd drop-in and build provenance.
The private VPN profile was not read, so its hooks, peers, IPv6 behavior and
kill-switch policy have not been audited.

Docker CE `29.9.2`, containerd `2.4.2` and Compose plugin `5.6.1` are installed
from Docker's Debian `trixie` stable ARM64 repository, using
`/etc/apt/keyrings/docker.asc`. Docker is enabled without local systemd overrides.
The only Compose project observed was `openalbert`, under `~/openalbert`.

Listening TCP ports during inspection:

- SSH: `22` on all addresses.
- RPC portmapper: `111` on all addresses; no NFS server was active and no NFS
  mounts were listed. Installed client components do not establish NAS usage.
- OpenAlbert inspector: `192.168.1.31:8080`.
- Loopback only: PostgreSQL `15432`, Temporal `7233`, Temporal UI `8233`,
  MinIO `9000/9001`, VictoriaLogs `9428`, log gateway `9429`.

The desktop is still active: `graphical.target`, LightDM, Wayland components,
Bluetooth and Avahi. Console tty1 autologin is configured for `mishankov`.
CUPS has enabled socket/path units but its service was inactive; WayVNC control
was enabled but inactive, with no VNC TCP listener observed. These are candidates
for a later headless-host decision if the desktop and peripherals are not needed;
none were disabled during this inventory.

## USB boot and replacing the disk

[bootloader.conf](bootloader.conf) records the observed EEPROM settings.
`BOOT_ORDER=0xf614` tries USB mass storage, then SD, then NVMe, then repeats
(digits are read from right to left). The bootloader build was `2026-09-25`.
The [official bootloader reference](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_ORDER)
describes the modes. Inspect with `vcgencmd bootloader_config`; review changes
manually with `sudo -E rpi-eeprom-config --edit` when recovering a host.

The current root and firmware mounts use disk PARTUUIDs. Do not copy the original
`fstab` or kernel command line onto a newly partitioned disk: use its actual IDs
and keep `/etc/fstab` consistent with `/boot/firmware/cmdline.txt`. Most firmware
settings were distribution defaults and are intentionally not copied here.
Private boot-migration backups exist under `/var/backups/pi-usb-*`; they have not
been inspected or tested as a restore source. Do not flash EEPROM or reboot a
remote recovery attempt without a way to reach the console or recovery media.

## Maintenance and recovery priorities

System timers cover APT maintenance, log rotation, filesystem trim/scrubbing,
dpkg metadata and zram writeback. No user cron or user systemd timers were found,
and no scheduled OpenAlbert backup appeared in the inspected system timers or
readable cron directories. Root's private crontab was not accessible. The presence
of APT timers alone does not verify automatic installation of security updates.

`~/openalbert-pi-migration-*` contains about 1.7 GB of local migration material;
`/var/backups/openalbert-vpn` also exists. These are on the same SSD as the live
data. Their consistency and contents have not been verified, and they do not
provide an off-host backup.

The next useful addition is a recurring **off-host backup with a restore test**:
include OpenAlbert's private `.env`, all application data, the deployed Compose
revision and the private VPN configuration. Choose a destination and retention
before adding a timer; stopping the full application for a cold copy also needs
an agreed maintenance window. This repository stores only public configuration.

For a replacement host: install the 64-bit OS and restore working LAN/SSH first;
configure USB boot for the actual disk; install Docker from its Debian repository;
restore application data with original ownership; then restore the VPN separately
using [its recovery notes](vpn/README.md). Keep the local console/LAN available
while testing routing. Existing OS desktop preferences, machine IDs, disk IDs,
SSH keys and private profiles are not a portable desired configuration.

Some protected files could not be inspected without sudo, including the VPN
profile, rollback script, SSH cloud-init drop-in and private backup directories.
This inventory does not claim a complete configuration or security audit.
