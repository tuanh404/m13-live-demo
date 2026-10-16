#!/usr/bin/env bash
# Reversible management of this demo project only; never publishes or deletes volumes.
set -euo pipefail
action=${1:?Use validate/build/start/stop/rollback}
envfile=${2:?Pass generated compose.env}
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
envfile=$(realpath -- "$envfile")
case "$envfile" in "$repo"/data/*/compose.env) ;; *) echo 'Use a generated data deployment env' >&2; exit 2;; esac
compose=(docker compose --env-file "$envfile" -f "$repo/deployment/mvp/compose.yml")
"${compose[@]}" config --quiet
case "$action" in
  validate) ;;
  build) "${compose[@]}" build api ;;
  start) "${compose[@]}" up -d --no-build ;;
  stop) "${compose[@]}" stop ;;
  rollback)
    image=${3:?Pass a previously tested local image tag or digest; back up data first}
    case "$image" in m13-demo:*|sha256:*) ;; *) echo 'Use a locally tested m13-demo image' >&2; exit 2;; esac
    docker image inspect --format '{{.Id}}' "$image" >/dev/null
    M13_IMAGE="$image" "${compose[@]}" up -d --no-build api
    ;;
  *) echo 'Use validate/build/start/stop/rollback' >&2; exit 2 ;;
esac
