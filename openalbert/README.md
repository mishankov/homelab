# OpenAlbert on Raspberry Pi

The tracked `compose.yaml` is based on OpenAlbert's
[upstream Compose](https://github.com/mishankov/OpenAlbert/blob/master/deploy/compose.yaml).
It runs Albert and its Ubuntu computer in the same `openalbert` Compose project.
Albert uses the published `master` images; only the computer is built locally.

For local code and documentation reference, see the upstream source submodule
in [`../vendor/openalbert`](../vendor/openalbert). Initialization and update
commands are in the [repository README](../README.md#openalbert-source).

Run from this repository's root **on the Pi**:

```sh
./openalbert/up.sh
./openalbert/stop.sh
```

`up.sh` builds the computer image before starting the stack with `--no-build`.
Run `install.sh` explicitly to prepare SSH keys and directory permissions before
the first start. `up.sh` does not generate keys or pull Albert images. `stop.sh` includes all profiles, including disabled STT and backup profiles.
Both scripts use the private `.env` followed by tracked `pi.env`. Exported shell
variables take Compose's usual precedence.

## Configuration

- `compose.yaml`: tracked service definitions, including `computer`.
- `.env`: private credentials; copy `.env.example` for a new installation.
- `pi.env`: the `master` image tag, model, STT, SSH and other non-secret Pi settings.
- `install.sh` and `installer/install-computer.sh`: explicit computer installation.
- `computer/`: Dockerfile, SSH configuration and SSH server entrypoint for Ubuntu 26.10.
- `container_data/`: persistent application and computer data; ignored by Git.
- `backup-config/`: private backup settings and S3 credentials; ignored by Git.

The inspector is bound to `192.168.1.31:8080` for trusted-LAN access at
<http://192.168.1.31:8080/inspect/> without authentication. `INSPECTOR_PUBLIC_URL`
controls links, not port bindings. PostgreSQL binds to loopback port `15432`.

## Computer

The image `homelab-openalbert-computer:ubuntu26.10` is built from the official
`ubuntu:26.10` base. It includes SSH, Bash, Python, Git, curl and passwordless sudo
for UID 10001 (`albert`). It contains no Albert runner or application credentials.
The published Albert image installs and updates its matching runner over SSH.
See upstream's [computer protocol](https://github.com/mishankov/OpenAlbert/blob/master/docs/computer.md).

Albert connects as `albert@computer:22` on the private `computer` network, using
`/data/computer/id_ed25519`. The SSH port is not published on the host. The client
key is mounted into Albert read-only; the computer receives only the authorized
public key and server key. Password authentication is disabled. The new Albert
SSH adapter no longer uses `known_hosts` or `COMPUTER_SSH_KNOWN_HOSTS_FILE`.

The existing paths remain unchanged:

| Host path under `openalbert/` | Computer path |
| --- | --- |
| `container_data/computer/home` | `/home/albert` |
| `container_data/computer/workspace` | `/workspace` |
| `container_data/computer/server` | `/etc/openalbert-ssh` (read-only) |

The new runner defaults to `/home/albert/.openalbert/workspace`, which persists
inside the home mount. Existing files under `/workspace` remain available by
specifying that absolute working directory. Runner versions and execution records
also persist in `/home/albert/.openalbert`.

Recreating the computer starts a fresh system from this Dockerfile. Packages and
system changes made inside the old container are intentionally not migrated.
Files in the home and workspace mounts and SSH keys are retained. Add required
system packages to the Dockerfile to keep them across future recreations.

To refresh the Ubuntu base explicitly before the next start:

```sh
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml build --pull computer
```

## Computer installation

Following the existing Pega installation layout, `install.sh` is the host-side
entry point and `installer/install-computer.sh` contains the installation steps.
Run explicitly from the repository root, after preparing private `.env` and
restoring any existing data, before the first `up.sh`:

```sh
./openalbert/install.sh
```

The outer script runs the installer directly on the Linux host, elevating through
sudo when needed. The host needs Bash and `ssh-keygen` from `openssh-client`.
Installation works without Docker or a running computer and does not build images
or start the stack; `up.sh` builds the computer separately.
The installer creates missing client/server keys, authorizes the client key,
and sets directory ownership and key permissions for UID 10001. Existing keys,
other `authorized_keys` entries, home files and workspace files are preserved;
repeating the installation does not rotate keys or duplicate the client key.

There is no Compose init service. Installation is never called by `up.sh` or the
computer entrypoint; the entrypoint only starts the SSH server. Before an update,
stop the computer before rerunning installation to avoid changing permissions
while it is using its files.

## Existing Pi installation

Prepare the checkout before starting it. Back up the existing private settings,
Compose and data first. Stop the existing stack, including the running legacy
computer and backup controller. Do not run both installations against the same bot.
For the current layout, on the Pi:

```sh
old_dir=/home/mishankov/openalbert
repo_dir=/absolute/path/to/homelab

(cd "$old_dir" && docker compose --env-file .env --env-file pi.env --profile '*' stop)
install -m 600 "$old_dir/.env" "$repo_dir/openalbert/.env"
sudo rsync -a --numeric-ids "$old_dir/container_data/" "$repo_dir/openalbert/container_data/"
sudo rsync -a --numeric-ids "$old_dir/backup-config/" "$repo_dir/openalbert/backup-config/"
cd "$repo_dir"
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml config -q
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml pull --ignore-buildable
```

Run `./openalbert/install.sh`, then `./openalbert/up.sh`.

Use an empty destination for the data copy. Keep this repository's tracked
`compose.yaml` and `pi.env`; do not overwrite them with the old installation's
files. The project name remains `openalbert`, so Compose recreates the existing
containers with the new bind-mount paths. The computer starts from the new Ubuntu
image, without a snapshot of the old system layer. Keep the original data copy
until application, SSH and file access have been checked.

## Updates

The `master` tag is recorded in `pi.env`, overriding a legacy tag in private
`.env`. An explicit `pull` fetches the current published `master` images; `up.sh`
starts the images already available locally. For a future Albert update, compare
upstream's `deploy/compose.yaml` and environment template with the tracked files here.
Preserve this deployment's computer service, network, mounts and inspector
binding. Do not replace the tracked Compose wholesale with upstream's standalone
file, which no longer defines a computer.

Back up the installation, validate, explicitly pull published images, then start:

```sh
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml config -q
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml pull --ignore-buildable
./openalbert/up.sh
```

The computer has `pull_policy: never`; it uses the local image.
To inspect the deployment:

```sh
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml ps
```

## Scheduled data backups

`pi.env` enables the `backup` profile together with `local-stt`. Prepare private
`backup-config/config.json` and `backup-config/s3.json` using upstream's
[backup instructions](https://github.com/mishankov/OpenAlbert/blob/master/docs/deployment.md#резервная-копия-и-восстановление).
Set `enabled: true` in the private config. The current Pi schedule is 02:30
Europe/Moscow with 14-day retention and a 60-second notice before stopping services.
For a new installation without backup settings, temporarily run with
`COMPOSE_PROFILES=local-stt` until these files are ready.

The controller stops the running application services for a consistent cold copy,
restarts them after creating the encrypted archive, uploads it to external S3 and
checks the remote inventory. It keeps its own container running throughout.
The archive contains PostgreSQL, MinIO, knowledge, `.env`, Compose, and all of
`container_data/computer`: SSH keys, home, workspace, runner files and executions.
It does not contain the computer image or writable system layer. Rebuilding the
computer from the repository Dockerfile is the intended recovery procedure;
programs installed interactively outside the data mounts are not backed up.

The current controller still requires local images to have a Docker RepoDigest.
The Pi's Docker 29 containerd image store supplies one for the built computer;
that local digest is recorded for provenance but is not a registry download.

Request a backup and inspect progress from the repository root:

```sh
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml exec backup albert-backup request
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml logs --tail=50 backup
```

### Restore data with a fresh computer image

Use the upstream restore command with the offline age identity to decrypt a copy
into a new empty directory. Restore writes data and image overrides without
starting services. Keep the offline identity and S3 credentials private.

In a fresh checkout on the recovery host, copy the restored `.env`,
`container_data/` and `compose.backup-images.json` into `openalbert/`, preserving
owners and permissions. Review `pi.env` and the inspector binding for the new
host. Recreate private `backup-config/` separately; it is not included in the
archive. Do not start a second bot against the same Telegram token.

Then, from the checkout root:

```sh
# Preserve registry digests for application services; omit the local computer digest.
python3 openalbert/prepare-restore.py openalbert
./openalbert/install.sh
# Keep scheduled backups stopped until the restored installation is verified.
export COMPOSE_PROFILES=local-stt
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml -f openalbert/compose.restore-images.json pull --ignore-buildable
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml -f openalbert/compose.restore-images.json build computer
docker compose --env-file openalbert/.env --env-file openalbert/pi.env -f openalbert/compose.yaml -f openalbert/compose.restore-images.json up -d --no-build
unset COMPOSE_PROFILES
```

`prepare-restore.py` leaves the original backup override untouched and writes
`compose.restore-images.json`, removing only the computer's image override.
The other services use the exact backed-up registry digests. The computer uses
its normal local tag and build context, together with the restored data mounts.
Use the restore overrides for the first start; routine `up.sh` uses current
`master` tags. Verify the restored data and SSH access before enabling the backup
profile again.

## Local checks

```sh
python3 openalbert/check-computer.py
```

This validates all Compose profiles with synthetic credentials, builds a test
image, runs the actual host installer in an isolated Linux test container with
synthetic data in disposable volumes, and starts only a disposable computer.
The test container has no Docker CLI or socket. It checks that all published image tags
are `master`, Ubuntu/Python versions, SSH, sudo, ownership and permissions,
repeatable installation without key rotation or replacement of existing
`authorized_keys` entries, and persistence of keys, home, workspace and runner
files after container recreation. It removes its containers, network,
volumes and test image afterwards. It does not use private `.env`, real data,
Telegram, an LLM or the Pi.
