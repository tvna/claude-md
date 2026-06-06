#!/usr/bin/env bash
#
# Devcontainer eBPF correlation monitor controller (best-effort, NOT a sandbox).
#
# Launches the bpftrace program egress-correlation.bt, which correlates each
# outbound TCP connect and each file open with the originating process (pid +
# comm) and records ONLY the destination IP:port or the file path -- never any
# syscall payload contents. The report is written to a LOCAL-ONLY sink; nothing
# leaves the machine (no third-party telemetry), matching the self-hosted design
# of the egress allowlist and DNS proxy.
#
# Honest limitation: the agent holds NET_ADMIN/CAP_BPF and can kill bpftrace or
# detach the probes from within the container (CVE-2025-32955 class bypass).
# This is detection plus correlation, not an enforcement boundary. See
# docs/runbooks/devcontainers.md.
#
# Graceful skip: on kernels without readable BTF, a mounted tracefs, or the
# CAP_BPF/CAP_PERFMON capabilities (common on Docker Desktop and hosted CI
# runners) `start` skips with a notice instead of failing the container boot.
#
# Default OFF: `start` and `stop` are no-ops unless EGRESS_EBPF=1.
#
# Subcommands:
#   check   Probe kernel/capability support. Pure: no root, no privileged calls,
#           no file writes. Prints `supported` (exit 0) or `skip` (exit 3) with
#           reasons on stderr. Detection inputs are overridable for tests.
#   start   Launch the monitor (gated by EGRESS_EBPF=1; graceful skip if check
#           reports the kernel is unsupported).
#   stop    Stop the monitor started from our .bt program (idempotent).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=.devcontainer/scripts/_egress-lib.sh
source "$SCRIPT_DIR/_egress-lib.sh"

# Overridable for tests; default to the real container values.
BPFTRACE_BIN="${BPFTRACE_BIN:-bpftrace}"
BT_SCRIPT="${BT_SCRIPT:-$SCRIPT_DIR/egress-correlation.bt}"
BTF_PATH="${BTF_PATH:-/sys/kernel/btf/vmlinux}"
TRACEFS_PATH="${TRACEFS_PATH:-/sys/kernel/debug/tracing}"
EGRESS_EBPF_REPORT="${EGRESS_EBPF_REPORT:-/tmp/egress-correlation.log}"

usage() {
  cat >&2 <<'EOF'
usage:
  _egress-ebpf.sh check
  _egress-ebpf.sh start
  _egress-ebpf.sh stop
EOF
}

# True when the effective capability set holds CAP_BPF (39) and CAP_PERFMON (38),
# or the caller is root. CAP_EFF (hex, no 0x) is overridable for tests; otherwise
# it is read from /proc/self/status. We require CAP_BPF/CAP_PERFMON specifically
# and never fall back to CAP_SYS_ADMIN.
has_bpf_caps() {
  local hex="${CAP_EFF:-}"
  if [[ -z "$hex" ]]; then
    # No explicit override: root has every capability; otherwise read the live
    # effective set. An explicit CAP_EFF (e.g. in tests) is authoritative and
    # bypasses the root short-circuit so the bit test stays deterministic.
    if [[ "$(id -u)" -eq 0 ]]; then
      return 0
    fi
    hex="$(awk '/^CapEff:/ { print $2 }' /proc/self/status 2>/dev/null)"
  fi
  [[ -n "$hex" ]] || return 1
  local bits=$((16#$hex))
  (((bits >> 38) & 1)) && (((bits >> 39) & 1))
}

# Probe whether the kernel can run the correlation monitor. Pure and
# unprivileged: it only reads command availability, two pseudo-filesystem paths,
# and the capability set. Prints `supported`/`skip` to stdout and any blocking
# reasons to stderr. Exit 0 supported, 3 unsupported (the graceful-skip seam).
cmd_check() {
  local -a reasons=()
  command -v "$BPFTRACE_BIN" >/dev/null 2>&1 || reasons+=("bpftrace not found ($BPFTRACE_BIN)")
  [[ -r "$BTF_PATH" ]] || reasons+=("kernel BTF not readable ($BTF_PATH)")
  [[ -d "$TRACEFS_PATH" ]] || reasons+=("tracefs not mounted ($TRACEFS_PATH)")
  has_bpf_caps || reasons+=("missing CAP_BPF/CAP_PERFMON (and not root)")

  if [[ "${#reasons[@]}" -gt 0 ]]; then
    local r
    for r in "${reasons[@]}"; do
      echo "eBPF unsupported: $r" >&2
    done
    echo "skip"
    return 3
  fi
  echo "supported"
}

cmd_start() {
  if [[ "${EGRESS_EBPF:-0}" != "1" ]]; then
    echo "EGRESS_EBPF!=1; eBPF correlation disabled (opt-in no-op)." >&2
    return 0
  fi

  # Graceful skip on unsupported kernels (Docker Desktop, hosted runners): never
  # fail the boot just because eBPF is unavailable.
  if ! cmd_check >/dev/null; then
    echo "eBPF correlation skipped: kernel/capabilities unsupported (best-effort)." >&2
    return 0
  fi

  if [[ ! -r "$BT_SCRIPT" ]]; then
    echo "bpftrace program not found: $BT_SCRIPT" >&2
    return 66
  fi

  # Local-only sink. No external telemetry; payload contents are never recorded.
  nohup "$BPFTRACE_BIN" "$BT_SCRIPT" >>"$EGRESS_EBPF_REPORT" 2>&1 &
  echo "started eBPF correlation monitor (report=$EGRESS_EBPF_REPORT)"
}

cmd_stop() {
  if [[ "${EGRESS_EBPF:-0}" != "1" ]]; then
    echo "EGRESS_EBPF!=1; eBPF correlation disabled (opt-in no-op)." >&2
    return 0
  fi

  # Stop only the bpftrace started from our program (best-effort, idempotent).
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "$BPFTRACE_BIN $BT_SCRIPT" || true
  fi
  echo "stopped eBPF correlation monitor (best-effort)"
}

main() {
  local subcmd="${1:-}"
  [[ $# -gt 0 ]] && shift
  case "$subcmd" in
    check) cmd_check "$@" ;;
    start) cmd_start "$@" ;;
    stop) cmd_stop "$@" ;;
    -h | --help | help) usage ;;
    *)
      usage
      return 64
      ;;
  esac
}

main "$@"
