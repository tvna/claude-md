#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ALLOWLIST_FILE" >&2
  exit 64
fi

ALLOWLIST_FILE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=.devcontainer/scripts/_egress-lib.sh
source "$SCRIPT_DIR/_egress-lib.sh"

# block (default): deny-by-default; only allowlisted egress is permitted.
# audit: record non-allowlisted egress without dropping it (discovery mode).
EGRESS_MODE="${EGRESS_MODE:-block}"
case "$EGRESS_MODE" in
  block | audit) ;;
  *)
    echo "invalid EGRESS_MODE: $EGRESS_MODE (expected 'block' or 'audit')" >&2
    exit 64
    ;;
esac

require_command getent || exit $?
require_command iptables || exit $?

if [[ "$(id -u)" -ne 0 ]]; then
  echo "egress allowlist must run as root" >&2
  exit 77
fi

mapfile -t HOSTS < <(read_allowlist "$ALLOWLIST_FILE" | sort -u)

if [[ "${#HOSTS[@]}" -eq 0 ]]; then
  echo "allowlist is empty: $ALLOWLIST_FILE" >&2
  exit 78
fi

egress_apply_accept_rules "${HOSTS[@]}"

if [[ "$EGRESS_MODE" == "block" ]]; then
  iptables -P OUTPUT DROP
  echo "applied egress allowlist (block) from $ALLOWLIST_FILE"
else
  # audit: the ACCEPT rules above short-circuit allowlisted traffic; anything
  # reaching the end of OUTPUT is logged (rate-limited, IP:port header only --
  # no payload) and then permitted by the ACCEPT policy. This records every
  # non-allowlisted destination without breaking connectivity, so an operator
  # can discover what a workload needs before promoting the file to block mode.
  iptables -A OUTPUT -m limit --limit 60/min --limit-burst 100 \
    -j LOG --log-prefix "EGRESS-AUDIT: " --log-level info
  iptables -P OUTPUT ACCEPT
  echo "applied egress allowlist (audit) from $ALLOWLIST_FILE"
fi
