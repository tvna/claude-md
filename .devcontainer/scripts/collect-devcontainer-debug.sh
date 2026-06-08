#!/usr/bin/env bash
#
# Host-side devcontainer debug-log collector (macOS-focused, cross-platform
# best-effort). Gathers the host diagnostics needed to triage a failed
# devcontainer start into a single LOCAL-ONLY bundle. Nothing leaves the
# machine; the operator reviews the bundle and shares it deliberately. See
# docs/runbooks/devcontainers.md "Debug log capture (macOS)" (Issue #1460).
#
# Safety (CLAUDE.md section 4):
#   - Collects only an allowlisted set of host diagnostics. It NEVER reads
#     ~/.config/gh, the agent session volumes, or a full environment dump --
#     those are token-bearing and out of scope.
#   - Every captured stream is piped through `redact`, a best-effort filter
#     that masks common token formats. Redaction is best-effort, not a
#     guarantee: review the bundle before sharing it (the SUMMARY says so too).
#   - The bundle is written under a local temp dir only; no external sink.
#
# Verification scope (CLAUDE.md section 1):
#   The end-to-end `collect` path needs macOS + Podman + a running VM and
#   cannot be exercised in Linux CI. CI exercises the pure `plan` and `redact`
#   seams (sources/binaries overridable via env) plus `bash -n`.
#
# Subcommands:
#   plan      Pure, unprivileged: print every source it would collect and the
#             output path. Writes nothing. CI-testable.
#   redact    Stdin -> stdout secret-masking filter (the safety core). Pure.
#   collect   Gather the allowlisted diagnostics into a redacted local bundle.
set -euo pipefail

# Overridable for tests; default to the real host values.
PODMAN_BIN="${PODMAN_BIN:-podman}"
# VS Code stores per-window logs here on macOS; Linux uses ~/.config/Code/logs.
if [[ -n "${VSCODE_LOGS_DIR:-}" ]]; then
  :
elif [[ "$(uname -s)" == "Darwin" ]]; then
  VSCODE_LOGS_DIR="${HOME}/Library/Application Support/Code/logs"
else
  VSCODE_LOGS_DIR="${HOME}/.config/Code/logs"
fi

usage() {
  cat >&2 <<'EOF'
usage:
  collect-devcontainer-debug.sh plan
  collect-devcontainer-debug.sh redact   # filters stdin to stdout
  collect-devcontainer-debug.sh collect

The bundle is local-only and best-effort redacted. Review it before sharing.
EOF
}

# The fixed, allowlisted command captures. One "label|command" per line; the
# command is run with `redact` applied and tolerant of a missing binary.
podman_sources() {
  cat <<EOF
podman-machine-list|${PODMAN_BIN} machine list
podman-info|${PODMAN_BIN} info
podman-system-connection-list|${PODMAN_BIN} system connection list
podman-machine-inspect|${PODMAN_BIN} machine inspect
podman-ps-all|${PODMAN_BIN} ps -a
podman-machine-journal|${PODMAN_BIN} machine ssh -- journalctl -n 500 --no-pager
EOF
}

# Default output directory for `collect`. A timestamped local temp dir.
default_outdir() {
  printf '%s/devcontainer-debug-%s' "${TMPDIR:-/tmp}" "$(date +%Y%m%d-%H%M%S)"
}

# Best-effort secret masking, stdin -> stdout. Patterns are written in portable
# ERE so the same script works under BSD sed (macOS) and GNU sed (Linux): no
# \b, no case-insensitive flag, no in-place edits. Header keywords spell out
# both cases explicitly. This is defense in depth, not a guarantee.
redact() {
  sed -E \
    -e 's/gh[opsur]_[A-Za-z0-9]{20,}/[REDACTED-TOKEN]/g' \
    -e 's/github_pat_[A-Za-z0-9_]{20,}/[REDACTED-TOKEN]/g' \
    -e 's/sk-[A-Za-z0-9_-]{20,}/[REDACTED-TOKEN]/g' \
    -e 's/AKIA[0-9A-Z]{16}/[REDACTED-AWS-KEY]/g' \
    -e 's/([Aa]uthorization:[[:space:]]*).*$/\1[REDACTED]/g' \
    -e 's/([Bb]earer[[:space:]]+)[A-Za-z0-9._~+/=-]+/\1[REDACTED]/g' \
    -e 's/([Ss]et-[Cc]ookie:[[:space:]]*).*$/\1[REDACTED]/g' \
    -e 's/([A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|PASSWD|APIKEY|API_KEY|PRIVATE_KEY)[[:space:]]*[=:][[:space:]]*)[^[:space:]"'"'"']+/\1[REDACTED]/g'
}

