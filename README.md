# Homelab

## ELK

### First start (installation)

```shell
docker compose up --exit-code-from setup-elk setup-elk
```

### Regular start

```shell
docker compose --profile elk up -d
```

## Kafka

```shell
docker compose --profile kafka up -d
```

## PostgreSQL

```shell
docker compose --profile pg up -d
```

## Pega

### Install

```shell
docker compose up --exit-code-from pega-installer pega-installer
```

### Regular start

```shell
docker compose --profile pega up -d
```
