#!/usr/bin/env bash
cd "$(dirname -- "$0")" || exit 1
set -eu -o pipefail

[[ -e ./env ]] || {
  echo "Please copy 'env-example' as 'env' and modify it."
  exit 1
}

timeout 60 docker network create cidrs 2>/dev/null || true

docker run --rm --detach --name cidrlistings \
  -p 127.0.0.1:8000:8000 \
  --net cidrs \
  --log-driver=journald \
  --log-opt tag="{{.Name}}/{{.ID}}" \
  --env-file "$PWD/env" \
  ghcr.io/aorith/cidr-listings:latest
