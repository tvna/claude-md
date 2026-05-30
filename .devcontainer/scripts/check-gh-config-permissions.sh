#!/usr/bin/env bash
# Verify that the host gh CLI config directory and credentials file have
# restrictive file modes before the devcontainer starts. Running this on
# the host avoids false positives from macOS/Podman bind mounts that can
# appear as mode 777 inside Linux containers.
set -euo pipefail

GH_DIR="${1:-${HOME}/.config/gh}"
HOSTS_FILE="${GH_DIR}/hosts.yml"
FAILED=0

mode_of() {
  local path="$1"

  if stat -f '%Lp' "${path}" >/dev/null 2>&1; then
    stat -f '%Lp' "${path}"
    return 0
  fi

  stat -c '%a' "${path}"
}

display_path() {
  local path="$1"
  local home_prefix="${HOME%/}/"

  if [[ "${path}" == "${HOME}" ]]; then
    printf '~'
  elif [[ "${path}" == "${home_prefix}"* ]]; then
    printf '~/%s' "${path#"${home_prefix}"}"
  else
    printf '%s' "${path}"
  fi
}

if [ ! -d "${GH_DIR}" ]; then
  echo "INFO: ${GH_DIR} not found; gh CLI auth not yet configured." >&2
  exit 0
fi

DIR_MODE=$(mode_of "${GH_DIR}")
if [ "${DIR_MODE}" != "700" ]; then
  echo "ERROR: ${GH_DIR} has mode ${DIR_MODE}, expected 700." >&2
  echo "  Fix on host: chmod 700 $(display_path "${GH_DIR}")" >&2
  FAILED=1
fi

if [ -f "${HOSTS_FILE}" ]; then
  FILE_MODE=$(mode_of "${HOSTS_FILE}")
  if [ "${FILE_MODE}" != "600" ]; then
    echo "ERROR: ${HOSTS_FILE} has mode ${FILE_MODE}, expected 600." >&2
    echo "  Fix on host: chmod 600 $(display_path "${HOSTS_FILE}")" >&2
    FAILED=1
  fi
fi

if [ "${FAILED}" -ne 0 ]; then
  echo "ERROR: Insecure file modes on gh config; fix on the host then restart the container." >&2
  exit 1
fi

echo "OK: gh config file modes are restrictive." >&2
