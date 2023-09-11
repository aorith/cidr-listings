#!/usr/bin/env bash
cd "$(dirname -- "$0")" || exit 1
set -eu -o pipefail

[[ -e ./env ]] || {
  echo "Please copy 'env-example' as 'env' and modify it."
  exit 1
}
source env

timeout 60 docker network create cidrs 2>/dev/null || true

docker run --rm --detach --name postgres \
  --net cidrs \
  -p 127.0.0.1:"$DB_PORT":5432 \
  -e POSTGRES_USER="$DB_USERNAME" \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" \
  -e POSTGRES_DB="$DB_NAME" \
  -v "$(realpath -- "${PWD}/data")":/var/lib/postgresql/data \
  postgres:15
