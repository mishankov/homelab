# OpenAlbert on Raspberry Pi

The tracked `compose.yaml` is based on OpenAlbert
[`0f0aa6c`](https://github.com/mishankov/OpenAlbert/tree/0f0aa6ccdd63b23d3093567a92ed354726a718fd).
It runs Albert and its Ubuntu computer in the same `openalbert` Compose project.
Albert uses the published `master` images; only the computer is built locally.

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
See upstream's [computer protocol](https://github.com/mishankov/OpenAlbert/blob/0f0aa6ccdd63b23d3093567a92ed354726a718fd/docs/computer.md).

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

## Backup status

The optional upstream `backup` service remains behind its profile. `pi.env`
enables only `local-stt`; do not enable `backup` for this configuration yet.
The upstream controller expects images that can be restored from registry digests;
it does not save the locally built computer image. A local Docker digest alone
does not make that image available from a registry during restoration.

Upstream fixed recovery for service names containing hyphens in `0f0aa6c`,
including `log-gateway` and `temporal-ui`; that fix is included in the published
`master` images verified for this configuration. An existing failed run's
`resume.json` is not changed by checking out these repository files.

Until local-image restoration is covered, use a consistent cold copy: stop the
whole stack, copy `.env`, `pi.env`, `compose.yaml`, `computer/`, private backup
settings and all `container_data/` with ownership and permissions preserved,
then start it again. The computer's home, workspace, keys and runner state are in
those bind mounts. Its system is rebuilt from the Dockerfile; installed packages
outside the mounts are not part of the data copy. A restored installation needs
the backed-up published image digests and a new local computer build.

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
