#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
UPSTREAM="${CLUB3090_DIR:-${ROOT}/club-3090}"
STATE="${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}"
ENV_FILE="${CLUB3090_SERVER_ENV_FILE:-/etc/club3090-server.env}"
UNIT_DIR="${CLUB3090_SYSTEMD_UNIT_DIR:-/etc/systemd/system}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || missing+=("$1"); }

missing=()
need python3
need systemctl
need git
need curl
need openssl
need pamtester
need docker
need sudo
if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  missing+=("Docker Compose (docker compose or docker-compose)")
fi
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  missing+=("Python PyYAML module")
fi
if ((${#missing[@]})); then
  printf 'Missing prerequisites (install them with your OS package manager, then rerun):\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi
if [[ "${CLUB3090_ENABLE_EXTRA_TEMPS:-0}" == "1" ]]; then
  need gcc
  if ! ldconfig -p 2>/dev/null | grep -q 'libnvidia-ml\.so'; then
    missing+=("NVIDIA Management Library development/runtime linker")
  fi
  if ! ldconfig -p 2>/dev/null | grep -q 'libpci\.so'; then
    missing+=("libpci development library")
  fi
  if ((${#missing[@]})); then
    printf 'Missing optional temperature-helper prerequisites:\\n' >&2
    printf '  - %s\\n' "${missing[@]}" >&2
    exit 1
  fi
fi

[[ -f "${ROOT}/src/control/runtime.py" && -f "${ROOT}/src/web/base.html" ]] || fail "run this script from a complete Club-3090 Server checkout"
[[ -f "${UPSTREAM}/scripts/switch.sh" && -f "${UPSTREAM}/scripts/setup.sh" && -d "${UPSTREAM}/models" ]] || fail "upstream checkout not found or incomplete at ${UPSTREAM}; see docs/INSTALL.md"
for value in "${ROOT}" "${UPSTREAM}" "${STATE}"; do
  [[ "${value}" != *[$'\t\n ']* ]] || fail "repository, upstream, and state paths cannot contain whitespace: ${value}"
done

if [[ "${EUID}" -eq 0 ]]; then SUDO=(); else SUDO=(sudo); fi
 "${SUDO[@]}" install -d -m 0700 "${STATE}"
 "${SUDO[@]}" install -d -m 0755 "$(dirname "${ENV_FILE}")"
 "${SUDO[@]}" install -d -m 0755 "${UNIT_DIR}"
if [[ "${CLUB3090_ENABLE_EXTRA_TEMPS:-0}" == "1" ]]; then
  temporary_binary="$(mktemp)"
  trap 'rm -f "${temporary_binary:-}"' EXIT
  gcc -O3 -I"${ROOT}/src/build/vendor" "${ROOT}/src/build/vendor/gputemps.c" -o "${temporary_binary}" -lnvidia-ml -lpci
  "${SUDO[@]}" install -D -m 0755 "${temporary_binary}" "${STATE}/bin/gputemps"
  rm -f "${temporary_binary}"
  trap - EXIT
fi
if ! "${SUDO[@]}" test -e "${ENV_FILE}"; then
  "${SUDO[@]}" install -m 0600 /dev/null "${ENV_FILE}"
  printf 'CLUB3090_ADMIN_PORT=%s\nCLUB3090_PROXY_PORT=%s\n' \
    "${CLUB3090_ADMIN_PORT:-8008}" "${CLUB3090_PROXY_PORT:-8009}" | "${SUDO[@]}" tee "${ENV_FILE}" >/dev/null
fi

install_unit() {
  local source="$1" target="$2" line
  local rendered="$(mktemp)"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line//@SOURCE_ROOT@/${ROOT}}"
    line="${line//@CLUB3090_DIR@/${UPSTREAM}}"
    line="${line//@CONTROL_DIR@/${STATE}}"
    printf '%s\n' "${line}"
  done < "${ROOT}/systemd/${source}" > "${rendered}"
  "${SUDO[@]}" install -m 0644 "${rendered}" "${UNIT_DIR}/${target}"
  rm -f "${rendered}"
}

install_unit club3090-control.service club3090-control.service
install_unit club3090-benchmarks.service club3090-benchmarks.service
install_unit club3090-updater.service club3090-updater.service
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable club3090-control.service club3090-benchmarks.service club3090-updater.service

printf 'Installed Club-3090 Server services from %s\n' "${ROOT}"
printf 'Upstream runtime: %s\nMutable state: %s\nConfiguration: %s\n' "${UPSTREAM}" "${STATE}" "${ENV_FILE}"
printf 'Start the admin service with: sudo systemctl start club3090-control.service\n'
