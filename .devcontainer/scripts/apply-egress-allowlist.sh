#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ALLOWLIST_FILE" >&2
  exit 64
fi

ALLOWLIST_FILE="$1"
BASE_DIR="$(cd "$(dirname "$ALLOWLIST_FILE")" && pwd)"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 69
  fi
}

require_command getent
require_command iptables

if [[ "$(id -u)" -ne 0 ]]; then
  echo "egress allowlist must run as root" >&2
  exit 77
fi

read_allowlist() {
  local file="$1"
  local line include

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"

    [[ -z "$line" ]] && continue

    if [[ "$line" == @include\ * ]]; then
      include="${line#@include }"
      read_allowlist "$BASE_DIR/$include"
    else
      printf '%s\n' "$line"
    fi
  done < "$file"
}

mapfile -t HOSTS < <(read_allowlist "$ALLOWLIST_FILE" | sort -u)

if [[ "${#HOSTS[@]}" -eq 0 ]]; then
  echo "allowlist is empty: $ALLOWLIST_FILE" >&2
  exit 78
fi

iptables -P OUTPUT ACCEPT
iptables -F OUTPUT

iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

while IFS= read -r nameserver; do
  iptables -A OUTPUT -p udp -d "$nameserver" --dport 53 -j ACCEPT
  iptables -A OUTPUT -p tcp -d "$nameserver" --dport 53 -j ACCEPT
done < <(awk '/^nameserver[[:space:]]+/ { print $2 }' /etc/resolv.conf | sort -u)

for host in "${HOSTS[@]}"; do
  while IFS= read -r ip; do
    iptables -A OUTPUT -p tcp -d "$ip" -m multiport --dports 22,80,443 -j ACCEPT
  done < <(getent ahostsv4 "$host" | awk '{ print $1 }' | sort -u)
done

iptables -P OUTPUT DROP
echo "applied egress allowlist from $ALLOWLIST_FILE"
