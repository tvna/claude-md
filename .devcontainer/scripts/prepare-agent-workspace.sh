#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 claude|codex" >&2
  exit 64
fi

agent="$1"
case "$agent" in
  claude | codex)
    ;;
  *)
    echo "unsupported agent: $agent" >&2
    exit 64
    ;;
esac

if ! id "$agent" >/dev/null 2>&1; then
  echo "missing required user: $agent" >&2
  exit 69
fi

if [[ "$(id -un)" != "$agent" ]]; then
  echo "expected to run as $agent, got $(id -un)" >&2
  exit 77
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "expected $agent to use uid 0 for rootless Podman workspace writes" >&2
  exit 77
fi

write_check="$PWD/.devcontainer-write-check.$$"
touch "$write_check"
rm -f "$write_check"
