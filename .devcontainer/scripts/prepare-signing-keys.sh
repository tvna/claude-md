#!/usr/bin/env bash
# HOST-side: copy only SSH public keys into ~/.ssh/devcontainer-signing-keys/
# so the devcontainer bind mount never exposes private keys to the agent
# container (whose user runs as UID 0).
# Called from devcontainer initializeCommand; exits 0 even when no keys found.
set -euo pipefail

ssh_dir="${HOME}/.ssh"
signing_dir="${ssh_dir}/devcontainer-signing-keys"

mkdir -p "${signing_dir}"
chmod 700 "${signing_dir}"

copied=0
for pub in "${ssh_dir}/id_ed25519.pub" "${ssh_dir}/id_rsa.pub" "${ssh_dir}/id_ecdsa.pub"; do
  if [[ -f "${pub}" ]]; then
    cp "${pub}" "${signing_dir}/$(basename "${pub}")"
    chmod 644 "${signing_dir}/$(basename "${pub}")"
    copied=$((copied + 1))
  fi
done

if [[ "${copied}" -eq 0 ]]; then
  echo "INFO: no SSH public keys found in ${ssh_dir} -- signing directory is empty" >&2
else
  echo "INFO: copied ${copied} SSH public key(s) to ${signing_dir}" >&2
fi
