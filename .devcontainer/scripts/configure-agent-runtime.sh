#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_dir="${script_dir}/../config"

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

if [[ "$(id -u)" -eq 0 ]]; then
  sudo_command=()
else
  sudo_command=(sudo)
fi

install_nix_binary() {
  local package="$1"
  local binary="$2"
  local out_path

  out_path="$(nix build --no-link --print-out-paths ".#${package}")"
  "${sudo_command[@]}" ln -sf "${out_path}/bin/${binary}" "/usr/local/bin/${binary}"
  "/usr/local/bin/${binary}" --version
}

install_nix_binary gh-cli gh
install_nix_binary pinned-uv uv
install_nix_binary python-runtime python3
# GitHub MCP server binary for the Docker-less stdio launch path (#1063):
# scripts/mcp_github_launch.sh execs this when no Docker daemon is present.
install_nix_binary github-mcp-server github-mcp-server
if [[ ! -x "/usr/local/bin/apm" ]]; then
  install_nix_binary apm-cli apm
else
  echo "apm already present: $(/usr/local/bin/apm --version)"
fi
if [[ "$agent" == "codex" ]]; then
  install_nix_binary bubblewrap bwrap
fi

home_dir="$(getent passwd "$agent" | cut -d: -f6)"
if [[ -z "$home_dir" ]]; then
  echo "unable to resolve home for $agent" >&2
  exit 69
fi

"${sudo_command[@]}" mkdir -p "$home_dir/.config/gh"

case "$agent" in
  claude)
    "${sudo_command[@]}" mkdir -p "$home_dir/.claude"
    "${sudo_command[@]}" cp "${config_dir}/claude/settings.json" "$home_dir/.claude/settings.json"
    ;;
  codex)
    "${sudo_command[@]}" mkdir -p "$home_dir/.codex"
    "${sudo_command[@]}" cp "${config_dir}/codex/config.toml" "$home_dir/.codex/config.toml"
    ;;
esac

"${sudo_command[@]}" chown -R "$agent:$agent" "$home_dir/.config" "$home_dir/.$agent"

"${sudo_command[@]}" cp "${config_dir}/profile.d/claude-md-nix-path.sh" /etc/profile.d/claude-md-nix-path.sh
"${sudo_command[@]}" cp "${config_dir}/profile.d/claude-md-agent-prompt.sh" /etc/profile.d/claude-md-agent-prompt.sh

echo "configured devcontainer runtime for $agent"
