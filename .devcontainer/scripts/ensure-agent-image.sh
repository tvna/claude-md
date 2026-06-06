#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 claude|codex [--platform linux/amd64|linux/arm64]" >&2
}

agent=""
platform=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)
      if [[ $# -lt 2 ]]; then
        usage
        exit 64
      fi
      platform="$2"
      shift 2
      ;;
    -*)
      echo "unknown argument: $1" >&2
      usage
      exit 64
      ;;
    *)
      if [[ -n "$agent" ]]; then
        echo "unexpected argument: $1" >&2
        usage
        exit 64
      fi
      agent="$1"
      shift
      ;;
  esac
done

if [[ -z "$agent" ]]; then
  usage
  exit 64
fi

case "$agent" in
  claude | codex) ;;
  *)
    echo "unsupported agent: $agent" >&2
    exit 64
    ;;
esac

podman="${DEVCONTAINER_PODMAN:-/opt/podman/bin/podman}"
if [[ ! -x "$podman" ]]; then
  echo "podman is not executable: $podman" >&2
  exit 69
fi

config=".devcontainer/${agent}/devcontainer.json"
if [[ ! -f "$config" ]]; then
  echo "missing devcontainer config: $config" >&2
  exit 66
fi

image="$(
  python3 - "$config" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    print(json.load(config_file)["image"])
PY
)"

if [[ "$image" == *":main" || "$image" == *":latest" ]]; then
  echo "devcontainer image must not use a mutable tag: $image" >&2
  exit 69
fi

if [[ "$image" != *@sha256:* && ! "$image" =~ :[0-9a-f]{40}$ ]]; then
  echo "devcontainer image must use a commit SHA tag or digest: $image" >&2
  exit 69
fi

platform_args=()
if [[ -n "$platform" ]]; then
  platform_args=(--platform "$platform")
fi

# A multi-platform manifest auto-resolves the host arch when --platform is
# omitted. When it is requested, podman pull fails if the manifest lacks that
# architecture -- the pull is itself the verification, so an amd64-only publish
# (the hazard the runbook warns about) loud-fails here instead of silently
# falling back.
if ! "$podman" pull "${platform_args[@]}" "$image"; then
  if [[ -n "$platform" ]]; then
    echo "failed to pull $image for platform $platform; the manifest may not include that architecture. Confirm a multi-platform publish includes $platform before opening this overlay (docs/runbooks/devcontainers.md)." >&2
  fi
  exit 69
fi

if ! "$podman" run --rm "${platform_args[@]}" --user "$agent" --entrypoint /bin/sh "$image" -lc "getent passwd '$agent' >/dev/null"; then
  echo "image $image does not contain required user $agent after pull" >&2
  exit 69
fi

"$(dirname "$0")/check-stale-agent-container.sh" "$agent" --workspace "$(pwd -P)" --podman "$podman" --rm
