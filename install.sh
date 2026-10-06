#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ENV_FILE="${CLUB3090_SERVER_ENV_FILE:-/etc/club3090-server.env}"
UNIT_DIR="${CLUB3090_SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
read_config_value() {
  local wanted="$1" line key value found=""
  [[ -r "${ENV_FILE}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" == *=* ]] || continue
    key="${line%%=*}"
    [[ "${key}" == "${wanted}" ]] || continue
    value="${line#*=}"
    if [[ "${value}" == '"'*"'" ]]; then value="${value:1:${#value}-2}"; fi
    found="${value%$'\r'}"
  done < "${ENV_FILE}"
  printf '%s' "${found}"
}
UPSTREAM="${CLUB3090_DIR:-$(read_config_value CLUB3090_DIR)}"
UPSTREAM="${UPSTREAM:-${ROOT}/club-3090}"
STATE="${CLUB3090_CONTROL_DIR:-$(read_config_value CLUB3090_CONTROL_DIR)}"
STATE="${STATE:-/var/lib/club3090-control}"
ADMIN_PORT="${CLUB3090_ADMIN_PORT:-$(read_config_value CLUB3090_ADMIN_PORT)}"
ADMIN_PORT="${ADMIN_PORT:-8008}"
PROXY_PORT="${CLUB3090_PROXY_PORT:-$(read_config_value CLUB3090_PROXY_PORT)}"
PROXY_PORT="${PROXY_PORT:-8009}"
ADMIN_BIND_HOST="${CLUB3090_ADMIN_BIND_HOST:-$(read_config_value CLUB3090_ADMIN_BIND_HOST)}"
ADMIN_BIND_HOST="${ADMIN_BIND_HOST:-0.0.0.0}"
PROXY_BIND_HOST="${CLUB3090_PROXY_BIND_HOST:-$(read_config_value CLUB3090_PROXY_BIND_HOST)}"
PROXY_BIND_HOST="${PROXY_BIND_HOST:-0.0.0.0}"
DEFAULT_MODE="${DEFAULT_MODE:-$(read_config_value DEFAULT_MODE)}"
EXTRA_TEMPS="${CLUB3090_ENABLE_EXTRA_TEMPS:-$(read_config_value CLUB3090_ENABLE_EXTRA_TEMPS)}"
EXTRA_TEMPS="${EXTRA_TEMPS:-0}"
SETUP_MODEL="${CLUB3090_SETUP_MODEL-}"
SETUP_MODEL_SET="${CLUB3090_SETUP_MODEL+x}"

progress() { printf '[install] %s\n' "$*" >&2; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || missing+=("$1"); }

progress "Checking host dependencies"
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
if [[ "${SETUP_MODEL_SET}" == "x" ]]; then
  [[ -n "${SETUP_MODEL}" && "${SETUP_MODEL}" != *[$'\t\n ']* ]] || fail "CLUB3090_SETUP_MODEL must be a non-empty, whitespace-free model identifier"
  need nvidia-smi
  need sha256sum
  if ! command -v hf >/dev/null 2>&1 && ! command -v huggingface-cli >/dev/null 2>&1; then
    missing+=("Hugging Face CLI (hf or huggingface-cli)")
  fi
