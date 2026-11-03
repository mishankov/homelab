# Independent OpenAlbert on Railway

Project: <https://railway.com/project/20fce16c-c34e-435d-b8d2-49bb8aae5cb3>

This is a separate Telegram bot with a new LLM key, independent data, and a
separate computer. It uses OpenCode Go and `gpt-6-luna`. Telegram access
is restricted by this instance’s allowed-user settings. The Pi is separate.

`TELEGRAM_ALLOW_BOT_MESSAGES=true` accepts bot participants in allowed groups,
including `-5430276608`, through the same handling as human participants. Telegram's
Bot-to-Bot Communication Mode must also be enabled, with Group Privacy disabled
or group admin rights granted for receiving ordinary bot messages.
Temporary progress status messages appear only in private chats. Groups and
group topics keep progress internal; the typing indicator remains enabled.

## Services and storage

- `Postgres`: Railway’s PostgreSQL 18 template, with SSL setup and a persistent
  database volume. Albert uses the default `railway` database. Temporal creates
  its own `temporal` and `temporal_visibility` databases on the same server.
- `openalbert-files`: a native Railway S3-compatible bucket in EU West (`ams`). The
  backend references its bucket name and credentials through Railway variables.
  The existing S3 client passed file-read, metadata, and conditional-write tests.
- `temporal`: Temporal Server; its durable state lives in PostgreSQL. Its small
  Docker context supplies the dynamic configuration.
- `computer`: Ubuntu 26.10 with SSH, Python, Bash, Git, curl, and sudo. Its 4 GB
  `/data` volume holds the persistent home, workspace, and SSH host keys.
- `openalbert`: the published backend plus a small bootstrap layer. Its 1 GB
  `/data` volume holds knowledge and the computer’s client key. The bootstrap
  fixes volume ownership, checks private SSH access, and runs Albert as UID 10001.

There is no STT service, and all STT variables are empty. The application services
use private networking and one replica in EU West. No public application domain
is configured. The inspector is private because it has no built-in login.

The Pi’s Docker-based backup controller and Docker logging driver do not run
here. Built-in log search is disabled; use Railway logs. Manage database and volume
backups through Railway separately.

Computer home files and workspace files survive redeployments. System packages
installed elsewhere must be added to its Dockerfile to survive recreation.

## Configuration and credentials

`.railway/railway.ts` describes the four services and their volumes, variables,
healthchecks, and placement. Secret values remain in Railway as `preserve()`.
Railway variable references connect Albert and Temporal to native storage.

The native `openalbert-files` bucket is included in the infrastructure specification.
For a fresh installation, create and deploy it in the signed-in Railway dashboard
before configuring the application’s bucket references. Keep its name and region
aligned with the specification.

`railway.py` runs CLI 5.71.0 from this directory using ignored
`.private/settings.json`. Normal commands load only the Railway API token from
its private file. Example local settings, without credential values:

```json
{
  "project": {
    "id": "20fce16c-c34e-435d-b8d2-49bb8aae5cb3",
    "environmentId": "0251efd9-4e4e-4935-b8d3-8550e2f2fe88"
  },
  "files": {
    "RAILWAY_API_TOKEN": "/absolute/path/to/private/railway-token"
  }
}
```

Keep `.private/` out of Git and container build contexts. Application credentials
are already stored in Railway; the wrapper loads only the account API token and
pins commands to this project and production environment.

## Operations

Run from this directory with Node.js 22+ and Python 3:

```sh
npm ci --ignore-scripts
python3 railway.py config plan
python3 railway.py service list --json
python3 railway.py logs --deployment --service openalbert --latest --lines 100
```

After reviewing an infrastructure change:

```sh
python3 railway.py config apply --yes
```

Upload changed Docker contexts individually:

```sh
python3 railway.py up ./computer --path-as-root --service computer --detach
python3 railway.py up ./temporal --path-as-root --service temporal --detach
python3 railway.py up ./backend --path-as-root --service openalbert --detach
```

These commands upload only the selected service directory. Do not upload this
entire directory with `--no-gitignore`. Native PostgreSQL and the bucket have no
local Docker context.

For a fresh setup, provision PostgreSQL and the bucket first, then Temporal and
the computer, then Albert. Keep one Albert replica to avoid competing Telegram
pollers. Review plans carefully before removing services, volumes, or buckets.

The backend Dockerfile pins its published OpenAlbert image digest. To update it,
review upstream changes, update the digest, and upload its Docker context. Its
readiness check validates computer SSH access before Albert starts; Railway then
checks `/healthz` after database, bucket, Telegram commands, Temporal, and browser
initialization.
