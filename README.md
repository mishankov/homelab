# Homelab

## LLM Meter (foreign-server)

[LLM Meter and Caddy](foreign-server/README.md) run together on `foreign-server`.

## LLM Meter relays

The macOS desktop relay collects OpenTelemetry from Codex and OpenCode. The
[OpenAlbert Pi stack](openalbert/README.md#configuration) meters model requests
through its own `usage-only` relay. Both relays upload usage to the LLM Meter
dashboard on `foreign-server`.

Before starting the relays, upgrade `foreign-server` to an LLM Meter release
that supports `POST /api/usage/events`. The old LLM Proxy server cannot ingest
relay usage. The renamed server opens `llm-meter.db`, so the server upgrade must
preserve the existing `llm-proxy.db` data.

### macOS harness telemetry

In the [LLM Meter Relay desktop app](https://github.com/mishankov/llm-meter/tree/main/desktop),
enter the dashboard's HTTPS origin and a workstation client key. Enable
**OpenTelemetry** at `127.0.0.1:4318`, keep **Model proxy** off, and leave the
local TLS fields blank for HTTP on loopback. Save and start the relay. The
relay uploads usage to the dashboard over HTTPS and stores its client key in
macOS Keychain.

#### Codex

Remove the old `openai_base_url` override if it points to the retired `/codex`
proxy. Merge the settings below into `~/.codex/config.toml` and start a fresh
Codex session.

```toml
[otel]
exporter = { otlp-http = { endpoint = "http://127.0.0.1:4318/v1/logs", protocol = "json" } }
log_user_prompt = false
log_agent_responses = false
log_guardian_assessments = false
log_sse_deltas = false
tool_result.max_bytes = 0
```

#### OpenCode

Remove the old `openai` and `opencode-go` `baseURL` overrides from
`~/.config/opencode/opencode.jsonc` if they point to the retired proxy routes.
Run these commands to configure the shared background server used by the CLI.

```sh
opencode service set env OTEL_EXPORTER_OTLP_ENDPOINT http://127.0.0.1:4318
opencode service start
```

OpenCode saves the setting in `~/.config/opencode/service.json` and appends the
signal paths to the OTLP origin. With **Server URL** blank, T3 Code launches its
own OpenCode server. Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`
in the T3 Code OpenCode provider's environment as well. When T3 Code connects
to the shared server through **Server URL**, the shared server's setting is
sufficient.

#### Verify usage

Send a short prompt from each harness, then check **Usage** in the LLM Meter
dashboard for `/codex/telemetry` and `/opencode/telemetry` records under the
workstation client. OpenCode can take a few seconds to export a batch.

See the [LLM Meter OpenTelemetry guide](https://github.com/mishankov/llm-meter/blob/main/docs/configuration.md#53-opentelemetry)
for other harnesses and exporter settings.

## OpenAlbert (Raspberry Pi)

OpenAlbert on `mishankov@pi` is managed separately from the local homelab stack.
Its Compose file, Pi settings and Ubuntu computer image are maintained in
[openalbert](openalbert/README.md).

```shell
./openalbert/up.sh
./openalbert/stop.sh
```

Run these commands **on the Pi**, from this repository's root. Compose, private
settings and data live under `openalbert/`; see its README for migrating the
existing installation.

The repository skill [update-openalbert](.agents/skills/update-openalbert/SKILL.md)
updates the running Pi installation with published images, preserves its settings
and computer, and verifies the deployment. Invoke it with `$update-openalbert`.

### OpenAlbert source

The upstream [OpenAlbert](https://github.com/mishankov/OpenAlbert) source is
available as a Git submodule in [`vendor/openalbert`](vendor/openalbert) for
code and documentation reference. To populate it after cloning this repository:

```shell
git submodule update --init --recursive
```

The submodule is pinned to a commit. To advance it to the latest upstream
`master` and record the new revision in this repository:

```shell
git submodule update --init --remote vendor/openalbert
git add vendor/openalbert
```

Updating this reference checkout does not update the deployed Docker images.

## Camunda

```shell
./camunda/up.sh
./camunda/stop.sh
```

Operate is available at http://localhost:8083 and uses the default `demo` / `demo`
credentials. Zeebe's gRPC gateway is available at `localhost:26500`. Camunda and
Kibana share Elasticsearch 8.14.3, available locally at `localhost:9200`.

## ELK

```shell
./elk/up.sh
./elk/stop.sh
```

## Kafka

```shell
./kafka/up.sh
./kafka/stop.sh
```

## PostgreSQL

```shell
./pg/up.sh
./pg/stop.sh
```

## Pega

```shell
./pega/install.sh
./pega/up.sh
./pega/stop.sh
```

## Hosts

[Raspberry Pi](hosts/pi/README.md): hardware, USB boot, networking, AmneziaWG,
recovery notes and a read-only status command:

```shell
./hosts/pi/status.sh
```
