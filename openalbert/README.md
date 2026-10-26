# OpenAlbert on Raspberry Pi

Run from this repository's root **on the Pi**, like the other service scripts:

```sh
./openalbert/up.sh
./openalbert/stop.sh
```

Each script runs one Docker Compose command using the existing
`~/openalbert/compose.yaml`, the only Compose file used by this deployment.
`pi.env` supplies non-secret Pi settings; credentials and the deployed image tag
come from `~/openalbert/.env`. Pi settings override the private file; exported
shell variables take precedence. No file is sourced as a shell script.

The installed file defines project `openalbert`, and relative data mounts stay
under `~/openalbert/container_data`. The Compose file and application revision
are not committed here.

The installed Compose file publishes the inspector as `192.168.1.31:8080:8080`,
available at <http://192.168.1.31:8080/inspect/> on the trusted LAN without
authentication. `INSPECTOR_PUBLIC_URL` only controls links, not port bindings.
Other service ports retain their installed bindings. PostgreSQL uses
host port `15432`. Stop includes every profile so it also stops local STT after
its profile has been disabled.

For validation and status, use Compose directly:

```sh
docker compose --env-file "$HOME/openalbert/.env" --env-file openalbert/pi.env -f "$HOME/openalbert/compose.yaml" config -q
docker compose --env-file "$HOME/openalbert/.env" --env-file openalbert/pi.env -f "$HOME/openalbert/compose.yaml" ps
```

## Updating OpenAlbert

Follow the upstream [deployment and backup instructions](https://github.com/mishankov/OpenAlbert/blob/master/docs/deployment.md).
Back up the private installation, download `compose.yaml` and `.env.release.example`
from the chosen published revision, and set the matching `OPENALBERT_IMAGE_TAG` in
`~/openalbert/.env`. Compare the example for new settings; preserve existing keys
and credentials. Preserve the Pi's inspector binding `192.168.1.31:8080:8080`
when replacing the installed Compose file; upstream defaults to loopback.
Then validate, explicitly pull the images, and start:

```sh
docker compose --env-file "$HOME/openalbert/.env" --env-file openalbert/pi.env -f "$HOME/openalbert/compose.yaml" config -q
docker compose --env-file "$HOME/openalbert/.env" --env-file openalbert/pi.env -f "$HOME/openalbert/compose.yaml" pull
./openalbert/up.sh
```

Normal start and stop use the installed configuration and do not download a newer
Compose file. Use these commands consistently: plain `docker compose` in the
installation directory does not apply homelab's `pi.env` settings.
For a new installation, prepare `~/openalbert` using the upstream instructions
first. The scripts leave the private `.env` and upstream Compose file in place.
