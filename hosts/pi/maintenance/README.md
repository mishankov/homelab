# Scheduled Docker cleanup

The system timer runs `docker system prune --force --filter until=168h` every
Sunday between 04:00 and approximately 04:30 Europe/Moscow. `Persistent=true`
catches up a missed run after the Pi comes back online. The service starts Docker
if needed and always targets the local Unix socket.

This removes stopped containers, unused networks, dangling images and unused
build cache. There is no `--all` or `--volumes`: tagged images and volumes are
kept. Bind-mounted application data is not removed. No separate image or builder
prune timer is needed.

The age filter for containers, images and networks refers to **creation time**,
not when they became unused. An old container stopped just before cleanup can
be removed, including completed Compose init containers. Their writable layers
and Docker logs are then lost; Compose can recreate the containers. Running
containers are not removed. Cache eviction is handled by Docker's builder.
See the [Docker command reference](https://docs.docker.com/reference/cli/docker/system/prune/).

## Install or update

Run on the Pi from the repository root:

```sh
sudo install -m 644 hosts/pi/maintenance/homelab-docker-prune.service /etc/systemd/system/
sudo install -m 644 hosts/pi/maintenance/homelab-docker-prune.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/homelab-docker-prune.service /etc/systemd/system/homelab-docker-prune.timer
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-docker-prune.timer
systemctl list-timers --all homelab-docker-prune.timer
```

Enabling the timer schedules cleanup; it does not explicitly start the service.
A previously installed persistent timer may run immediately to catch up.

## Inspect, run manually, or disable

```sh
systemctl status homelab-docker-prune.timer
journalctl -u homelab-docker-prune.service --no-pager -n 100
docker system df

# Run the same cleanup immediately, including deletion of eligible objects:
sudo systemctl start homelab-docker-prune.service

# Stop future scheduled runs (an already running cleanup is not cancelled):
sudo systemctl disable --now homelab-docker-prune.timer
```

Successful oneshot services return to `inactive (dead)` after completion; check
`systemctl show homelab-docker-prune.service -p Result -p ExecMainStatus` and the
journal for the outcome. Docker reports deleted objects and reclaimed space in
the service journal. A timer remaining active does not prove its last cleanup
succeeded.
