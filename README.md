# Homelab

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
