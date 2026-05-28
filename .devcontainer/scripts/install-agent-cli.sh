#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 claude|codex" >&2
  exit 64
fi

case "$1" in
  claude)
    package="claude-cli"
    binary="claude"
    ;;
  codex)
    package="codex-cli"
    binary="codex"
    ;;
  *)
    echo "unsupported agent: $1" >&2
    exit 64
    ;;
esac

if [[ "$(id -u)" -eq 0 ]]; then
  sudo_command=()
else
  sudo_command=(sudo)
fi

out_path="$(nix build --no-link --print-out-paths ".#${package}")"
"${sudo_command[@]}" ln -sf "${out_path}/bin/${binary}" "/usr/local/bin/${binary}"
"/usr/local/bin/${binary}" --version
