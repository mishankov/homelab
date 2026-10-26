# OpenAlbert on Raspberry Pi

Run from this repository's root **on the Pi**, like the other service scripts:

```sh
./openalbert/up.sh
./openalbert/stop.sh
```

Each script runs one Docker Compose command. [compose.yml](compose.yml) includes
the existing `~/openalbert/compose.yaml` with the local port override.
`pi.env` supplies non-secret Pi settings; credentials and the deployed image tag
come from `~/openalbert/.env`. Pi settings override the private file; exported
shell variables take precedence. No file is sourced as a shell script.

The Compose project stays `openalbert`, and relative data mounts stay under
`~/openalbert/container_data`. `OPENALBERT_STATE_DIR=/absolute/path` selects another
installation. The main Compose file and application revision are not committed
here. Docker Compose **2.24.4+** is required for the port override.

The inspector is at <http://192.168.1.31:8080/inspect/> on the trusted LAN, without
authentication; other service ports retain upstream bindings. PostgreSQL uses
host port `15432`. Stop includes every profile so it also stops local STT after
its profile has been disabled.

For validation and status, use Compose directly:

```sh
docker compose --env-file openalbert/pi.env -f openalbert/compose.yml config -q
docker compose --env-file openalbert/pi.env -f openalbert/compose.yml ps
```

## Updating OpenAlbert

Follow the upstream [deployment and backup instructions](https://github.com/mishankov/OpenAlbert/blob/master/docs/deployment.md).
Back up the private installation, download `compose.yaml` and `.env.release.example`
from the chosen published revision, and set the matching `OPENALBERT_IMAGE_TAG` in
`~/openalbert/.env`. Compare the example for new settings; preserve existing keys
and credentials. Then validate, explicitly pull the images, and start:

```sh
docker compose --env-file openalbert/pi.env -f openalbert/compose.yml config -q
docker compose --env-file openalbert/pi.env -f openalbert/compose.yml pull
./openalbert/up.sh
```

Normal start and stop use the installed configuration and do not download a newer
Compose file. Use these commands consistently: plain `docker compose` in the
installation directory does not apply homelab's Pi settings or port override.
For a new installation, prepare `~/openalbert` using the upstream instructions
first. The scripts leave the private `.env` and upstream Compose file in place.

## Verification

```sh
python3 -m unittest discover -s openalbert/tests -v
```

Tests render Compose with temporary paths and dummy credentials. They require
the Compose CLI, without a running Docker daemon, and never read the live `.env`.
