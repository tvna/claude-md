#!/usr/bin/env bash
# Wire up SSH commit signing in ~/.gitconfig for the named agent user.
# Skips silently when no SSH public key is present in ~/.ssh -- signing is
# optional; the devcontainer remains fully functional without it.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <agent> <home_dir>" >&2
  exit 64
fi

agent="$1"
home_dir="$2"
ssh_dir="${home_dir}/.ssh/devcontainer-signing-keys"

if [[ "$(id -u)" -eq 0 ]]; then
  sudo_command=()
else
  sudo_command=(sudo)
fi

signing_key=""
for k in "${ssh_dir}/id_ed25519.pub" "${ssh_dir}/id_rsa.pub" "${ssh_dir}/id_ecdsa.pub"; do
  if [[ -f "$k" ]]; then
    signing_key="$k"
    break
  fi
done

if [[ -z "$signing_key" ]]; then
  echo "INFO: no SSH public key found in ${ssh_dir} -- git signing not configured" >&2
  exit 0
fi

gitconfig="${home_dir}/.gitconfig"

"${sudo_command[@]}" git config --file "${gitconfig}" gpg.format ssh
"${sudo_command[@]}" git config --file "${gitconfig}" user.signingKey "${signing_key}"
"${sudo_command[@]}" git config --file "${gitconfig}" commit.gpgsign true
"${sudo_command[@]}" chown "${agent}:${agent}" "${gitconfig}"

echo "configured git SSH commit signing: key=${signing_key}"
