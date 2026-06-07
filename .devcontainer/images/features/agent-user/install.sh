#!/usr/bin/env sh
set -eu

agent_user="${AGENTUSER:-}"

case "$agent_user" in
  claude | codex)
    ;;
  *)
    echo "unsupported agentUser: $agent_user" >&2
    exit 64
    ;;
esac

mkdir -p "/home/$agent_user"

awk -F: -v agent="$agent_user" '
  BEGIN { OFS = FS; print agent, "x", "0", "0", agent, "/home/" agent, "/bin/bash" }
  $1 != agent { print }
' /etc/passwd > /etc/passwd.new
cat /etc/passwd.new > /etc/passwd
rm /etc/passwd.new

awk -F: -v agent="$agent_user" '
  BEGIN { OFS = FS; print agent, "x", "0", "" }
  $1 != agent { print }
' /etc/group > /etc/group.new
cat /etc/group.new > /etc/group
rm /etc/group.new

chown -R 0:0 "/home/$agent_user"
printf '%s ALL=(root) NOPASSWD:ALL\n' "$agent_user" > "/etc/sudoers.d/$agent_user"
chmod 0440 "/etc/sudoers.d/$agent_user"

# This Feature runs last in overrideFeatureInstallOrder (after the nix Feature),
# so the store is fully populated at this build-time point and `devcontainer
# build` does not run postCreateCommand afterwards. Drop the Nix store
# optimisation hardlink farm (/nix/store/.links): it is a build-time dedup
# mechanism with no runtime role, but Trivy's secret scanner in
# publish-devcontainer-images.yml walks every .links/<hash> entry as a second
# path to the same file, double-reporting Code scanning alerts. Removing a
# .links entry only drops one hardlink; the real store path keeps the inode, so
# package contents and inter-derivation dedup are preserved. Refs #1348.
rm -rf /nix/store/.links
