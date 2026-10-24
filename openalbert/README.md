# OpenAlbert on Raspberry Pi

This directory records the host configuration for `ssh mishankov@pi` without
maintaining a copy of OpenAlbert's service definitions. The existing deployment
uses Compose project `openalbert`, private settings in `~/openalbert/.env`, and
bind-mounted data in `~/openalbert/container_data`. Commands must run **on the Pi**;
they use the local Docker daemon and do not SSH automatically.

The main [Compose file](https://github.com/mishankov/OpenAlbert/blob/master/compose.yaml)
and [environment template](https://github.com/mishankov/OpenAlbert/blob/master/.env.release.example)
are downloaded together from upstream by `sync.py`. Neither is committed here.
`pi.env` contains only non-secret host choices; `compose.override.yaml` replaces
the inspector port binding. OpenAlbert remains a separate Compose project rather
than being included in the root homelab stack, avoiding service and port collisions.

## Use the existing installation

Requirements: Python 3.8+, outbound HTTPS to GitHub/GHCR, Docker, and Docker Compose
**2.24.4+** (`!override` support). Docker access is required for management commands.
The Pi currently has Compose 5.6.1. Clone this repository on the Pi and run commands
from its root; do not put the checkout inside `~/openalbert/container_data`.

```sh
# Download the latest upstream configuration. Does not pull images or restart anything.
./openalbert/sync.py

# Validate without printing the rendered secrets; inspect current services.
./openalbert/compose.sh config -q
./openalbert/compose.sh ps

# Explicitly pull images and apply the selected upstream revision.
./openalbert/up.sh

# Stop all services, including optional STT, keeping containers and data.
./openalbert/stop.sh
```

For an initial adoption with the same application versions as the running Pi,
pass the full SHA from its private `.env` `OPENALBERT_IMAGE_TAG` (without `sha-`)
to `sync.py`. This value is intentionally not recorded in Git.

`sync.py [ref]` accepts a branch, tag, or commit; its default `master` is resolved
to a concrete SHA on every invocation. That selection is cached locally in the
ignored `.upstream/` directory. Normal start/stop/status commands use the cache
without contacting GitHub or selecting a newer release. Compose and the five
OpenAlbert image tags use the same SHA, even if the private `.env` contains an older
tag. Wait for that upstream revision's entire publication workflow to succeed
before deploying. `up.sh` stops if any image pull fails, before changing containers.
Upstream service definitions and third-party image versions can change on sync;
new homelab commits are needed only when the Pi's own settings need to change.

The order of settings is upstream defaults, the private `.env`, then tracked
`pi.env`; exported shell variables take Docker Compose's usual precedence. The
application image tag is always set from the selected revision. Keep tokens,
Telegram IDs, database/S3 credentials and other private settings in the existing
`.env`. Do not source that file as a shell script. `config` without `-q` and
`config --environment` print secrets, so do not paste their output into Git or PRs.

The inspector is available on the trusted LAN at
<http://192.168.1.31:8080/inspect/>. It has no authentication; the override binds
only to that Pi address. Other service ports retain upstream's loopback bindings;
PostgreSQL uses host port `15432`. Adjust `pi.env` if the Pi's address changes.

All relative upstream bind mounts are resolved against `~/openalbert`, regardless
of the checkout location or current working directory. The wrappers reuse those
data paths without relocating them and leave the existing `.env` and Compose file
in place. Applying an upstream update can still migrate data inside containers.
`OPENALBERT_STATE_DIR=/absolute/path` can select another installation directory.
Once adopted, use these wrappers consistently: plain `docker compose` in the old
installation directory still reads its old Compose file and image tag.

## New installation or additional upstream settings

After `sync.py`, copy the downloaded template to the private installation directory:

```sh
mkdir -p ~/openalbert
revision=$(cat openalbert/.upstream/current)
cp "openalbert/.upstream/$revision/.env.release.example" ~/openalbert/.env
chmod 600 ~/openalbert/.env
```

Only copy for a **new installation**; never overwrite the existing Pi `.env`.
Fill all required credentials, Telegram access IDs and LLM keys. Use a URL-safe
PostgreSQL password. Compare the cached template with the private `.env` when
upstream introduces new options; sync does not merge or overwrite private values.

Prepare memory permissions as required by upstream, then validate and start:

```sh
mkdir -p ~/openalbert/container_data/knowledge
sudo chown 10001:10001 ~/openalbert/container_data/knowledge
./openalbert/compose.sh config -q
./openalbert/up.sh
```

## Backups and updates

Configuration in Git does not back up credentials, PostgreSQL/Temporal state,
MinIO attachments, Markdown memory, logs or STT weights. Follow the upstream
[backup and restore instructions](https://github.com/mishankov/OpenAlbert/blob/master/docs/deployment.md#резервная-копия-и-восстановление).
For a consistent cold backup, stop services with `./openalbert/stop.sh`, archive
the entire private installation with numeric file owners, and also save this
checkout's `openalbert/.upstream/` cache and the homelab commit. Resume with
`./openalbert/up.sh`. Store the backup privately off the Pi.

Before updating, keep the previous cached SHA, back up the data, review upstream's
deployment notes and compare environment templates. Then run `sync.py [ref]`,
`compose.sh config -q` and `up.sh`. A previous SHA can be selected with `sync.py SHA`,
but returning to old images after data migrations may require restoring the
matching backup; changing the tag alone cannot undo migrations. If disabling
local STT, first run `./openalbert/compose.sh --profile local-stt stop stt`, then
change `pi.env` and apply the configuration.

## Verification

```sh
python3 -m unittest discover -s openalbert/tests -v
```

These checks require the Docker Compose CLI but no running Docker daemon. They
use temporary paths, a small upstream fixture and dummy credentials; they never
start containers or read the real installation's secrets.
