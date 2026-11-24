# LLM Meter on foreign-server

The dashboard and API are served over HTTPS at the IP in the private
`LLM_METER_ADDRESS` setting. Caddy obtains and renews a Let's Encrypt IP
certificate using the `shortlived` ACME profile.
Keep inbound TCP ports 80 and 443 reachable for HTTPS and certificate validation.
UDP 443 serves HTTP/3. Caddy connects to LLM Meter on the Compose network.

## Dashboard token

Run this from your laptop to retrieve the dashboard login token over SSH:

```sh
ssh -T foreign-server 'sed -n "s/^DASHBOARD_TOKEN=//p" "$HOME/.local/state/llm-meter/docker.env"'
```

On macOS, append `| pbcopy` to copy it directly to the clipboard.

## Deploy

Use Docker Engine with the Compose plugin on `foreign-server`. The private
`~/.local/state/llm-meter/docker.env` file must have mode `0600` and contain
`DASHBOARD_TOKEN` and `LLM_METER_ADDRESS`. Set `LLM_METER_ADDRESS` to the bare IP
without a scheme or port. Reuse the existing dashboard token during upgrades.

From the repository root, copy the deployment files to the server:

```sh
ssh foreign-server 'mkdir -p ~/homelab/foreign-server'
rsync -av foreign-server/compose.yaml foreign-server/Caddyfile foreign-server/README.md \
  foreign-server:homelab/foreign-server/
```

On the server, keep the existing Docker volume named `llm-proxy-data`. For a
fresh deployment, create it first with `docker volume create llm-proxy-data`.
When upgrading from LLM Proxy, stop the old container and make a consistent
SQLite backup of `llm-proxy.db` as `llm-meter.db` in that volume before starting
LLM Meter. Keep the old database and deployment files for rollback.

```sh
cd ~/homelab/foreign-server
docker compose --env-file ~/.local/state/llm-meter/docker.env config --quiet
docker compose --env-file ~/.local/state/llm-meter/docker.env up -d --wait
meter_address=$(sed -n 's/^LLM_METER_ADDRESS=//p' ~/.local/state/llm-meter/docker.env)
curl --fail "https://$meter_address/healthz"
```

The direct API routes are `/v1` and `/antigravity`.
Direct clients send `X-LLM-Meter-Key` alongside their upstream credentials.
Relays upload usage to `/api/usage/events`, including
[Codex and OpenCode telemetry](../README.md#macos-harness-telemetry).
Issue new `llmm_...` keys for clients and relays after an upgrade from LLM
Proxy. The `caddy-data` volume
holds Caddy's ACME account and certificates across container recreation.

## Roll back the LLM Meter migration

Stop LLM Meter and Caddy, restore the saved Compose and Caddy files, and start
the previous LLM Proxy release against `llm-proxy.db`. Keep `llm-meter.db`
separately if the new service has already recorded usage.
