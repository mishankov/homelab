# LLM Proxy on foreign-server

The dashboard and API are served at <https://178.104.150.186/>. Caddy obtains and
renews a Let's Encrypt IP certificate using the `shortlived` ACME profile.
Keep inbound TCP ports 80 and 443 reachable for HTTPS and certificate validation.
UDP 443 serves HTTP/3. Caddy connects to LLM Proxy on the Compose network.

## Dashboard token

Run this from your laptop to retrieve the dashboard login token over SSH:

```sh
ssh -T foreign-server 'sed -n "s/^DASHBOARD_TOKEN=//p" "$HOME/.local/state/llm-proxy/docker.env"'
```

On macOS, append `| pbcopy` to copy it directly to the clipboard.

## Deploy

Use Docker Engine with the Compose plugin on `foreign-server`. The private
`~/.local/state/llm-proxy/docker.env` file must contain `DASHBOARD_TOKEN` and have
mode `0600`. Reuse the existing token when migrating the standalone container.

From the repository root, copy the deployment files to the server:

```sh
ssh foreign-server 'mkdir -p ~/homelab/foreign-server'
rsync -av foreign-server/compose.yaml foreign-server/Caddyfile foreign-server/README.md \
  foreign-server:homelab/foreign-server/
```

On the server, keep the existing `llm-proxy-data` volume. For a fresh deployment,
create it first with `docker volume create llm-proxy-data`. To migrate a running
standalone `llm-proxy` container, stop it and back up the volume before starting
Compose. Only one proxy should write to the SQLite database at a time.

```sh
cd ~/homelab/foreign-server
docker compose --env-file ~/.local/state/llm-proxy/docker.env config --quiet
docker compose --env-file ~/.local/state/llm-proxy/docker.env up -d --wait
curl --fail https://178.104.150.186/healthz
```

Use the same HTTPS base for the existing API routes `/v1`, `/backend-api/codex`
and `/opencode-go`. Keep the client's upstream credentials and its
`X-LLM-Proxy-Key` header. The `caddy-data` volume holds Caddy's ACME account and
certificates across container recreation.

## Roll back the standalone migration

If the previous `llm-proxy` container is still present, stop the Compose proxy
before starting it. Both containers use the same data volume.

```sh
cd ~/homelab/foreign-server
docker compose --env-file ~/.local/state/llm-proxy/docker.env stop caddy llm-proxy
docker start llm-proxy
curl --fail http://127.0.0.1:8080/healthz
```
