#!/usr/bin/env bash
# Shared SessionStart download helper (Refs #2038).
#
# Why this exists:
#   The ten SessionStart installers (scripts/install-*.sh) each fetch a pinned
#   release with a single curl call. curl does not retry by default, so a
#   transient network blip aborts the install with no in-session recovery, and
#   the failure surfacing differs per script. This helper centralises one
#   retry-with-backoff loop and one fail-loud-but-fail-open path so every
#   installer behaves identically (SSOT). scan_install_curl_retry_drift.py keeps
#   the installers from reintroducing a bare download command.
#
# This file is SOURCED, never executed: it only defines functions. The sourcing
# installer owns `set -euo pipefail`; retry_download keeps the download failure
# inside an `if`/`||` context so it never trips `set -e` on its own.
#
# Public API:
#   retry_download URL DEST TOOL_LABEL REINSTALL_CMD
#     Fetch URL to DEST, retrying up to RETRY_MAX_RETRIES times (default 3;
#     initial attempt + 3 retries = 4 total) with exponential backoff
#     (RETRY_BASE_DELAY * 2^n seconds; default base 2 -> 2s, 4s, 8s). Returns 0
#     on the first success. After all attempts fail it prints a loud stderr
#     banner plus one best-effort SessionStart additionalContext JSON object on
#     stdout, then returns 1. Callers fail open with `|| exit 0`.
#
# Tunables (env, primarily for tests):
#   RETRY_BASE_DELAY   backoff base seconds (default 2; tests set 0)
#   RETRY_MAX_RETRIES  retries after the initial attempt (default 3)

# Emit the loud failure banner (stderr) and a best-effort in-session message
# (stdout, SessionStart additionalContext). stdout stays JSON-only so the
# installer's hook output contract holds; python3 keeps the JSON well-formed.
_retry_emit_failure() {
  local url="$1" tool="$2" reinstall="$3" attempts="$4"
  {
    echo "============================================================"
    echo "install: ${tool}: DOWNLOAD FAILED after ${attempts} attempt(s)"
    echo "  url:      ${url}"
    echo "  recovery: re-run '${reinstall}' once network access is restored"
    echo "  impact:   ${tool} is unavailable this session; its local gate"
    echo "            soft-skips and CI remains the hard gate"
    echo "============================================================"
  } >&2
  local msg
  msg="SessionStart installer failure: ${tool} download failed after ${attempts} attempt(s) from ${url}. The session started without it; re-run '${reinstall}' once network access is restored."
  python3 -c 'import json, sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))' "${msg}" 2>/dev/null || true
}

# retry_download URL DEST TOOL_LABEL REINSTALL_CMD
retry_download() {
  local url="$1" dest="$2" tool="$3" reinstall="$4"
  local base="${RETRY_BASE_DELAY:-2}"
  local max_retries="${RETRY_MAX_RETRIES:-3}"
  local attempt=0 delay
  while true; do
    if curl -fsSL "${url}" -o "${dest}"; then
      return 0
    fi
    if [ "${attempt}" -ge "${max_retries}" ]; then
      break
    fi
    delay=$((base * (1 << attempt)))
    echo "retry_download: ${tool}: attempt $((attempt + 1))/$((max_retries + 1)) failed; retrying in ${delay}s ..." >&2
    sleep "${delay}"
    attempt=$((attempt + 1))
  done
  _retry_emit_failure "${url}" "${tool}" "${reinstall}" "$((max_retries + 1))"
  return 1
}