# Run one allowlisted command, redacting its output into "$1". Tolerates a
# missing binary (records `unavailable`) and a non-zero exit (kept, redacted),
# so one missing tool never aborts the whole bundle.
capture_cmd() {
  local outfile="$1"
  shift
  if ! command -v "$1" >/dev/null 2>&1 && [[ ! -x "$1" ]]; then
    printf 'unavailable: %s not found on host\n' "$1" >"$outfile"
    return 0
  fi
  { "$@" 2>&1 || true; } | redact >"$outfile"
}

# Copy the newest VS Code Dev Containers (remote-containers) log directory,
# redacted, into the bundle. This is the primary startup debug log on macOS.
collect_vscode_logs() {
  local dest="$1"
  local note="$dest/vscode-remote-containers.txt"
  if [[ ! -d "$VSCODE_LOGS_DIR" ]]; then
    printf 'unavailable: VS Code logs dir not found (%s)\n' "$VSCODE_LOGS_DIR" >"$note"
    return 0
  fi
  # The remote-containers extension logs under a per-window exthost subtree.
  local newest
  newest="$(find "$VSCODE_LOGS_DIR" -type d -name '*remote-containers*' 2>/dev/null \
    | while read -r d; do printf '%s\t%s\n' "$(stat_mtime "$d")" "$d"; done \
    | sort -rn | head -n 1 | cut -f2-)"
  if [[ -z "$newest" ]]; then
    {
      printf 'no remote-containers log dir under %s\n' "$VSCODE_LOGS_DIR"
      printf 'Open it manually: VS Code -> Output panel -> "Dev Containers" channel.\n'
    } >"$note"
    return 0
  fi
  mkdir -p "$dest/vscode-remote-containers"
  local f base
  find "$newest" -type f -name '*.log' 2>/dev/null | while read -r f; do
    base="$(basename "$f")"
    redact <"$f" >"$dest/vscode-remote-containers/$base"
  done
  printf 'copied (redacted) from: %s\n' "$newest" >"$note"
}

# Portable mtime-as-epoch (BSD stat vs GNU stat), used to pick the newest dir.
stat_mtime() {
  stat -f '%m' "$1" 2>/dev/null || stat -c '%Y' "$1" 2>/dev/null || echo 0
}

cmd_plan() {
  local outdir="${DEVCONTAINER_DEBUG_OUTDIR:-$(default_outdir)}"
  echo "output bundle dir: $outdir"
  echo "sources:"
  local label
  while IFS='|' read -r label _; do
    [[ -n "$label" ]] && echo "  - $label"
  done < <(podman_sources)
  echo "  - vscode-remote-containers (from: $VSCODE_LOGS_DIR)"
  echo "excluded (token-bearing, never collected): ~/.config/gh, agent session volumes, environment dump"
  echo "note: bundle is local-only and best-effort redacted; review before sharing"
}

cmd_collect() {
  local outdir="${DEVCONTAINER_DEBUG_OUTDIR:-$(default_outdir)}"
  mkdir -p "$outdir"

  local label command
  while IFS='|' read -r label command; do
    [[ -n "$label" ]] || continue
    # shellcheck disable=SC2086 # command is an allowlisted, space-split argv
    capture_cmd "$outdir/${label}.txt" $command
  done < <(podman_sources)

  collect_vscode_logs "$outdir"

  {
    echo "Devcontainer debug bundle"
    echo "host: $(uname -srm 2>/dev/null || echo unknown)"
    echo "created: $(date 2>/dev/null || echo unknown)"
    echo
    echo "Contents are best-effort redacted (token formats masked). Redaction"
    echo "is NOT a guarantee -- review every file before sharing this bundle."
    echo "Token-bearing sources (~/.config/gh, session volumes, env dump) were"
    echo "deliberately NOT collected."
  } >"$outdir/SUMMARY.txt"

  echo "wrote bundle: $outdir"
  if command -v tar >/dev/null 2>&1; then
    local tarball="${outdir}.tar.gz"
    if tar -czf "$tarball" -C "$(dirname "$outdir")" "$(basename "$outdir")" 2>/dev/null; then
      echo "wrote tarball: $tarball"
    fi
  fi
  echo "review the bundle before sharing it (it is local-only and best-effort redacted)"
}

main() {
  local subcmd="${1:-}"
  [[ $# -gt 0 ]] && shift
  case "$subcmd" in
    plan) cmd_plan "$@" ;;
    redact) redact "$@" ;;
    collect) cmd_collect "$@" ;;
    -h | --help | help) usage ;;
    *)
      usage
      return 64
      ;;
  esac
}

main "$@"
