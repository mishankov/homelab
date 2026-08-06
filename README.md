# Homelab

## ELK

### First start (installation)

```shell
docker compose -f compose.yml -f elk/compose.yml -f elk/compose.install.yml up --exit-code-from setup-elk setup-elk
```

Stop after `setup-elk` service finishes

### Regular start

```shell
docker compose -f compose.yml -f elk/compose.yml up
```

## Kafka

```shell
docker compose -f compose.yml -f kafka/compose.yml up
```

## PostgreSQL

```shell
docker compose -f compose.yml -f pg/compose.yml up
```
