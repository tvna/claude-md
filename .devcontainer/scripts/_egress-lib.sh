# shellcheck shell=bash
#
# Shared egress-allowlist helpers.
#
# Sourced by apply-egress-allowlist.sh (the privileged dispatcher) and by the
# bash<->Python parser-parity gate (scripts/scan_allowlist_parser_parity.py).
# Sourcing this file defines functions only and has NO side effects: it does not
# check privileges and does not mutate the firewall. The caller decides when to
# apply rules. read_allowlist performs no name resolution, so the parity gate can
# source this library and resolve host sets without network access.

# Fail loud when a required command is absent. Returns 69 (EX_UNAVAILABLE) so a
# caller using ``|| exit $?`` preserves the historical exit code.
require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    return 69
  fi
}

# Expand an allowlist file into a newline-delimited host list on stdout.
#
# Recursively follows ``@include <file>`` directives relative to the including
# file's directory, strips inline ``#`` comments and surrounding whitespace, and
# skips blank / comment-only lines. This is pure parsing with no name
# resolution; it mirrors scripts/_allowlist.py:resolve_hosts and the two are
# kept in agreement by scripts/scan_allowlist_parser_parity.py.
read_allowlist() {
  local file="$1"
  local base
  base="$(cd "$(dirname "$file")" && pwd)"
  local line include
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"

    [[ -z "$line" ]] && continue

    if [[ "$line" == @include\ * ]]; then
      include="${line#@include }"
      read_allowlist "$base/$include"
    else
      printf '%s\n' "$line"
    fi
  done < "$file"
}

# Print the nameserver IPs from /etc/resolv.conf, de-duplicated.
resolve_nameservers() {
  awk '/^nameserver[[:space:]]+/ { print $2 }' /etc/resolv.conf | sort -u
}

# Apply the OUTPUT-chain ACCEPT rules shared by block and audit mode: loopback,
# established/related, DNS to the configured nameservers, and each resolved
# allowlist host on the agent egress ports (22/80/443). Mutates iptables, so it
# must run from a privileged dispatcher. Hosts are passed as positional args.
egress_apply_accept_rules() {
  iptables -P OUTPUT ACCEPT
  iptables -F OUTPUT

  iptables -A OUTPUT -o lo -j ACCEPT
  iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

  local nameserver
  while IFS= read -r nameserver; do
    iptables -A OUTPUT -p udp -d "$nameserver" --dport 53 -j ACCEPT
    iptables -A OUTPUT -p tcp -d "$nameserver" --dport 53 -j ACCEPT
  done < <(resolve_nameservers)

  local host ip
  for host in "$@"; do
    while IFS= read -r ip; do
      iptables -A OUTPUT -p tcp -d "$ip" -m multiport --dports 22,80,443 -j ACCEPT
    done < <(getent ahostsv4 "$host" | awk '{ print $1 }' | sort -u)
  done
}
