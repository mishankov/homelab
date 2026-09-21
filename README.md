# Homelab

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
