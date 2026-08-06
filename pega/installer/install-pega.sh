#!/usr/bin/env bash

set -euo pipefail

readonly DB_HOST="postgresql"
readonly DB_PORT="5432"
readonly ADMIN_DATABASE="postgres"
readonly PEGA_DATABASE="pega"
readonly ADMIN_USER="postgres"
readonly ADMIN_PASSWORD="postgres"
readonly PEGA_USER="pega"
readonly PEGA_PASSWORD="rules"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "Install PostgreSQL client"
apt-get update
apt-get install --yes --no-install-recommends postgresql-client

export PGPASSWORD="${ADMIN_PASSWORD}"

echo "Create Pega database"
if [[ "$(psql \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${ADMIN_USER}" \
    --dbname="${ADMIN_DATABASE}" \
    --tuples-only \
    --no-align \
    --set=ON_ERROR_STOP=1 \
    --command="SELECT 1 FROM pg_database WHERE datname = '${PEGA_DATABASE}';")" != "1" ]]; then
    psql \
        --host="${DB_HOST}" \
        --port="${DB_PORT}" \
        --username="${ADMIN_USER}" \
        --dbname="${ADMIN_DATABASE}" \
        --set=ON_ERROR_STOP=1 \
        --command="CREATE DATABASE ${PEGA_DATABASE};"
fi

echo "Configure PL/Java for Java 21"
psql \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${ADMIN_USER}" \
    --dbname="${ADMIN_DATABASE}" \
    --set=ON_ERROR_STOP=1 \
    --command="ALTER DATABASE ${PEGA_DATABASE} SET pljava.vmoptions TO '-Djava.security.manager=allow';"

echo "Enable PL/Java in Pega database"
psql \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${ADMIN_USER}" \
    --dbname="${PEGA_DATABASE}" \
    --set=ON_ERROR_STOP=1 \
    --command="CREATE EXTENSION pljava;"

echo "Prepare Pega database"
psql \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${ADMIN_USER}" \
    --dbname="${PEGA_DATABASE}" \
    --set=ON_ERROR_STOP=1 \
    --file="${SCRIPT_DIR}/init_pega.sql"

echo "Run Pega install script"
cd /distr/scripts

./install.sh \
    --driverJAR /postgresql-42.2.14.jar \
    --driverClass org.postgresql.Driver \
    --dbType postgres \
    --dbURL "jdbc:postgresql://${DB_HOST}:${DB_PORT}/${PEGA_DATABASE}" \
    --dbUser "${PEGA_USER}" \
    --dbPassword "${PEGA_PASSWORD}" \
    --adminPassword install \
    --rulesSchema rules \
    --dataSchema data
