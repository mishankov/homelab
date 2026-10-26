# OpenAlbert on Raspberry Pi

Run from this repository's root **on the Pi**, like the other service scripts:

```sh
./openalbert/up.sh
./openalbert/stop.sh
```

Both commands use relative paths within this checkout:

- `openalbert/compose.yaml`: the upstream Compose file, downloaded separately.
- `openalbert/.env`: private credentials and the deployed image tag.
- `openalbert/pi.env`: tracked non-secret Pi settings, overriding the private file.
- `openalbert/container_data/`: persistent data, relative to the Compose file.

Only the scripts and non-secret settings are committed. The downloaded Compose
file, private `.env` and data are ignored by Git. There is one Compose file and
no download helper. Exported shell variables take Compose's usual precedence.
Stop includes all profiles, including local STT if its profile has been disabled.

## Existing Pi installation

The existing deployment must be migrated before using these commands. Stop it,
copy its Compose file, private `.env` and all data into this checkout, preserving
file ownership. For example, on the Pi, set these to the actual absolute paths:

```sh
old_dir=/path/to/current/openalbert
repo_dir=/path/to/homelab

(cd "$old_dir" && docker compose --profile '*' stop)
cp "$old_dir/compose.yaml" "$repo_dir/openalbert/compose.yaml"
install -m 600 "$old_dir/.env" "$repo_dir/openalbert/.env"
sudo rsync -a --numeric-ids "$old_dir/container_data/" "$repo_dir/openalbert/container_data/"
cd "$repo_dir"
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml config -q
./openalbert/up.sh
```

Use an empty destination for the data copy. Keep the old installation as a backup
until the migrated application has been verified. The Compose file's project
name must remain `openalbert` so `up` recreates the existing project's containers
with the new bind-mount paths. Do not start both copies against the same bot.

The Pi's existing Compose file publishes the inspector as
`192.168.1.31:8080:8080`. Preserve that binding for trusted-LAN access at
<http://192.168.1.31:8080/inspect/> without authentication.
`INSPECTOR_PUBLIC_URL` only controls links, not port bindings. PostgreSQL uses
host port `15432` through `pi.env`.

## New installations and updates

Follow upstream's [deployment and backup instructions](https://github.com/mishankov/OpenAlbert/blob/master/docs/deployment.md),
using this checkout's `openalbert/` as the installation directory. Download
`compose.yaml` from the chosen published revision into `openalbert/compose.yaml`;
for a new installation, copy its `.env.release.example` to `openalbert/.env`,
fill the required credentials and prepare data permissions as upstream describes.

For updates, back up the installation first, use the matching image tag in
`openalbert/.env`, compare the new environment template without overwriting
credentials, and preserve the inspector binding when replacing Compose.
Validate, explicitly pull images, then start:

```sh
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml config -q
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml pull
./openalbert/up.sh
```

Normal start and stop do not download a newer Compose file. To inspect services:

```sh
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml ps
```
