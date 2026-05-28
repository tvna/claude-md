#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 claude|codex" >&2
  exit 64
fi

agent="$1"
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

"$podman" pull "$image"

if ! "$podman" run --rm --user "$agent" --entrypoint /bin/sh "$image" -lc "getent passwd '$agent' >/dev/null"; then
  echo "image $image does not contain required user $agent after pull" >&2
  exit 69
fi

"$(dirname "$0")/check-stale-agent-container.sh" "$agent" --workspace "$(pwd -P)" --podman "$podman" --rm