fi
if ((${#missing[@]})); then
  printf 'Missing prerequisites (install them with your OS package manager, then rerun):\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi
if [[ "${EXTRA_TEMPS}" == "1" ]]; then
progress "Checking optional temperature-helper dependencies"
  need gcc
  if ! ldconfig -p 2>/dev/null | grep -q 'libnvidia-ml\.so'; then
    missing+=("NVIDIA Management Library development/runtime linker")
  fi
  if ! ldconfig -p 2>/dev/null | grep -q 'libpci\.so'; then
    missing+=("libpci development library")
  fi
  if ((${#missing[@]})); then
    printf 'Missing optional temperature-helper prerequisites:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    exit 1
  fi
fi

progress "Validating server and upstream checkouts"
[[ -x "${ROOT}/install.sh" && -f "${ROOT}/src/control/http_server.py" && -f "${ROOT}/src/web/base.html" ]] || fail "run this script from a complete Club-3090 Server checkout"
for helper in prepare-headless-x.sh start-vllm-last-mode.sh follow-vllm-log.sh refresh-ip-certificate.sh; do
  [[ -x "${ROOT}/scripts/club3090-server/${helper}" ]] || fail "missing executable checkout helper: ${ROOT}/scripts/club3090-server/${helper}"
done
for unit in club3090-control.service club3090-benchmarks.service club3090-updater.service club3090-headless-x.service club3090-console-log.service club3090-vllm.service club3090-cert-refresh.service club3090-cert-refresh.timer; do
  [[ -r "${ROOT}/systemd/${unit}" ]] || fail "missing systemd unit template: ${ROOT}/systemd/${unit}"
done
git_top="$(git -C "${ROOT}" rev-parse --show-toplevel 2>/dev/null)" || fail "installer must run from a git checkout"
[[ "${git_top}" == "${ROOT}" ]] || fail "run install.sh from the root of the git checkout"
[[ -d "${UPSTREAM}" ]] || fail "upstream checkout not found at ${UPSTREAM}; expected scripts/preflight.sh, scripts/setup.sh, scripts/switch.sh, scripts/launch.sh, and models/. See docs/INSTALL.md"
UPSTREAM="$(cd -- "${UPSTREAM}" && pwd -P)"
upstream_git_top="$(git -C "${UPSTREAM}" rev-parse --show-toplevel 2>/dev/null)" || fail "upstream checkout is not a git repository at ${UPSTREAM}; expected scripts/preflight.sh, scripts/setup.sh, scripts/switch.sh, scripts/launch.sh, and models/. See docs/INSTALL.md"
[[ "${upstream_git_top}" == "${UPSTREAM}" ]] || fail "CLUB3090_DIR must name the root of an upstream git checkout at ${UPSTREAM}; see docs/INSTALL.md"
[[ -f "${UPSTREAM}/scripts/preflight.sh" && -f "${UPSTREAM}/scripts/setup.sh" && -f "${UPSTREAM}/scripts/switch.sh" && -f "${UPSTREAM}/scripts/launch.sh" && -d "${UPSTREAM}/models" ]] || fail "upstream checkout incomplete at ${UPSTREAM}; expected scripts/preflight.sh, scripts/setup.sh, scripts/switch.sh, scripts/launch.sh, and models/. See docs/INSTALL.md"
for value in "${ROOT}" "${UPSTREAM}" "${STATE}"; do
  [[ "${value}" != *[$'\t\n ']* ]] || fail "repository, upstream, and state paths cannot contain whitespace: ${value}"
done
for port in "${ADMIN_PORT}" "${PROXY_PORT}"; do
  [[ "${port}" =~ ^[0-9]{1,5}$ ]] && ((10#${port} >= 1 && 10#${port} <= 65535)) || fail "invalid service port: ${port}"
done
[[ "${ADMIN_PORT}" != "${PROXY_PORT}" ]] || fail "admin and proxy ports must differ"
for value in "${ADMIN_BIND_HOST}" "${PROXY_BIND_HOST}" "${DEFAULT_MODE}" "${EXTRA_TEMPS}"; do
  [[ "${value}" != *[$'\t\n ']* ]] || fail "service settings cannot contain whitespace: ${value}"
done

if [[ "${SETUP_MODEL_SET}" == "x" ]]; then
  progress "Running upstream model setup for ${SETUP_MODEL} from ${UPSTREAM}"
  (cd -- "${UPSTREAM}" && bash "${UPSTREAM}/scripts/setup.sh" "${SETUP_MODEL}")
  progress "Upstream model setup completed"
else
  progress "No model selected; skipping upstream model setup"
fi

if [[ "${EUID}" -eq 0 ]]; then SUDO=(); else SUDO=(sudo); fi
progress "Creating mutable state and service configuration directories"
 "${SUDO[@]}" install -d -m 0700 "${STATE}"
 "${SUDO[@]}" install -d -m 0755 "$(dirname "${ENV_FILE}")"
 "${SUDO[@]}" install -d -m 0755 "${UNIT_DIR}"
if [[ "${EXTRA_TEMPS}" == "1" ]]; then
  progress "Compiling optional temperature helper"
  temporary_binary="$(mktemp)"
  trap 'rm -f "${temporary_binary:-}"' EXIT
  gcc -O3 -I"${ROOT}/src/build/vendor" "${ROOT}/src/build/vendor/gputemps.c" -o "${temporary_binary}" -lnvidia-ml -lpci
  "${SUDO[@]}" install -D -m 0755 "${temporary_binary}" "${STATE}/bin/gputemps"
  rm -f "${temporary_binary}"
  trap - EXIT
fi
progress "Writing service configuration to ${ENV_FILE}"
 "${SUDO[@]}" env \
  CLUB3090_SERVER_DIR="${ROOT}" \
  CLUB3090_DIR="${UPSTREAM}" \
  CLUB3090_CONTROL_DIR="${STATE}" \
  CLUB3090_ADMIN_PORT="${ADMIN_PORT}" \
  CLUB3090_PROXY_PORT="${PROXY_PORT}" \
  CLUB3090_ADMIN_BIND_HOST="${ADMIN_BIND_HOST}" \
  CLUB3090_PROXY_BIND_HOST="${PROXY_BIND_HOST}" \
  DEFAULT_MODE="${DEFAULT_MODE}" \
  CLUB3090_ENABLE_EXTRA_TEMPS="${EXTRA_TEMPS}" \
  python3 - "${ENV_FILE}" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
keys = (
    "CLUB3090_SERVER_DIR",
    "CLUB3090_DIR",
    "CLUB3090_CONTROL_DIR",
    "CLUB3090_ADMIN_PORT",
    "CLUB3090_PROXY_PORT",
    "CLUB3090_ADMIN_BIND_HOST",
    "CLUB3090_PROXY_BIND_HOST",
    "DEFAULT_MODE",
    "CLUB3090_ENABLE_EXTRA_TEMPS",
)
updates = {key: os.environ[key] for key in keys}
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
written = set()
output = []
for line in lines:
    key = line.partition("=")[0]
    if key not in updates:
        output.append(line)
    elif key not in written:
        output.append(f"{key}={updates[key]}")
        written.add(key)
for key in keys:
    if key not in written:
        output.append(f"{key}={updates[key]}")
path.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
    handle.write("\n".join(output) + "\n")
    temporary = handle.name
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY

install_unit() {
  local source="$1" target="$2" line
  local rendered="$(mktemp)"
  progress "Rendering and installing ${target}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line//@SOURCE_ROOT@/${ROOT}}"
    line="${line//@ENV_FILE@/${ENV_FILE}}"
    line="${line//@CLUB3090_DIR@/${UPSTREAM}}"
    line="${line//@CONTROL_DIR@/${STATE}}"
    printf '%s\n' "${line}"
  done < "${ROOT}/systemd/${source}" > "${rendered}"
  "${SUDO[@]}" install -m 0644 "${rendered}" "${UNIT_DIR}/${target}"
  rm -f "${rendered}"
}

progress "Rendering systemd service units into ${UNIT_DIR}"
install_unit club3090-control.service club3090-control.service
install_unit club3090-benchmarks.service club3090-benchmarks.service
install_unit club3090-updater.service club3090-updater.service
install_unit club3090-headless-x.service club3090-headless-x.service
install_unit club3090-console-log.service club3090-console-log.service
install_unit club3090-vllm.service club3090-vllm.service
install_unit club3090-cert-refresh.service club3090-cert-refresh.service
install_unit club3090-cert-refresh.timer club3090-cert-refresh.timer
progress "Reloading systemd unit definitions"
"${SUDO[@]}" systemctl daemon-reload
progress "Enabling control, benchmark, updater, and inference services"
"${SUDO[@]}" systemctl enable club3090-control.service club3090-benchmarks.service club3090-updater.service club3090-vllm.service
progress "Starting control, updater, and inference services; systemd may wait for startup"
"${SUDO[@]}" systemctl start club3090-control.service club3090-updater.service club3090-vllm.service
progress "Installation complete"

printf 'Installed Club-3090 Server services from %s\n' "${ROOT}"
printf 'Upstream runtime: %s\nMutable state: %s\nConfiguration: %s\n' "${UPSTREAM}" "${STATE}" "${ENV_FILE}"
printf 'Admin panel: http://%s:%s/admin\nOpenAI-compatible API: http://%s:%s/v1\n' "${ADMIN_BIND_HOST}" "${ADMIN_PORT}" "${PROXY_BIND_HOST}" "${PROXY_PORT}"
