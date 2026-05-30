#!/usr/bin/env bash
# Verify that the gh CLI config directory and credentials file have
# restrictive file modes. Called at postStartCommand time inside the
# container; the bind-mounted path reflects the host source permissions.
# Exits 1 and prints remediation commands when modes are too permissive.
set -euo pipefail

GH_DIR="${1:-${HOME}/.config/gh}"
HOSTS_FILE="${GH_DIR}/hosts.yml"
FAILED=0

if [ ! -d "${GH_DIR}" ]; then
  echo "INFO: ${GH_DIR} not found; gh CLI auth not yet configured." >&2
  exit 0
fi

DIR_MODE=$(stat -c '%a' "${GH_DIR}")
if [ "${DIR_MODE}" != "700" ]; then
  echo "ERROR: ${GH_DIR} has mode ${DIR_MODE}, expected 700." >&2
  echo "  Fix on host: chmod 700 ${GH_DIR}" >&2
  FAILED=1
fi

if [ -f "${HOSTS_FILE}" ]; then
  FILE_MODE=$(stat -c '%a' "${HOSTS_FILE}")
  if [ "${FILE_MODE}" != "600" ]; then
    echo "ERROR: ${HOSTS_FILE} has mode ${FILE_MODE}, expected 600." >&2
    echo "  Fix on host: chmod 600 ${HOSTS_FILE}" >&2
    FAILED=1
  fi
fi

if [ "${FAILED}" -ne 0 ]; then
  echo "ERROR: Insecure file modes on gh config; fix on the host then restart the container." >&2
  exit 1
fi

echo "OK: gh config file modes are restrictive." >&2
