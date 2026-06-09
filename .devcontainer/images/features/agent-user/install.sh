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
