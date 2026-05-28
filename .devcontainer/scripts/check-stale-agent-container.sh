#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: check-stale-agent-container.sh claude|codex [--workspace PATH] [--config PATH] [--podman PATH] [--rm]

Detect Dev Containers instances that are labelled for this workspace and
config but do not contain the required agent user. Without --rm, this
script only reports stale containers and exits non-zero when any are found.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 64
fi

agent="$1"
shift

case "$agent" in
  claude | codex)
    ;;
  *)
    echo "unsupported agent: $agent" >&2
    exit 64
    ;;
esac

workspace="$(pwd -P)"
config=""
podman="${DEVCONTAINER_PODMAN:-/opt/podman/bin/podman}"
remove=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      if [[ $# -lt 2 ]]; then
        usage
        exit 64
      fi
      workspace="$2"
      shift 2
      ;;
    --config)
      if [[ $# -lt 2 ]]; then
        usage
        exit 64
      fi
      config="$2"
      shift 2
      ;;
    --podman)
      if [[ $# -lt 2 ]]; then
        usage
        exit 64
      fi
      podman="$2"
      shift 2
      ;;
    --rm)
      remove=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

if [[ ! -d "$workspace" ]]; then
  echo "workspace does not exist: $workspace" >&2
  exit 66
fi

workspace="$(cd "$workspace" && pwd -P)"
if [[ -z "$config" ]]; then
  config="$workspace/.devcontainer/$agent/devcontainer.json"
fi

if [[ ! -f "$config" ]]; then
  echo "config does not exist: $config" >&2
  exit 66
fi

if [[ ! -x "$podman" ]]; then
  echo "podman is not executable: $podman" >&2
  exit 69
fi

container_output="$(
  "$podman" ps -q -a \
    --filter "label=devcontainer.local_folder=$workspace" \
    --filter "label=devcontainer.config_file=$config"
)"

containers=()
if [[ -n "$container_output" ]]; then
  mapfile -t containers <<<"$container_output"
fi

if [[ "${#containers[@]}" -eq 0 ]]; then
  echo "OK: no existing devcontainer containers for $agent at $workspace"
  exit 0
fi

stale=()
for container in "${containers[@]}"; do
  if "$podman" start "$container" >/dev/null 2>&1; then
    if "$podman" exec --user root "$container" sh -lc "getent passwd '$agent' >/dev/null 2>&1 || grep -E '^$agent:' /etc/passwd >/dev/null 2>&1" >/dev/null 2>&1; then
      echo "OK: $container contains user $agent"
    else
      echo "STALE: $container is missing user $agent"
      stale+=("$container")
    fi
  else
    echo "STALE: $container could not be started for inspection"
    stale+=("$container")
  fi
done

if [[ "${#stale[@]}" -eq 0 ]]; then
  exit 0
fi

if [[ "$remove" -eq 0 ]]; then
  echo "Run again with --rm to remove stale containers after confirming the workspace and config above." >&2
  exit 2
fi

for container in "${stale[@]}"; do
  "$podman" rm -f "$container"
  echo "removed stale container: $container"
done
