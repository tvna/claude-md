#!/usr/bin/env sh
set -eu

# Bake the selected agent Nix devShell closure into the image at build time so
# the first runtime `nix develop .#<agent>` no longer realises the closure from
# cache.nixos.org (~23s, the dominant container-create cost; see #1491, #1471).
#
# `@devcontainers/cli build` does not run lifecycle hooks, so the closure cannot
# be warmed by the postCreateCommand at build time -- it must be realised here,
# inside a Feature layer that runs as root during the image build. The workspace
# is NOT mounted during Feature install, so the flake files are staged into this
# Feature's own directory by the publish workflow and copied next to this script.

agent_shell="${AGENTSHELL:-claude}"
case "$agent_shell" in
  claude | codex) ;;
  *)
    echo "nix-warm-agent: unsupported agentShell: $agent_shell" >&2
    exit 64
    ;;
esac

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

# Resolve the `nix` binary installed by the `nix` Feature. Its profile.d scripts
# are sourced only by login/interactive shells, so source them explicitly here
# and add the default profile bin to PATH as a fallback.
for profile in \
  /etc/profile.d/nix.sh \
  /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh \
  /nix/var/nix/profiles/default/etc/profile.d/nix.sh
do
  if [ -r "$profile" ]; then
    # shellcheck disable=SC1090,SC1091
    . "$profile"
  fi
done
case ":${PATH}:" in
  *:/nix/var/nix/profiles/default/bin:*) ;;
  *) PATH="/nix/var/nix/profiles/default/bin:${PATH}"; export PATH ;;
esac

if ! command -v nix >/dev/null 2>&1; then
  echo "nix-warm-agent: nix not on PATH after sourcing the nix profile" >&2
  exit 69
fi

# Stage the flake into a root-owned, NON-git directory. Using the `path:` flake
# ref forces Nix's plain-path evaluator instead of the git-tree evaluator, which
# sidesteps the libgit2 "dubious ownership" error the runtime git+file fetch hits
# (#1471). The flake has no git+file/self input, so nothing else needs the tree.
work="/opt/nix-warm-agent"
rm -rf "$work"
mkdir -p "$work"
for f in flake.nix flake.lock pyproject.toml; do
  if [ ! -f "$script_dir/$f" ]; then
    echo "nix-warm-agent: missing staged flake file: $f" >&2
    exit 65
  fi
  cp "$script_dir/$f" "$work/$f"
done

# Realise and leave the selected agent devShell closure in /nix/store. The store
# paths persist in the image independently of $work, so the staged copy is
# removed afterwards to keep the layer to just the closure. The experimental
# features are passed explicitly in case this non-login shell did not pick up
# the Feature's /etc/nix/nix.conf.
nix develop "path:${work}#${agent_shell}" \
  --extra-experimental-features "nix-command flakes" \
  --accept-flake-config \
  --command true

rm -rf "$work"

echo "nix-warm-agent: baked .#${agent_shell} devShell closure"
