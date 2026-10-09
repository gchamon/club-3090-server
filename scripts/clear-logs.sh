#!/usr/bin/env bash
set -euo pipefail

CONTROL_DIR="${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}"
LOG_FILES=(
  "${CONTROL_DIR}/control.log"
  "${CONTROL_DIR}/audit.log"
  "${CONTROL_DIR}/debug.log"
  "${CONTROL_DIR}/self-update.log"
  "${CONTROL_DIR}/benchmarks/benchmarks.log"
)

if [[ ! -d "${CONTROL_DIR}" ]]; then
  printf 'Control directory does not exist: %s\n' "${CONTROL_DIR}" >&2
  exit 1
fi

for file in "${LOG_FILES[@]}"; do
  [[ ! -e "${file}" && ! -L "${file}" ]] && continue
  if [[ -L "${file}" || ! -f "${file}" ]]; then
    printf 'Refusing to clear non-regular log file: %s\n' "${file}" >&2
    exit 1
  fi
  if [[ ! -w "${file}" ]]; then
    printf 'No write permission for log file: %s (run with sudo if needed)\n' "${file}" >&2
    exit 1
  fi
done

cleared=0
for file in "${LOG_FILES[@]}"; do
  [[ -f "${file}" ]] || continue
  : > "${file}"
  printf 'Cleared %s\n' "${file}"
  ((cleared += 1))
done

if ((cleared == 0)); then
  printf 'No application log files found under %s\n' "${CONTROL_DIR}"
fi
