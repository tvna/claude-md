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

home_dir="$(getent passwd "$agent" | cut -d: -f6)"
if [[ -z "$home_dir" ]]; then
  echo "unable to resolve home for $agent" >&2
  exit 69
fi

"${sudo_command[@]}" mkdir -p "$home_dir/.config/gh"

case "$agent" in
  claude)
    "${sudo_command[@]}" mkdir -p "$home_dir/.claude"
    "${sudo_command[@]}" tee "$home_dir/.claude/settings.json" >/dev/null <<'JSON'
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "mcp__github__*"
    ]
  }
}
JSON
    ;;
  codex)
    "${sudo_command[@]}" mkdir -p "$home_dir/.codex"
    "${sudo_command[@]}" tee "$home_dir/.codex/config.toml" >/dev/null <<'TOML'
# Devcontainer-local defaults. This file lives on a container-engine
# named volume and is not read by the macOS/container host.
approval_policy = "never"

[permissions]
allow = ["bash", "mcp__github__*"]
TOML
    ;;
esac

"${sudo_command[@]}" chown -R "$agent:$agent" "$home_dir/.config" "$home_dir/.$agent"

"${sudo_command[@]}" tee /etc/profile.d/claude-md-nix-path.sh >/dev/null <<'BASH'
# Make binaries linked from Nix-built packages available in plain terminals.
case ":${PATH}:" in
  *:/usr/local/bin:*) ;;
  *) export PATH="/usr/local/bin:${PATH}" ;;
esac
BASH

"${sudo_command[@]}" tee /etc/profile.d/claude-md-agent-prompt.sh >/dev/null <<'BASH'
# Short, devcontainer-local prompt: agent:repo(branch)$
__claude_md_git_branch() {
  git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null
}

__claude_md_agent_prompt() {
  local agent="${AGENT_CONTAINER:-agent}"
  local dir="${PWD##*/}"
  local branch
  branch="$(__claude_md_git_branch)"
  if [ -n "$branch" ]; then
    printf '%s:%s(%s)\\$ ' "$agent" "$dir" "$branch"
  else
    printf '%s:%s\\$ ' "$agent" "$dir"
  fi
}

case "$-" in
  *i*) PS1='$(__claude_md_agent_prompt)' ;;
esac
BASH

echo "configured devcontainer runtime for $agent"
