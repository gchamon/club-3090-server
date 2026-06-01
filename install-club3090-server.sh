#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="2026-06-01.v0.9.24"
CHANGE_LOG_ICONS='{"new_feature":"🟢","fix":"🐞","remove_feature":"🔴","security":"🔒","performance":"⚡","ui_ux":"🖥️","build_pipeline_improvement":"🛠️","test":"🧪","update":"🔄","docs":"📝","backend":"🧰","compatibility":"🧩","modified_feature":"⚙️"}'
CHANGE_LOG_LATEST=$(cat <<'EOF_CHANGE_LOG_LATEST'
• ⚡ Compact embedded compressed payload declarations onto single-line base64 strings so the installer no longer wastes bytes on wrapped payload line breaks.
• ⚡ Further reduced the installer size by max-gzip packing the embedded control and updater Python payloads behind tiny runtime unpackers while preserving the generated files written on install/update
• ⚡ Reduced the shipped installer size by compressing the embedded admin web UI payload and enabling stronger safe JavaScript minification while preserving the existing panel behavior.
EOF_CHANGE_LOG_LATEST
)
CLUB_3090_VERSION='{"release":"v0.8.6-1-ga74398d","released_at":"2026-05-26T17:54:31-03:00","commit":"a74398d64f1748be0febccc727dc908b25e792fd","compatible_release_patterns":["v0.8.6*","v0.8.6-1-ga74398d*"],"compatible_commit_prefixes":["a74398d64f1748be0febccc727dc908b25e792fd","a74398d"]}'
CLUB3090_SELF_UPDATE_REPO_URL="${CLUB3090_SELF_UPDATE_REPO_URL:-https://github.com/VykosX/club-3090-server.git}"
CLUB3090_SELF_UPDATE_REF="${CLUB3090_SELF_UPDATE_REF:-refs/heads/master}"
CLUB3090_SELF_UPDATE_BRANCH="${CLUB3090_SELF_UPDATE_BRANCH:-master}"
CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE="${CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE:-https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/install-club3090-server.sh}"
CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE="${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE:-https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/build/metadata.json}"
if [[ "${CLUB3090_SELF_UPDATE_REPO_URL}" != "https://github.com/VykosX/club-3090-server.git" ]]; then
  CLUB3090_SELF_UPDATE_REPO_URL="https://github.com/VykosX/club-3090-server.git"
fi
if [[ "${CLUB3090_SELF_UPDATE_REF}" != "refs/heads/master" ]]; then
  CLUB3090_SELF_UPDATE_REF="refs/heads/master"
fi
if [[ "${CLUB3090_SELF_UPDATE_BRANCH}" != "master" ]]; then
  CLUB3090_SELF_UPDATE_BRANCH="master"
fi
if [[ "${CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE}" != *"{sha}"* ]] || [[ "${CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE}" != https://raw.githubusercontent.com/VykosX/club-3090-server/*/install-club3090-server.sh ]]; then
  CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE="https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/install-club3090-server.sh"
fi
if [[ "${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE}" != *"{sha}"* ]] || [[ "${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE}" != https://raw.githubusercontent.com/VykosX/club-3090-server/*/build/metadata.json ]]; then
  CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE="https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/build/metadata.json"
fi

printf 'Club-3090 Server Installer %s\n' "${SCRIPT_VERSION}"

# club-3090 headless server/control installer
# Install:
#   curl -fsSL https://tinyurl.com/club-3090-webserver | bash
# Update control/admin/proxy/console services only:
#   curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- --update
# Migrate an existing /opt/ai/club-3090 checkout to a fresh upstream clone:
#   curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- --migrate
# Restart a broken/incomplete migration from scratch:
#   curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- --migrate restart
# Custom admin/proxy ports:
#   bash install-club3090-server.sh --ports 18008:18009
# Save a Hugging Face token for setup and later admin-panel downloads:
#   bash install-club3090-server.sh --hf-token hf_xxx
# Enable loopback-only local automation API:
#   bash install-club3090-server.sh --local-automation
# Overrides:
#   CLUB3090_DIR=/path/to/club-3090 DEFAULT_MODE=vllm/dual-dflash HF_TOKEN=hf_xxx bash install-club3090-server.sh
# If DEFAULT_MODE is unset, the installer auto-selects:
#   - vllm/default on 0-1 detected GPUs
#   - vllm/dual on 2+ detected GPUs

CONTROL_DIR="/opt/club3090-control"
NETWORK_STATE_FILE="${CONTROL_DIR}/network_state.json"
TLS_CERT_FILE="${CONTROL_DIR}/tls.crt"
TLS_KEY_FILE="${CONTROL_DIR}/tls.key"
TAILSCALE_CERT_FILE="${CONTROL_DIR}/tailscale.crt"
TAILSCALE_KEY_FILE="${CONTROL_DIR}/tailscale.key"
HTTPS_HOST_FILE="${CONTROL_DIR}/https_host"
CADDYFILE_PATH="${CONTROL_DIR}/Caddyfile"
MIGRATION_STATE_FILE="${CONTROL_DIR}/migration-state.env"

ACTION="install"
ONLINE_MODE="disable"
ONLINE_TLS_MODE="disable"
ONLINE_TLS_CERT_IP_MODE="disable"
ONLINE_TLS_TAILSCALE_MODE="disable"
ONLINE_TLS_TAILSCALE_FUNNEL_MODE="disable"
LOCAL_AUTOMATION_MODE="disable"
PORTS_SPEC=""
HF_TOKEN_INPUT=""
MIGRATION_FORCE_RESTART=0
REQUESTED_CLUB3090_COMMIT=""
UPSTREAM_REPO_URL="${CLUB3090_REPO_URL:-https://github.com/noonghunna/club-3090.git}"
while [[ "$#" -gt 0 ]]; do
  case "${1}" in
    --update)
      ACTION="update"
      shift
      ;;
    --migrate)
      ACTION="migrate"
      if [[ "$#" -ge 2 && "${2}" == "restart" ]]; then
        MIGRATION_FORCE_RESTART=1
        shift 2
      else
        shift
      fi
      ;;
    --install)
      ACTION="install"
      shift
      ;;
    --online)
      ONLINE_MODE="enable"
      shift
      ;;
    --use-https|use-https)
      ONLINE_TLS_MODE="enable"
      shift
      ;;
    --use-https:cert-ip|use-https:cert-ip)
      ONLINE_TLS_MODE="enable"
      ONLINE_TLS_CERT_IP_MODE="enable"
      shift
      ;;
    --use-https:tailscale|use-https:tailscale)
      ONLINE_TLS_MODE="enable"
      ONLINE_TLS_TAILSCALE_MODE="enable"
      shift
      ;;
    --use-https:tailscale:enable-funnel|use-https:tailscale:enable-funnel)
      ONLINE_TLS_MODE="enable"
      ONLINE_TLS_TAILSCALE_MODE="enable"
      ONLINE_TLS_TAILSCALE_FUNNEL_MODE="enable"
      shift
      ;;
    --local-automation)
      LOCAL_AUTOMATION_MODE="enable"
      shift
      ;;
    --hf-token|--hf_token)
      if [[ "$#" -lt 2 ]]; then
        echo "ERROR: --hf-token requires a value." >&2
        exit 1
      fi
      HF_TOKEN_INPUT="${2}"
      shift 2
      ;;
    --ports)
      if [[ "$#" -lt 2 ]]; then
        echo "ERROR: --ports requires a value like 8008:8009" >&2
        exit 1
      fi
      PORTS_SPEC="${2}"
      shift 2
      ;;
    --club3090-commit)
      if [[ "$#" -lt 2 ]]; then
        echo "ERROR: --club3090-commit requires a commit id." >&2
        exit 1
      fi
      REQUESTED_CLUB3090_COMMIT="${2}"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown argument: ${1}" >&2
      exit 1
      ;;
  esac
done

ADMIN_PORT="${CLUB3090_ADMIN_PORT:-8008}"
PROXY_PORT="${CLUB3090_PROXY_PORT:-8009}"
LOCAL_API_PORT="${CLUB3090_LOCAL_API_PORT:-10881}"

read_existing_service_port() {
  local key="$1"
  local unit="/etc/systemd/system/club3090-control.service"
  if [[ -r "${unit}" ]]; then
    sed -n "s/^Environment=${key}=//p" "${unit}" 2>/dev/null | head -n 1
  fi
}

read_existing_server_flag() {
  local key="$1"
  local path="${CONTROL_DIR}/server_config.json"
  if [[ -r "${path}" ]] && command -v python3 >/dev/null 2>&1; then
    python3 - "$path" "$key" <<'PYFLAG' 2>/dev/null
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
except Exception:
    sys.exit(0)
val = obj.get(key)
if isinstance(val, bool):
    print("true" if val else "false")
elif val is not None:
    print(val)
PYFLAG
  fi
}

read_existing_service_env() {
  local key="$1"
  local unit="$2"
  if [[ -r "${unit}" ]]; then
    sed -n "s/^Environment=${key}=//p" "${unit}" 2>/dev/null | head -n 1
  fi
}

existing_https_topology_detected() {
  local control_unit="/etc/systemd/system/club3090-control.service"
  local caddy_unit="/etc/systemd/system/club3090-caddy.service"
  local bind_host=""
  local bind_port=""
  if [[ -r "${caddy_unit}" || -r "${CADDYFILE_PATH}" ]]; then
    return 0
  fi
  bind_host="$(read_existing_service_env "CLUB3090_ADMIN_BIND_HOST" "${control_unit}" || true)"
  bind_port="$(read_existing_service_env "CLUB3090_ADMIN_BIND_PORT" "${control_unit}" || true)"
  if [[ "${bind_host}" == "127.0.0.1" ]]; then
    return 0
  fi
  if [[ -n "${bind_port}" && "${bind_port}" != "${ADMIN_PORT}" ]]; then
    return 0
  fi
  return 1
}

read_repo_env_value() {
  local path="$1"
  local key="$2"
  if [[ -r "${path}" ]] && command -v python3 >/dev/null 2>&1; then
    python3 - "$path" "$key" <<'PYENVREAD' 2>/dev/null
import sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                print(v.strip())
                break
except Exception:
    pass
PYENVREAD
  fi
}

if [[ ( "${ACTION}" == "update" || "${ACTION}" == "migrate" ) && -z "${PORTS_SPEC}" ]]; then
  existing_admin_port="$(read_existing_service_port CLUB3090_ADMIN_PORT || true)"
  existing_proxy_port="$(read_existing_service_port CLUB3090_PROXY_PORT || true)"
  existing_local_api_port="$(read_existing_service_port CLUB3090_LOCAL_API_PORT || true)"
  if [[ "${existing_admin_port:-}" =~ ^[0-9]+$ ]]; then
    ADMIN_PORT="${existing_admin_port}"
  fi
  if [[ "${existing_proxy_port:-}" =~ ^[0-9]+$ ]]; then
    PROXY_PORT="${existing_proxy_port}"
  fi
  if [[ "${existing_local_api_port:-}" =~ ^[0-9]+$ ]]; then
    LOCAL_API_PORT="${existing_local_api_port}"
  fi
fi

if [[ -n "${PORTS_SPEC}" ]]; then
  if [[ "${PORTS_SPEC}" =~ ^([0-9]{2,5}):([0-9]{2,5})$ ]]; then
    ADMIN_PORT="${BASH_REMATCH[1]}"
    PROXY_PORT="${BASH_REMATCH[2]}"
  else
    echo "ERROR: --ports must look like 8008:8009" >&2
    exit 1
  fi
fi

validate_port() {
  local p="$1"
  [[ "${p}" =~ ^[0-9]+$ ]] || return 1
  (( p >= 1 && p <= 65535 ))
}

if ! validate_port "${ADMIN_PORT}"; then
  echo "ERROR: Invalid admin port: ${ADMIN_PORT}" >&2
  exit 1
fi
if ! validate_port "${PROXY_PORT}"; then
  echo "ERROR: Invalid proxy port: ${PROXY_PORT}" >&2
  exit 1
fi
if [[ "${ADMIN_PORT}" == "${PROXY_PORT}" ]]; then
  echo "ERROR: Admin and proxy ports must be different." >&2
  exit 1
fi
if [[ "${ADMIN_PORT}" == "${LOCAL_API_PORT}" ]] || [[ "${PROXY_PORT}" == "${LOCAL_API_PORT}" ]]; then
  echo "ERROR: Admin, proxy, and local API ports must all be different." >&2
  exit 1
fi

choose_loopback_port() {
  local preferred="$1"
  shift
  local candidate
  local used_ports="$*"
  for candidate in "${preferred}" $((preferred + 1000)) $((preferred + 2000)) $((preferred + 10000)); do
    if validate_port "${candidate}"; then
      case " ${used_ports} " in
        *" ${candidate} "*) ;;
        *)
          if command -v ss >/dev/null 2>&1; then
            if ss -ltnH "( sport = :${candidate} )" 2>/dev/null | grep -q .; then
              continue
            fi
          fi
          printf '%s\n' "${candidate}"
          return 0
          ;;
      esac
    fi
  done
  return 1
}

CLUB3090_DIR="${CLUB3090_DIR:-/opt/ai/club-3090}"
DEFAULT_MODE="${DEFAULT_MODE:-}"
CONTROL_PY="${CONTROL_DIR}/control.py"
UPDATER_PY="${CONTROL_DIR}/updater.py"
FOLLOW_SH="${CONTROL_DIR}/follow-vllm-log.sh"
START_SH="${CONTROL_DIR}/start-vllm-last-mode.sh"
HEADLESS_X_SH="${CONTROL_DIR}/prepare-headless-x.sh"
ACTIVE_MODE_FILE="${CONTROL_DIR}/active_mode"
SELF_UPDATE_LOG_FILE="${CONTROL_DIR}/self-update.log"
SELF_UPDATE_STATE_FILE="${CONTROL_DIR}/self-update-state.json"
SELF_UPDATE_SECRET_FILE="${CONTROL_DIR}/self-update-secret"
SELF_UPDATE_SCRIPT_PATH="${CONTROL_DIR}/install-club3090-server.sh"
SELF_UPDATE_RELOAD_FLAG_FILE="${CONTROL_DIR}/self-update-reload-updater"
BASH_BIN="${BASH_BIN:-$(command -v bash || true)}"
if [[ -n "${PYTHON_BIN:-}" ]] && command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v "${PYTHON_BIN}")"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
REPO_ENV_FILE="${CLUB3090_DIR}/.env"
HF_TOKEN_VALUE="${HF_TOKEN_INPUT:-${HF_TOKEN:-}}"

if [[ -z "${HF_TOKEN_VALUE}" ]]; then
  existing_saved_hf_token="$(read_repo_env_value "${REPO_ENV_FILE}" "HF_TOKEN" || true)"
  if [[ -n "${existing_saved_hf_token:-}" ]]; then
    HF_TOKEN_VALUE="${existing_saved_hf_token}"
  fi
fi

if [[ -n "${HF_TOKEN_VALUE}" ]]; then
  export HF_TOKEN="${HF_TOKEN_VALUE}"
fi

if [[ "${ACTION}" == "update" || "${ACTION}" == "migrate" ]]; then
  existing_online_enabled="$(read_existing_server_flag "online_enabled" || true)"
  existing_https_enabled="$(read_existing_server_flag "https_enabled" || true)"
  existing_local_api_enabled="$(read_existing_server_flag "local_api_enabled" || true)"
  existing_https_host="$(cat "${HTTPS_HOST_FILE}" 2>/dev/null || true)"
  existing_https_topology="false"
  if existing_https_topology_detected; then
    existing_https_topology="true"
  fi
  if [[ "${ONLINE_MODE}" != "enable" && "${existing_online_enabled}" == "true" ]]; then
    ONLINE_MODE="enable"
  fi
  if [[ "${ONLINE_TLS_MODE}" != "enable" && ( "${existing_https_enabled}" == "true" || "${existing_https_topology}" == "true" ) ]]; then
    ONLINE_TLS_MODE="enable"
  fi
  if [[ "${ONLINE_MODE}" != "enable" && "${ONLINE_TLS_MODE}" == "enable" ]]; then
    ONLINE_MODE="enable"
  fi
  if [[ "${LOCAL_AUTOMATION_MODE}" != "enable" && "${existing_local_api_enabled}" == "true" ]]; then
    LOCAL_AUTOMATION_MODE="enable"
  fi
  if [[ "${ONLINE_TLS_MODE}" == "enable" && "${ONLINE_TLS_TAILSCALE_MODE}" != "enable" && "${existing_https_host}" == *.ts.net ]]; then
    ONLINE_TLS_TAILSCALE_MODE="enable"
  fi
fi

ONLINE_EFFECTIVE_ENABLED="false"
ONLINE_TLS_EFFECTIVE_ENABLED="false"
LOCAL_AUTOMATION_EFFECTIVE_ENABLED="false"
TAILSCALE_HTTPS_EFFECTIVE_ENABLED="false"
if [[ "${ONLINE_MODE}" == "enable" ]]; then
  ONLINE_EFFECTIVE_ENABLED="true"
fi
if [[ "${ONLINE_TLS_MODE}" == "enable" ]]; then
  ONLINE_TLS_EFFECTIVE_ENABLED="true"
fi
if [[ "${ONLINE_TLS_TAILSCALE_MODE}" == "enable" ]]; then
  TAILSCALE_HTTPS_EFFECTIVE_ENABLED="true"
fi
if [[ "${LOCAL_AUTOMATION_MODE}" == "enable" ]]; then
  LOCAL_AUTOMATION_EFFECTIVE_ENABLED="true"
fi
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" && "${ONLINE_EFFECTIVE_ENABLED}" != "true" ]]; then
  echo "ERROR: HTTPS can only be enabled together with --online." >&2
  exit 1
fi

CONTROL_ADMIN_BIND_HOST="0.0.0.0"
CONTROL_PROXY_BIND_HOST="0.0.0.0"
CONTROL_ADMIN_BIND_PORT="${ADMIN_PORT}"
CONTROL_PROXY_BIND_PORT="${PROXY_PORT}"
CONTROL_UPDATER_BIND_HOST="127.0.0.1"
CONTROL_UPDATER_BIND_PORT="${CLUB3090_UPDATER_BIND_PORT:-18010}"
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
  CONTROL_ADMIN_BIND_HOST="127.0.0.1"
  CONTROL_PROXY_BIND_HOST="127.0.0.1"
  CONTROL_ADMIN_BIND_PORT="$(choose_loopback_port 18008 "${ADMIN_PORT}" "${PROXY_PORT}" "${LOCAL_API_PORT}")"
  CONTROL_PROXY_BIND_PORT="$(choose_loopback_port 18009 "${ADMIN_PORT}" "${PROXY_PORT}" "${LOCAL_API_PORT}" "${CONTROL_ADMIN_BIND_PORT}")"
  if [[ -z "${CONTROL_ADMIN_BIND_PORT:-}" || -z "${CONTROL_PROXY_BIND_PORT:-}" || -z "${CONTROL_UPDATER_BIND_PORT:-}" ]]; then
    echo "ERROR: Could not allocate internal loopback ports for Caddy-backed HTTPS mode." >&2
    exit 1
  fi
fi
if [[ "${CONTROL_UPDATER_BIND_PORT}" == "${ADMIN_PORT}" || "${CONTROL_UPDATER_BIND_PORT}" == "${PROXY_PORT}" || "${CONTROL_UPDATER_BIND_PORT}" == "${LOCAL_API_PORT}" || "${CONTROL_UPDATER_BIND_PORT}" == "${CONTROL_ADMIN_BIND_PORT}" || "${CONTROL_UPDATER_BIND_PORT}" == "${CONTROL_PROXY_BIND_PORT}" ]]; then
  echo "ERROR: Self-update helper port ${CONTROL_UPDATER_BIND_PORT} conflicts with another configured service port." >&2
  exit 1
fi
if [[ -z "${CONTROL_UPDATER_BIND_PORT:-}" ]]; then
  echo "ERROR: Could not allocate a loopback port for the self-update helper service." >&2
  exit 1
fi

detect_gpu_count() {
  local count="${CLUB3090_GPU_COUNT_OVERRIDE:-}"
  if [[ -n "${count}" ]] && [[ "${count}" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "${count}"
    return 0
  fi
  if command -v nvidia-smi >/dev/null 2>&1; then
    count="$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits 2>/dev/null | awk 'NF{c++} END{print c+0}')"
    if [[ "${count}" =~ ^[0-9]+$ ]]; then
      printf '%s\n' "${count}"
      return 0
    fi
    count="$(nvidia-smi -L 2>/dev/null | awk '/^GPU [0-9]+:/{c++} END{print c+0}')"
    if [[ "${count}" =~ ^[0-9]+$ ]]; then
      printf '%s\n' "${count}"
      return 0
    fi
  fi
  printf '0\n'
}

GPU_COUNT="$(detect_gpu_count)"
AUTO_DEFAULT_MODE="vllm/default"
if [[ "${GPU_COUNT}" -gt 1 ]]; then
  AUTO_DEFAULT_MODE="vllm/dual"
fi

if [[ -z "${DEFAULT_MODE}" ]]; then
  DEFAULT_MODE="${AUTO_DEFAULT_MODE}"
fi

if [[ ! -d "${CLUB3090_DIR}" && "${ACTION}" != "install" && ! ( "${ACTION}" == "migrate" && "${MIGRATION_FORCE_RESTART}" == "1" ) ]]; then
  echo "ERROR: CLUB3090_DIR does not exist: ${CLUB3090_DIR}" >&2
  echo "Re-run with: CLUB3090_DIR=/actual/path/to/club-3090 bash install-club3090-server.sh" >&2
  exit 1
fi

if [[ ! -f "${CLUB3090_DIR}/scripts/switch.sh" && "${ACTION}" != "install" && ! ( "${ACTION}" == "migrate" && "${MIGRATION_FORCE_RESTART}" == "1" ) ]]; then
  echo "ERROR: Could not find ${CLUB3090_DIR}/scripts/switch.sh" >&2
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: This installer only supports Linux hosts." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: Could not read /etc/os-release to detect the Linux distribution." >&2
  exit 1
fi

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: sudo is required when not running as root." >&2
    exit 1
  fi
  SUDO=(sudo)
fi

request_root_permissions() {
  if [[ "${#SUDO[@]}" -eq 0 ]]; then
    return 0
  fi
  printf 'Requesting root permissions\n'
  if ! "${SUDO[@]}" -v; then
    echo "ERROR: Failed to obtain root permissions with sudo." >&2
    exit 1
  fi
}

request_root_permissions

log_step() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

log_done() {
  printf '[%s] done: %s\n' "$(date +%H:%M:%S)" "$*"
}

status_line() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

validate_upstream_checkout_layout() {
  local repo_dir="${1:-${CLUB3090_DIR}}"
  local missing=()
  local rel
  for rel in \
    "scripts/switch.sh" \
    "scripts/setup.sh" \
    "scripts/update.sh" \
    "scripts/launch.sh"; do
    if [[ ! -f "${repo_dir}/${rel}" ]]; then
      missing+=("${rel}")
    fi
  done
  if [[ ! -d "${repo_dir}/models" ]]; then
    missing+=("models/")
  fi
  if [[ "${#missing[@]}" -gt 0 ]]; then
    echo "ERROR: club-3090 checkout at ${repo_dir} is incomplete for this control layer." >&2
    printf 'Missing required upstream paths: %s\n' "$(IFS=', '; echo "${missing[*]}")" >&2
    exit 1
  fi
}

bootstrap_upstream_repo_for_install() {
  if [[ "${ACTION}" != "install" ]]; then
    return 0
  fi
  if [[ -f "${CLUB3090_DIR}/scripts/switch.sh" ]]; then
    return 0
  fi
  if [[ -d "${CLUB3090_DIR}" ]]; then
    echo "ERROR: ${CLUB3090_DIR} already exists but is missing scripts/switch.sh." >&2
    echo "Remove or repair that directory, or point CLUB3090_DIR at a valid club-3090 checkout." >&2
    exit 1
  fi
  local parent_dir owner_name owner_group
  parent_dir="$(dirname "${CLUB3090_DIR}")"
  owner_name="${SUDO_USER:-$(id -un)}"
  owner_group="$(id -gn "${owner_name}" 2>/dev/null || id -gn)"
  log_step "Cloning upstream club-3090 into ${CLUB3090_DIR}"
  "${SUDO[@]}" mkdir -p "${parent_dir}"
  if ! "${SUDO[@]}" env GIT_TERMINAL_PROMPT=0 git clone --progress "${UPSTREAM_REPO_URL}" "${CLUB3090_DIR}"; then
    echo "ERROR: Failed to clone ${UPSTREAM_REPO_URL} into ${CLUB3090_DIR}" >&2
    exit 1
  fi
  "${SUDO[@]}" chmod -R a+rX "${CLUB3090_DIR}" >/dev/null 2>&1 || true
  if [[ -d "${CLUB3090_DIR}/scripts" ]]; then
    "${SUDO[@]}" find "${CLUB3090_DIR}/scripts" -maxdepth 1 -type f -name '*.sh' -exec chmod 755 {} +
  fi
  "${SUDO[@]}" chown -R "${owner_name}:${owner_group}" "${CLUB3090_DIR}" >/dev/null 2>&1 || true
  validate_upstream_checkout_layout "${CLUB3090_DIR}"
}

bootstrap_upstream_repo_for_install

if [[ ! -d "${CLUB3090_DIR}" && ! ( "${ACTION}" == "migrate" && "${MIGRATION_FORCE_RESTART}" == "1" ) ]]; then
  echo "ERROR: CLUB3090_DIR does not exist: ${CLUB3090_DIR}" >&2
  exit 1
fi

if [[ ! -f "${CLUB3090_DIR}/scripts/switch.sh" && ! ( "${ACTION}" == "migrate" && "${MIGRATION_FORCE_RESTART}" == "1" ) ]]; then
  echo "ERROR: Could not find ${CLUB3090_DIR}/scripts/switch.sh" >&2
  exit 1
fi

validate_upstream_checkout_layout "${CLUB3090_DIR}"

restore_repo_for_forced_migration_restart() {
  if [[ "${ACTION}" != "migrate" || "${MIGRATION_FORCE_RESTART}" != "1" ]]; then
    return 0
  fi
  if [[ -d "${CLUB3090_DIR}" ]]; then
    return 0
  fi
  if [[ ! -r "${MIGRATION_STATE_FILE}" ]]; then
    return 0
  fi
  local backup_dir=""
  local parsed_dir=""
  set +u
  # shellcheck disable=SC1090
  . "${MIGRATION_STATE_FILE}"
  set -u
  backup_dir="${MIGRATION_BACKUP_DIR:-}"
  parsed_dir="${MIGRATION_REPO_DIR:-}"
  if [[ -n "${parsed_dir}" ]]; then
    CLUB3090_DIR="${parsed_dir}"
    REPO_ENV_FILE="${CLUB3090_DIR}/.env"
  fi
  if [[ -n "${backup_dir}" && -d "${backup_dir}" && ! -d "${CLUB3090_DIR}" ]]; then
    status_line "Forced migrate restart: restoring backed-up repo from ${backup_dir} to ${CLUB3090_DIR} before restarting"
    "${SUDO[@]}" mv "${backup_dir}" "${CLUB3090_DIR}"
  fi
}

restore_repo_for_forced_migration_restart

if [[ -z "${BASH_BIN}" ]]; then
  echo "ERROR: bash is required but was not found in PATH." >&2
  exit 1
fi

source /etc/os-release
OS_ID_LOWER="$(printf '%s' "${ID:-}" | tr '[:upper:]' '[:lower:]')"
OS_LIKE_LOWER="$(printf '%s' "${ID_LIKE:-}" | tr '[:upper:]' '[:lower:]')"
OS_FAMILY="unsupported"

case "${OS_ID_LOWER}" in
  arch|manjaro|endeavouros)
    OS_FAMILY="arch"
    ;;
  ubuntu|debian|linuxmint|pop)
    OS_FAMILY="debian"
    ;;
  *)
    if [[ "${OS_LIKE_LOWER}" == *arch* ]]; then
      OS_FAMILY="arch"
    elif [[ "${OS_LIKE_LOWER}" == *debian* ]] || [[ "${OS_LIKE_LOWER}" == *ubuntu* ]]; then
      OS_FAMILY="debian"
    fi
    ;;
esac

if [[ "${OS_FAMILY}" == "unsupported" ]]; then
  echo "ERROR: Unsupported distribution: ${PRETTY_NAME:-${ID:-unknown}}. Supported families: Arch and Ubuntu/Debian." >&2
  exit 1
fi

append_control_log_line() {
  local line
  line="$(date +'%Y-%m-%d %H:%M:%S') $*"
  printf '%s\n' "${line}"
  "${SUDO[@]}" mkdir -p "${CONTROL_DIR}" >/dev/null 2>&1 || true
  printf '%s\n' "${line}" | "${SUDO[@]}" tee -a "${CONTROL_DIR}/control.log" >/dev/null 2>&1 || true
  printf '%s\n' "${line}" | "${SUDO[@]}" tee -a "${CONTROL_DIR}/audit.log" >/dev/null 2>&1 || true
}

shell_quote() {
  printf '%q' "$1"
}

club3090_release_tag_for_backup() {
  local release raw sanitized
  raw="${CLUB_3090_VERSION:-}"
  release="$(printf '%s' "${raw}" | sed -n 's/.*"release"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  sanitized="$(printf '%s' "${release}" | tr ' /:\\' '_' | tr -cd 'A-Za-z0-9._-')"
  printf '%s' "${sanitized:-unknown-release}"
}

ensure_control_dir() {
  "${SUDO[@]}" mkdir -p "${CONTROL_DIR}" >/dev/null 2>&1 || true
}

migration_state_defaults() {
  MIGRATION_STATUS=""
  MIGRATION_RUN_ID=""
  MIGRATION_STARTED_AT=""
  MIGRATION_UPDATED_AT=""
  MIGRATION_LAST_STEP=""
  MIGRATION_REMOTE_HEAD=""
  MIGRATION_REPO_URL=""
  MIGRATION_REPO_DIR=""
  MIGRATION_BACKUP_DIR=""
  MIGRATION_REPO_RENAMED=0
  MIGRATION_REPO_CLONED=0
  MIGRATION_ASSETS_MERGED=0
  MIGRATION_BOOTSTRAP_INVENTORY_DONE=0
  MIGRATION_SETUP_DONE=0
  MIGRATION_POST_SETUP_INVENTORY_DONE=0
  MIGRATION_UPDATE_DONE=0
  MIGRATION_FINAL_INVENTORY_DONE=0
  MIGRATION_SERVICES_REFRESHED=0
}

migration_state_defaults

load_migration_state() {
  migration_state_defaults
  if [[ ! -f "${MIGRATION_STATE_FILE}" ]]; then
    return 1
  fi
  set +u
  # shellcheck disable=SC1090
  . "${MIGRATION_STATE_FILE}"
  set -u
  return 0
}

save_migration_state() {
  ensure_control_dir
  "${SUDO[@]}" tee "${MIGRATION_STATE_FILE}" >/dev/null <<STATE
MIGRATION_STATUS=$(printf '%q' "${MIGRATION_STATUS}")
MIGRATION_RUN_ID=$(printf '%q' "${MIGRATION_RUN_ID}")
MIGRATION_STARTED_AT=$(printf '%q' "${MIGRATION_STARTED_AT}")
MIGRATION_UPDATED_AT=$(printf '%q' "${MIGRATION_UPDATED_AT}")
MIGRATION_LAST_STEP=$(printf '%q' "${MIGRATION_LAST_STEP}")
MIGRATION_REMOTE_HEAD=$(printf '%q' "${MIGRATION_REMOTE_HEAD}")
MIGRATION_REPO_URL=$(printf '%q' "${MIGRATION_REPO_URL}")
MIGRATION_REPO_DIR=$(printf '%q' "${MIGRATION_REPO_DIR}")
MIGRATION_BACKUP_DIR=$(printf '%q' "${MIGRATION_BACKUP_DIR}")
MIGRATION_REPO_RENAMED=$(printf '%q' "${MIGRATION_REPO_RENAMED}")
MIGRATION_REPO_CLONED=$(printf '%q' "${MIGRATION_REPO_CLONED}")
MIGRATION_ASSETS_MERGED=$(printf '%q' "${MIGRATION_ASSETS_MERGED}")
MIGRATION_BOOTSTRAP_INVENTORY_DONE=$(printf '%q' "${MIGRATION_BOOTSTRAP_INVENTORY_DONE}")
MIGRATION_SETUP_DONE=$(printf '%q' "${MIGRATION_SETUP_DONE}")
MIGRATION_POST_SETUP_INVENTORY_DONE=$(printf '%q' "${MIGRATION_POST_SETUP_INVENTORY_DONE}")
MIGRATION_UPDATE_DONE=$(printf '%q' "${MIGRATION_UPDATE_DONE}")
MIGRATION_FINAL_INVENTORY_DONE=$(printf '%q' "${MIGRATION_FINAL_INVENTORY_DONE}")
MIGRATION_SERVICES_REFRESHED=$(printf '%q' "${MIGRATION_SERVICES_REFRESHED}")
STATE
}

write_repo_env_value() {
  local path="$1"
  local key="$2"
  local value="$3"
  "${SUDO[@]}" "${PYTHON_BIN}" - "${path}" "${key}" "${value}" <<'PYENVWRITE'
import os, sys
path, key, value = sys.argv[1:4]
rows = []
found = False
if os.path.exists(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                k, _v = line.split("=", 1)
                if k.strip() == key:
                    rows.append(f"{key}={value}")
                    found = True
                    continue
            rows.append(line)
if not found:
    rows.append(f"{key}={value}")
os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
with open(path, "w", encoding="utf-8", newline="\n") as f:
    for line in rows:
        f.write(line.rstrip("\n") + "\n")
PYENVWRITE
}

persist_hf_token_if_available() {
  if [[ -z "${HF_TOKEN_VALUE}" ]]; then
    append_control_log_line "hf token: no token provided or previously saved; gated model downloads may require one later"
    return 0
  fi
  append_control_log_line "hf token: persisting token to ${REPO_ENV_FILE} for setup and later admin download reuse"
  write_repo_env_value "${REPO_ENV_FILE}" "HF_TOKEN" "${HF_TOKEN_VALUE}"
}

detect_upstream_remote_head() {
  git ls-remote "${UPSTREAM_REPO_URL}" HEAD 2>/dev/null | awk 'NR==1{print $1}'
}

git_repo_head() {
  local path="$1"
  if [[ ! -d "${path}/.git" ]]; then
    return 1
  fi
  git -C "${path}" rev-parse HEAD 2>/dev/null | head -n 1
}

migration_update_state() {
  local step="$1"
  MIGRATION_STATUS="in_progress"
  MIGRATION_LAST_STEP="${step}"
  MIGRATION_UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  save_migration_state
}

migration_mark_flag_done() {
  local flag_name="$1"
  local step="$2"
  printf -v "${flag_name}" '%s' "1"
  migration_update_state "${step}"
}

migration_pending_summary() {
  local pending=()
  [[ "${MIGRATION_REPO_RENAMED}" == "1" ]] || pending+=("rename")
  [[ "${MIGRATION_REPO_CLONED}" == "1" ]] || pending+=("clone")
  [[ "${MIGRATION_ASSETS_MERGED}" == "1" ]] || pending+=("asset-merge")
  [[ "${MIGRATION_BOOTSTRAP_INVENTORY_DONE}" == "1" ]] || pending+=("inventory-bootstrap")
  [[ "${MIGRATION_SETUP_DONE}" == "1" ]] || pending+=("setup")
  [[ "${MIGRATION_POST_SETUP_INVENTORY_DONE}" == "1" ]] || pending+=("inventory-post-setup")
  [[ "${MIGRATION_UPDATE_DONE}" == "1" ]] || pending+=("update.sh")
  [[ "${MIGRATION_FINAL_INVENTORY_DONE}" == "1" ]] || pending+=("inventory-final")
  if [[ "${#pending[@]}" -eq 0 ]]; then
    printf '%s' "none"
  else
    local joined=""
    local item
    for item in "${pending[@]}"; do
      if [[ -n "${joined}" ]]; then
        joined+=", "
      fi
      joined+="${item}"
    done
    printf '%s' "${joined}"
  fi
}

prepare_migration_state() {
  ensure_control_dir
  local remote_head=""
  remote_head="$(detect_upstream_remote_head || true)"
  if [[ "${MIGRATION_FORCE_RESTART}" == "1" ]]; then
    if [[ -f "${MIGRATION_STATE_FILE}" ]]; then
      append_control_log_line "migrate forced restart requested; deleting previous resume state at ${MIGRATION_STATE_FILE}"
      "${SUDO[@]}" rm -f "${MIGRATION_STATE_FILE}" >/dev/null 2>&1 || true
    fi
    migration_state_defaults
  fi
  if load_migration_state && [[ -n "${MIGRATION_STATUS}" && "${MIGRATION_STATUS}" != "complete" ]]; then
    if [[ -n "${remote_head}" && -n "${MIGRATION_REMOTE_HEAD}" && "${remote_head}" != "${MIGRATION_REMOTE_HEAD}" ]]; then
      append_control_log_line "migrate resume state found but upstream HEAD changed from ${MIGRATION_REMOTE_HEAD} to ${remote_head}; restarting unfinished migration phases"
      MIGRATION_REMOTE_HEAD="${remote_head}"
      MIGRATION_REPO_URL="${UPSTREAM_REPO_URL}"
      MIGRATION_REPO_DIR="${CLUB3090_DIR}"
      MIGRATION_REPO_CLONED=0
      MIGRATION_ASSETS_MERGED=0
      MIGRATION_BOOTSTRAP_INVENTORY_DONE=0
      MIGRATION_SETUP_DONE=0
      MIGRATION_POST_SETUP_INVENTORY_DONE=0
      MIGRATION_UPDATE_DONE=0
      MIGRATION_FINAL_INVENTORY_DONE=0
      MIGRATION_SERVICES_REFRESHED=0
      if [[ -n "${MIGRATION_BACKUP_DIR}" && -d "${MIGRATION_BACKUP_DIR}" && ! -d "${CLUB3090_DIR}" ]]; then
        MIGRATION_REPO_RENAMED=1
      fi
      migration_update_state "resume_restart_new_upstream_head"
    else
      append_control_log_line "migrate resume detected: last_step=${MIGRATION_LAST_STEP:-unknown}, backup=${MIGRATION_BACKUP_DIR:-unknown}, pending=$(migration_pending_summary)"
    fi
    return 0
  fi
  migration_state_defaults
  MIGRATION_STATUS="in_progress"
  MIGRATION_RUN_ID="$(date +%Y%m%d-%H%M%S)"
  MIGRATION_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  MIGRATION_UPDATED_AT="${MIGRATION_STARTED_AT}"
  MIGRATION_LAST_STEP="initialized"
  MIGRATION_REMOTE_HEAD="${remote_head}"
  MIGRATION_REPO_URL="${UPSTREAM_REPO_URL}"
  MIGRATION_REPO_DIR="${CLUB3090_DIR}"
  save_migration_state
  append_control_log_line "migrate state initialized: remote_head=${MIGRATION_REMOTE_HEAD:-unknown}, repo=${CLUB3090_DIR}"
}

finalize_migration_state_success() {
  MIGRATION_STATUS="complete"
  MIGRATION_LAST_STEP="complete"
  MIGRATION_UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  append_control_log_line "migrate completed successfully"
  "${SUDO[@]}" rm -f "${MIGRATION_STATE_FILE}" >/dev/null 2>&1 || true
  migration_state_defaults
}

migration_exit_trap() {
  local rc=$?
  if [[ "${ACTION}" == "migrate" ]]; then
    if [[ "${rc}" -ne 0 ]]; then
      ensure_control_dir
      load_migration_state || true
      if [[ -n "${MIGRATION_STARTED_AT}" ]]; then
        MIGRATION_STATUS="interrupted"
        MIGRATION_UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        save_migration_state
        status_line "Migration interrupted at step '${MIGRATION_LAST_STEP:-unknown}'. Resume later with --migrate."
        status_line "Remaining migration phases: $(migration_pending_summary)"
      fi
    fi
  fi
}

trap 'migration_exit_trap' EXIT
trap 'exit 130' INT TERM

run_live_command() {
  local label="$1"
  local cwd="$2"
  local command="$3"
  status_line "${label}: starting"
  status_line "${label}: command: ${command}"
  "${SUDO[@]}" env CLUB3090_STATUS_LABEL="${label}" CLUB3090_STATUS_CWD="${cwd}" CLUB3090_STATUS_COMMAND="${command}" CLUB3090_STATUS_HEARTBEAT_SECONDS="2" "${PYTHON_BIN}" - <<'PYRUNLIVE'
import os
import selectors
import subprocess
import sys
import time

label = os.environ.get("CLUB3090_STATUS_LABEL", "command")
cwd = os.environ.get("CLUB3090_STATUS_CWD") or None
command = os.environ.get("CLUB3090_STATUS_COMMAND", "")
heartbeat_seconds = float(os.environ.get("CLUB3090_STATUS_HEARTBEAT_SECONDS", "2") or "2")
start = time.time()
last_emit = start
env = os.environ.copy()
if cwd:
    env_path = os.path.join(cwd, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()
        except Exception:
            pass
proc = subprocess.Popen(
    ["bash", "-lc", command],
    cwd=cwd,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
selector = selectors.DefaultSelector()
assert proc.stdout is not None
fd = proc.stdout.fileno()
os.set_blocking(fd, False)
selector.register(proc.stdout, selectors.EVENT_READ)
buffer = ""

def stamp(message):
    print(f"[{time.strftime('%H:%M:%S')}] {label}: {message}", flush=True)

while True:
    events = selector.select(timeout=heartbeat_seconds)
    if events:
        for key, _mask in events:
            chunk = os.read(key.fd, 8192)
            if not chunk:
                continue
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.rstrip("\r")
                if line:
                    stamp(line)
                else:
                    stamp("")
                last_emit = time.time()
    else:
        if proc.poll() is None:
            elapsed = int(time.time() - start)
            idle = int(time.time() - last_emit)
            stamp(f"still running ({elapsed}s elapsed, {idle}s since last output)")
            last_emit = time.time()
    if proc.poll() is not None:
        try:
            remainder = os.read(fd, 8192)
        except BlockingIOError:
            remainder = b""
        if remainder:
            buffer += remainder.decode("utf-8", errors="replace")
        if buffer:
            for line in buffer.splitlines():
                stamp(line.rstrip("\r"))
            buffer = ""
        break

rc = proc.wait()
stamp(f"finished with exit code {rc} after {int(time.time() - start)}s")
sys.exit(rc)
PYRUNLIVE
}

count_tree_files() {
  local path="$1"
  if [[ ! -e "${path}" ]]; then
    printf '0\n'
    return 0
  fi
  find "${path}" -type f 2>/dev/null | wc -l | awk '{print $1}'
}

merge_dir_contents_logged() {
  local label="$1"
  local src="$2"
  local dst="$3"
  if [[ ! -d "${src}" ]]; then
    append_control_log_line "${label}: source missing, skipping (${src})"
    return 0
  fi
  local file_count
  file_count="$(count_tree_files "${src}")"
  migration_update_state "merge_${label}"
  append_control_log_line "${label}: merging ${file_count} files from ${src} into ${dst}"
  run_live_command "${label}" "/" "mkdir -p $(shell_quote "${dst}") && cp -a $(shell_quote "${src}")/. $(shell_quote "${dst}")/"
}

quarantine_non_git_genesis_dirs() {
  local quarantine_root="${MIGRATION_BACKUP_DIR:-${CLUB3090_DIR}-migrate-artifacts}/preserved-genesis"
  local genesis_dir
  local rel
  local dest
  while IFS= read -r genesis_dir; do
    [[ -n "${genesis_dir}" ]] || continue
    if [[ -d "${genesis_dir}/.git" ]]; then
      append_control_log_line "genesis quarantine: keeping existing git checkout ${genesis_dir}"
      continue
    fi
    rel="${genesis_dir#"${CLUB3090_DIR}/"}"
    dest="${quarantine_root}/${rel//\//__}.pre-setup"
    append_control_log_line "genesis quarantine: moving non-git directory ${genesis_dir} to ${dest}"
    run_live_command "genesis quarantine" "/" "mkdir -p $(shell_quote "$(dirname "${dest}")") && mv $(shell_quote "${genesis_dir}") $(shell_quote "${dest}")"
  done < <(find "${CLUB3090_DIR}/models" -type d -path '*/vllm/patches/genesis' 2>/dev/null || true)
}

merge_dir_contents() {
  local src="$1"
  local dst="$2"
  if [[ ! -d "${src}" ]]; then
    return 0
  fi
  "${SUDO[@]}" mkdir -p "${dst}"
  "${SUDO[@]}" cp -a "${src}/." "${dst}/"
}

merge_env_files() {
  local dest="$1"
  local src="$2"
  local old_root="${3:-}"
  local new_root="${4:-}"
  if [[ ! -f "${src}" ]]; then
    return 0
  fi
  "${SUDO[@]}" "${PYTHON_BIN}" - "${dest}" "${src}" "${old_root}" "${new_root}" <<'PYMERGEENV'
import os, sys
dest, src, old_root, new_root = sys.argv[1:5]
def parse(path):
    data = {}
    if not os.path.exists(path):
        return data
    for raw in open(path, "r", encoding="utf-8", errors="replace").read().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            data[key] = value.strip()
    return data
def rewrite_repo_local_paths(data):
    if not old_root or not new_root:
        return data
    prefix = old_root.rstrip("/") + "/"
    for key, value in list(data.items()):
        text = str(value or "").strip()
        if key in {"MODEL_DIR", "HF_HOME", "TRANSFORMERS_CACHE"} and text.startswith(prefix):
            data[key] = new_root.rstrip("/") + "/" + text[len(prefix):]
    return data
merged = parse(dest)
incoming = rewrite_repo_local_paths(parse(src))
merged.update(incoming)
os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
with open(dest, "w", encoding="utf-8", newline="\n") as f:
    for key in sorted(merged):
        f.write(f"{key}={merged[key]}\n")
PYMERGEENV
}

normalize_migrated_model_assets() {
  local model_dir_root="$1"
  local legacy_qwen_root="${model_dir_root}/qwen3.6-27b"
  local canonical_qwen_root="${model_dir_root}/qwen3.6-27b-gguf"
  local root_mmproj="${canonical_qwen_root}/mmproj-F16.gguf"
  local source_mmproj=""
  [[ -n "${model_dir_root}" && -d "${model_dir_root}" ]] || return 0
  if [[ -d "${legacy_qwen_root}" ]]; then
    append_control_log_line "migrate asset normalize: mirroring legacy ${legacy_qwen_root} into ${canonical_qwen_root}"
    "${SUDO[@]}" mkdir -p "${canonical_qwen_root}"
    "${SUDO[@]}" cp -a "${legacy_qwen_root}/." "${canonical_qwen_root}/" >/dev/null 2>&1 || true
  fi
  if [[ -d "${canonical_qwen_root}" && ! -f "${root_mmproj}" ]]; then
    while IFS= read -r source_mmproj; do
      [[ -n "${source_mmproj}" ]] || continue
      append_control_log_line "migrate asset normalize: restoring root mmproj-F16.gguf from ${source_mmproj}"
      "${SUDO[@]}" mkdir -p "${canonical_qwen_root}"
      if ! "${SUDO[@]}" ln -f "${source_mmproj}" "${root_mmproj}" >/dev/null 2>&1; then
        "${SUDO[@]}" cp -f "${source_mmproj}" "${root_mmproj}" >/dev/null 2>&1 || true
      fi
      break
    done < <(find "${canonical_qwen_root}" -mindepth 2 -maxdepth 2 -type f -name 'mmproj-F16.gguf' 2>/dev/null | sort || true)
  fi
}

rebuild_runtime_inventory_cli() {
  local phase_flag="${1:-}"
  local phase_step="${2:-inventory_rebuild}"
  if [[ "${ACTION}" == "migrate" || -n "${phase_flag}" ]]; then
    migration_update_state "${phase_step}"
  fi
  append_control_log_line "runtime inventory rebuild starting (${phase_step})"
  run_live_command "runtime inventory rebuild" "/" "env CLUB3090_DIR=$(shell_quote "${CLUB3090_DIR}") $(shell_quote "${PYTHON_BIN}") $(shell_quote "${CONTROL_PY}") --rebuild-inventory"
  append_control_log_line "runtime inventory rebuild finished (${phase_step})"
  if [[ -n "${phase_flag}" ]]; then
    migration_mark_flag_done "${phase_flag}" "${phase_step}_complete"
  fi
}

collect_required_setup_commands() {
  "${SUDO[@]}" env CLUB3090_DIR="${CLUB3090_DIR}" DEFAULT_MODE="${DEFAULT_MODE}" "${PYTHON_BIN}" - "${CONTROL_DIR}" <<'PYSETUPCMDS'
import json, os, sys
control_dir = sys.argv[1]
inventory_path = os.path.join(control_dir, "runtime_inventory.json")
instances_path = os.path.join(control_dir, "instances.json")
active_mode_path = os.path.join(control_dir, "active_mode")
last_good_mode_path = os.path.join(control_dir, "last_good_mode")
default_mode = str(os.environ.get("DEFAULT_MODE") or "").strip()
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
def read_text(path):
    try:
        return open(path, "r", encoding="utf-8").read().strip()
    except Exception:
        return ""
inventory = load_json(inventory_path, {})
variants = list(inventory.get("variants") or [])
lookup = {}
for variant in variants:
    for key in (variant.get("variant_id"), variant.get("upstream_tag"), variant.get("compose_rel_path")):
        if key:
            lookup[str(key)] = variant
modes = []
if default_mode:
    modes.append(default_mode)
for value in (read_text(active_mode_path), read_text(last_good_mode_path)):
    if value:
        modes.append(value)
for row in load_json(instances_path, []):
    if isinstance(row, dict) and row.get("enabled") and row.get("mode"):
        modes.append(str(row.get("mode")))
commands = []
seen = set()
for mode in modes:
    variant = lookup.get(str(mode))
    if not variant:
        continue
    command = str(variant.get("setup_command") or variant.get("install_command") or "").strip()
    if command and command not in seen:
        seen.add(command)
        commands.append(command)
for command in commands:
    print(command)
PYSETUPCMDS
}

run_required_setup_commands() {
  local commands=()
  local action_label="${ACTION:-install}"
  mapfile -t commands < <(collect_required_setup_commands)
  if [[ "${#commands[@]}" -eq 0 ]]; then
    append_control_log_line "${action_label} setup: no required setup commands detected from runtime inventory"
    if [[ "${ACTION}" == "migrate" ]]; then
      migration_mark_flag_done "MIGRATION_SETUP_DONE" "setup_skipped_no_commands"
    fi
    return 0
  fi
  local cmd
  local idx=0
  local total="${#commands[@]}"
  for cmd in "${commands[@]}"; do
    [[ -n "${cmd}" ]] || continue
    idx=$((idx + 1))
    if [[ "${ACTION}" == "migrate" ]]; then
      migration_update_state "setup_command_${idx}_of_${total}"
    fi
    append_control_log_line "${action_label} setup command: ${cmd}"
    run_live_command "model setup ${idx}/${total}" "${CLUB3090_DIR}" "${cmd}"
  done
  if [[ "${ACTION}" == "migrate" ]]; then
    migration_mark_flag_done "MIGRATION_SETUP_DONE" "setup_complete"
  fi
}

migrate_repo_checkout() {
  local timestamp local_head remote_head backup_dir repo_head_after_clone partial_dir
  local_head="$(git_repo_head "${CLUB3090_DIR}" || true)"
  remote_head="${MIGRATION_REMOTE_HEAD:-}"
  if [[ -z "${MIGRATION_BACKUP_DIR}" ]]; then
    timestamp="$(date +%Y%m%d-%H%M%S)"
    MIGRATION_BACKUP_DIR="${CLUB3090_DIR}-backup_$(club3090_release_tag_for_backup)_${timestamp}"
    save_migration_state
  fi
  backup_dir="${MIGRATION_BACKUP_DIR}"

  if [[ "${MIGRATION_REPO_RENAMED}" != "1" && -n "${local_head}" && -n "${remote_head}" && "${local_head}" == "${remote_head}" ]]; then
    append_control_log_line "migrate checkout replacement skipped: local repo HEAD already matches upstream (${local_head})"
    MIGRATION_REPO_RENAMED=1
    MIGRATION_REPO_CLONED=1
    MIGRATION_ASSETS_MERGED=1
    migration_update_state "local_checkout_already_current"
    return 0
  fi

  if [[ "${MIGRATION_REPO_RENAMED}" != "1" ]]; then
    if [[ ! -d "${CLUB3090_DIR}" ]]; then
      echo "ERROR: --migrate requires an existing checkout at ${CLUB3090_DIR}" >&2
      exit 1
    fi
    if [[ -e "${backup_dir}" ]]; then
      echo "ERROR: backup path already exists: ${backup_dir}" >&2
      exit 1
    fi
    migration_update_state "backup_path_selected"
    append_control_log_line "migrate backup path chosen: ${backup_dir}"
    run_live_command "migrate rename existing checkout" "/" "mv $(shell_quote "${CLUB3090_DIR}") $(shell_quote "${backup_dir}")"
    migration_mark_flag_done "MIGRATION_REPO_RENAMED" "rename_complete"
    append_control_log_line "migrate rename success: ${CLUB3090_DIR} -> ${backup_dir}"
  else
    append_control_log_line "migrate rename step already complete; using backup at ${backup_dir}"
  fi

  if [[ ! -d "${backup_dir}" ]]; then
    echo "ERROR: migration backup directory is missing: ${backup_dir}" >&2
    exit 1
  fi

  if [[ "${MIGRATION_REPO_CLONED}" != "1" ]]; then
    if repo_head_after_clone="$(git_repo_head "${CLUB3090_DIR}" || true)" && [[ -n "${repo_head_after_clone}" ]]; then
      append_control_log_line "migrate clone step already satisfied by existing checkout at ${CLUB3090_DIR} (${repo_head_after_clone})"
      migration_mark_flag_done "MIGRATION_REPO_CLONED" "clone_already_present"
    else
      if [[ -e "${CLUB3090_DIR}" ]]; then
        partial_dir="${CLUB3090_DIR}-partial_$(date +%Y%m%d-%H%M%S)"
        append_control_log_line "migrate found partial clone target at ${CLUB3090_DIR}; moving it aside to ${partial_dir}"
        run_live_command "migrate quarantine partial clone" "/" "mv $(shell_quote "${CLUB3090_DIR}") $(shell_quote "${partial_dir}")"
      fi
      migration_update_state "clone_fresh_upstream_repo"
      run_live_command "migrate git clone" "/" "GIT_TERMINAL_PROMPT=0 git clone --progress $(shell_quote "${UPSTREAM_REPO_URL}") $(shell_quote "${CLUB3090_DIR}")"
      if [[ -n "${REQUESTED_CLUB3090_COMMIT}" ]]; then
        append_control_log_line "migrate target commit requested: ${REQUESTED_CLUB3090_COMMIT}"
        run_live_command "migrate checkout target commit" "${CLUB3090_DIR}" "git checkout --detach $(shell_quote "${REQUESTED_CLUB3090_COMMIT}")"
      fi
      "${SUDO[@]}" chmod -R a+rX "${CLUB3090_DIR}" >/dev/null 2>&1 || true
      repo_head_after_clone="$(git_repo_head "${CLUB3090_DIR}" || true)"
      validate_upstream_checkout_layout "${CLUB3090_DIR}"
      append_control_log_line "migrate clone success: ${UPSTREAM_REPO_URL} -> ${CLUB3090_DIR} (${repo_head_after_clone:-unknown-head})"
      migration_mark_flag_done "MIGRATION_REPO_CLONED" "clone_complete"
    fi
  else
    append_control_log_line "migrate clone step already complete for ${CLUB3090_DIR}"
  fi

  if [[ "${MIGRATION_ASSETS_MERGED}" != "1" ]]; then
    migration_update_state "asset_merge_start"
    merge_dir_contents_logged "migrate models-cache merge" "${backup_dir}/models-cache" "${CLUB3090_DIR}/models-cache"
    if [[ -f "${backup_dir}/.env" ]]; then
      append_control_log_line "migrate env merge: merging ${backup_dir}/.env into ${CLUB3090_DIR}/.env"
      merge_env_files "${CLUB3090_DIR}/.env" "${backup_dir}/.env" "${backup_dir}" "${CLUB3090_DIR}"
    else
      append_control_log_line "migrate env merge: no .env found in ${backup_dir}, skipping"
    fi
    local backup_model_dir_raw backup_model_dir_resolved new_model_dir_raw new_model_dir_resolved
    backup_model_dir_raw="$(read_repo_env_value "${backup_dir}/.env" "MODEL_DIR" || true)"
    if [[ -n "${backup_model_dir_raw}" ]]; then
      if [[ "${backup_model_dir_raw}" = /* ]]; then
        if [[ "${backup_model_dir_raw}" == "${CLUB3090_DIR}"* ]]; then
          backup_model_dir_resolved="${backup_dir}${backup_model_dir_raw#"${CLUB3090_DIR}"}"
        else
          backup_model_dir_resolved="${backup_model_dir_raw}"
        fi
      else
        backup_model_dir_resolved="$(cd "${backup_dir}" && cd "${backup_model_dir_raw}" 2>/dev/null && pwd || true)"
      fi
    else
      backup_model_dir_resolved="${backup_dir}/models-cache"
    fi
    new_model_dir_raw="$(read_repo_env_value "${CLUB3090_DIR}/.env" "MODEL_DIR" || true)"
    if [[ -n "${new_model_dir_raw}" ]]; then
      if [[ "${new_model_dir_raw}" = /* ]]; then
        new_model_dir_resolved="${new_model_dir_raw}"
      else
        new_model_dir_resolved="$(cd "${CLUB3090_DIR}" && cd "${new_model_dir_raw}" 2>/dev/null && pwd || true)"
      fi
    else
      new_model_dir_resolved="${CLUB3090_DIR}/models-cache"
    fi
    append_control_log_line "migrate model-dir resolution: backup_raw=${backup_model_dir_raw:-<default>} backup_resolved=${backup_model_dir_resolved:-<unresolved>} new_raw=${new_model_dir_raw:-<default>} new_resolved=${new_model_dir_resolved:-<unresolved>}"
    if [[ -n "${backup_model_dir_resolved:-}" && -d "${backup_model_dir_resolved}" && -n "${new_model_dir_resolved:-}" ]]; then
      if [[ "${backup_model_dir_resolved}" != "${new_model_dir_resolved}" ]]; then
        merge_dir_contents_logged "migrate effective model dir merge" "${backup_model_dir_resolved}" "${new_model_dir_resolved}"
      else
        append_control_log_line "migrate effective model dir merge skipped: source and target resolve to the same path (${new_model_dir_resolved})"
      fi
    else
      append_control_log_line "migrate effective model dir merge skipped: source missing or unresolved"
    fi
    while IFS= read -r cache_dir; do
      [[ -n "${cache_dir}" ]] || continue
      if [[ "${cache_dir}" == *"/patches/genesis/"* || "${cache_dir}" == *"/patches/genesis" ]]; then
        append_control_log_line "migrate cache merge skipped for genesis patch tree: ${cache_dir}"
        continue
      fi
      local rel
      rel="${cache_dir#"${backup_dir}/"}"
      merge_dir_contents_logged "migrate cache merge ${rel}" "${cache_dir}" "${CLUB3090_DIR}/${rel}"
    done < <(find "${backup_dir}/models" -type d -path '*/cache' 2>/dev/null || true)
    normalize_migrated_model_assets "${CLUB3090_DIR}/models-cache"
    if [[ -n "${new_model_dir_resolved:-}" && "${new_model_dir_resolved}" != "${CLUB3090_DIR}/models-cache" ]]; then
      normalize_migrated_model_assets "${new_model_dir_resolved}"
    fi
    append_control_log_line "migrate asset merge summary: repo-local models-cache preserved, effective MODEL_DIR mirrored, compose cache directories copied, .env merged if present"
    migration_mark_flag_done "MIGRATION_ASSETS_MERGED" "asset_merge_complete"
  else
    append_control_log_line "migrate asset merge step already complete"
  fi
}

APT_UPDATED=0
PACMAN_SYNCED=0
install_packages() {
  if [[ "$#" -eq 0 ]]; then
    return 0
  fi
  case "${OS_FAMILY}" in
    arch)
      if [[ "${PACMAN_SYNCED}" -eq 0 ]]; then
        "${SUDO[@]}" pacman -Sy --noconfirm
        PACMAN_SYNCED=1
      fi
      "${SUDO[@]}" pacman -S --needed --noconfirm "$@"
      ;;
    debian)
      if [[ "${APT_UPDATED}" -eq 0 ]]; then
        "${SUDO[@]}" apt-get update
        APT_UPDATED=1
      fi
      DEBIAN_FRONTEND=noninteractive "${SUDO[@]}" apt-get install -y "$@"
      ;;
  esac
}

install_packages_with_timeout() {
  local timeout_seconds="$1"
  shift
  if [[ "$#" -eq 0 ]]; then
    return 0
  fi
  case "${OS_FAMILY}" in
    arch)
      if [[ "${PACMAN_SYNCED}" -eq 0 ]]; then
        if command -v timeout >/dev/null 2>&1; then
          timeout --foreground --kill-after=15s "${timeout_seconds}s" "${SUDO[@]}" pacman -Sy --noconfirm
        else
          "${SUDO[@]}" pacman -Sy --noconfirm
        fi
        PACMAN_SYNCED=1
      fi
      if command -v timeout >/dev/null 2>&1; then
        timeout --foreground --kill-after=15s "${timeout_seconds}s" "${SUDO[@]}" pacman -S --needed --noconfirm "$@"
      else
        "${SUDO[@]}" pacman -S --needed --noconfirm "$@"
      fi
      ;;
    debian)
      if [[ "${APT_UPDATED}" -eq 0 ]]; then
        if command -v timeout >/dev/null 2>&1; then
          timeout --foreground --kill-after=15s "${timeout_seconds}s" "${SUDO[@]}" apt-get update
        else
          "${SUDO[@]}" apt-get update
        fi
        APT_UPDATED=1
      fi
      if command -v timeout >/dev/null 2>&1; then
        DEBIAN_FRONTEND=noninteractive timeout --foreground --kill-after=15s "${timeout_seconds}s" "${SUDO[@]}" apt-get install -y "$@"
      else
        DEBIAN_FRONTEND=noninteractive "${SUDO[@]}" apt-get install -y "$@"
      fi
      ;;
  esac
}

install_aur_package_if_possible() {
  local pkg="$1"
  if command -v yay >/dev/null 2>&1; then
    yay -S --needed --noconfirm "${pkg}"
    return $?
  fi
  if command -v paru >/dev/null 2>&1; then
    paru -S --needed --noconfirm "${pkg}"
    return $?
  fi
  return 1
}

require_command_after_install() {
  local cmd="$1"
  local why="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    return 0
  fi
  echo "ERROR: Required dependency '${cmd}' is still missing after installation attempts. ${why}" >&2
  exit 1
}

ensure_command_or_install() {
  local cmd="$1"
  local description="$2"
  shift 2
  if command -v "${cmd}" >/dev/null 2>&1; then
    return 0
  fi
  echo "${description}"
  if ! install_packages "$@"; then
    echo "WARNING: Failed to install packages for ${cmd}. Continuing, but related features may be unavailable." >&2
    return 1
  fi
  command -v "${cmd}" >/dev/null 2>&1
}

ensure_command_or_install_with_timeout() {
  local cmd="$1"
  local timeout_seconds="$2"
  local description="$3"
  shift 3
  if command -v "${cmd}" >/dev/null 2>&1; then
    return 0
  fi
  echo "${description}"
  if ! install_packages_with_timeout "${timeout_seconds}" "$@"; then
    echo "WARNING: Timed out or failed while installing packages for ${cmd}. Continuing, but related features may be unavailable." >&2
    return 1
  fi
  command -v "${cmd}" >/dev/null 2>&1
}

ensure_pamtester_available() {
  if command -v pamtester >/dev/null 2>&1; then
    return 0
  fi
  echo "Installing pamtester for Linux account authentication..."
  case "${OS_FAMILY}" in
    arch)
      install_packages pamtester >/dev/null 2>&1 || true
      if ! command -v pamtester >/dev/null 2>&1; then
        install_aur_package_if_possible pamtester >/dev/null 2>&1 || true
      fi
      ;;
    debian)
      install_packages pamtester >/dev/null 2>&1 || true
      ;;
  esac
  require_command_after_install pamtester "The admin UI depends on it for local account authentication. Install it manually if your distribution does not package it."
}

ensure_headless_nvidia_dependencies() {
  local need_install=0
  if ! command -v Xorg >/dev/null 2>&1; then
    need_install=1
  fi
  if ! command -v nvidia-settings >/dev/null 2>&1; then
    need_install=1
  fi
  if [[ "${need_install}" -eq 0 ]]; then
    return 0
  fi
  echo "Installing headless NVIDIA fan-control dependencies..."
  case "${OS_FAMILY}" in
    arch)
      install_packages xorg-server xorg-xinit nvidia-settings || true
      ;;
    debian)
      install_packages xserver-xorg-core xinit nvidia-settings || true
      ;;
  esac
  require_command_after_install Xorg "Headless fan control and NVIDIA tuning rely on a private Xorg display."
  require_command_after_install nvidia-settings "Fan control and GPU tuning rely on nvidia-settings."
}

install_caddy_official_debian_repo() {
  if command -v caddy >/dev/null 2>&1; then
    return 0
  fi
  echo "Installing Caddy from the official Debian/Ubuntu repository..."
  install_packages ca-certificates debian-keyring debian-archive-keyring apt-transport-https curl gpg >/dev/null 2>&1 || true
  require_command_after_install curl "Caddy installation needs curl to configure the official repository."
  require_command_after_install gpg "Caddy installation needs gpg to configure the official repository."
  "${SUDO[@]}" mkdir -p /usr/share/keyrings /etc/apt/sources.list.d
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | "${SUDO[@]}" gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | "${SUDO[@]}" tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  "${SUDO[@]}" chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  APT_UPDATED=0
  install_packages caddy >/dev/null 2>&1 || true
}

ensure_caddy_available() {
  if command -v caddy >/dev/null 2>&1; then
    return 0
  fi
  case "${OS_FAMILY}" in
    arch)
      echo "Installing Caddy..."
      install_packages caddy >/dev/null 2>&1 || true
      ;;
    debian)
      install_caddy_official_debian_repo
      ;;
  esac
  require_command_after_install caddy "HTTPS mode uses Caddy as the TLS reverse-proxy frontend."
}

read_network_state_field() {
  local key="$1"
  if [[ -r "${NETWORK_STATE_FILE}" ]] && command -v python3 >/dev/null 2>&1; then
    python3 - "${NETWORK_STATE_FILE}" "${key}" <<'PYSTATE' 2>/dev/null
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
except Exception:
    sys.exit(0)
val = obj.get(key)
if isinstance(val, list):
    print(",".join(str(x) for x in val))
elif val is not None:
    print(val)
PYSTATE
  fi
}

write_network_state() {
  local firewall_manager="$1"
  local upnp_enabled="$2"
  local tls_enabled="$3"
  if [[ -z "${PYTHON_BIN}" ]]; then
    return 1
  fi
  "${SUDO[@]}" "${PYTHON_BIN}" - "${NETWORK_STATE_FILE}" "${firewall_manager}" "${upnp_enabled}" "${tls_enabled}" "${ADMIN_PORT}" "${PROXY_PORT}" <<'PYNSTATE'
import json, os, sys
path, firewall_manager, upnp_enabled, tls_enabled, admin_port, proxy_port = sys.argv[1:]
os.makedirs(os.path.dirname(path), exist_ok=True)
firewall_ports = [int(admin_port), int(proxy_port)]
upnp_ports = [int(admin_port), int(proxy_port)] if upnp_enabled == "true" else []
if tls_enabled == "true":
    firewall_ports.extend([80, 443])
    if upnp_enabled == "true":
        upnp_ports.extend([80, 443])
obj = {
    "firewall_manager": firewall_manager,
    "firewall_ports": sorted(set(firewall_ports)),
    "upnp_ports": sorted(set(upnp_ports)),
    "tls_enabled": tls_enabled == "true",
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2, sort_keys=True)
os.replace(tmp, path)
PYNSTATE
}

close_tracked_online_exposure() {
  local cleanup_deadline
  cleanup_deadline="$(( $(network_now_seconds) + 15 ))"
  local old_fw old_ports old_upnp_ports old_port
  old_fw="$(read_network_state_field firewall_manager || true)"
  old_ports="$(read_network_state_field firewall_ports || true)"
  old_upnp_ports="$(read_network_state_field upnp_ports || true)"
  if [[ "${TAILSCALE_HTTPS_EFFECTIVE_ENABLED:-false}" == "true" ]]; then
    old_upnp_ports=""
  fi
  for old_port in ${old_ports//,/ }; do
    if network_deadline_expired "${cleanup_deadline}"; then
      echo "WARNING: Previous online exposure cleanup exceeded 15 seconds; continuing installer." >&2
      break
    fi
    [[ "${old_port}" =~ ^[0-9]+$ ]] || continue
    case "${old_fw}" in
      ufw)
        run_network_cmd 3 "${SUDO[@]}" ufw delete allow "${old_port}"/tcp || true
        ;;
      firewalld)
        if command -v firewall-cmd >/dev/null 2>&1 && run_network_cmd 3 "${SUDO[@]}" firewall-cmd --state; then
          run_network_cmd 3 "${SUDO[@]}" firewall-cmd --permanent --remove-port="${old_port}"/tcp || true
        fi
        ;;
      iptables)
        if command -v iptables >/dev/null 2>&1; then
          while run_network_cmd 2 "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${old_port}" -j ACCEPT; do
            run_network_cmd 2 "${SUDO[@]}" iptables -D INPUT -p tcp --dport "${old_port}" -j ACCEPT || break
          done
        fi
        ;;
    esac
  done
  for old_port in ${old_upnp_ports//,/ }; do
    if network_deadline_expired "${cleanup_deadline}"; then
      echo "WARNING: Previous UPnP exposure cleanup exceeded 15 seconds; continuing installer." >&2
      break
    fi
    [[ "${old_port}" =~ ^[0-9]+$ ]] || continue
    if command -v upnpc >/dev/null 2>&1; then
      run_network_cmd 3 upnpc -d "${old_port}" tcp || true
    fi
  done
  if [[ "${old_fw}" == "firewalld" ]] && command -v firewall-cmd >/dev/null 2>&1 && run_network_cmd 3 "${SUDO[@]}" firewall-cmd --state; then
    run_network_cmd 5 "${SUDO[@]}" firewall-cmd --reload || true
  fi
  if [[ -e "${NETWORK_STATE_FILE}" ]]; then
    "${SUDO[@]}" rm -f "${NETWORK_STATE_FILE}" >/dev/null 2>&1 || true
  fi
}

detect_public_ipv4() {
  local public_ip=""
  if command -v curl >/dev/null 2>&1; then
    public_ip="$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  fi
  if [[ "${public_ip}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    printf '%s\n' "${public_ip}"
    return 0
  fi
  return 1
}

detect_tailscale_https_host() {
  command -v tailscale >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  tailscale status --json 2>/dev/null | python3 -c 'import json, sys
try:
    status = json.load(sys.stdin)
except Exception:
    sys.exit(1)
self_node = status.get("Self") or {}
dns_name = str(self_node.get("DNSName") or "").strip().rstrip(".")
if dns_name.endswith(".ts.net"):
    print(dns_name)
    sys.exit(0)
host_name = str(self_node.get("HostName") or "").strip().strip(".")
magic_suffix = str(status.get("MagicDNSSuffix") or "").strip().strip(".")
if host_name and magic_suffix:
    print(f"{host_name}.{magic_suffix}")
    sys.exit(0)
sys.exit(1)'
}

resolve_https_public_host() {
  local explicit_host="${CLUB3090_HTTPS_HOST:-${CLUB3090_ONLINE_HOST:-}}"
  local public_ip="" tailscale_host=""
  if [[ "${ONLINE_TLS_TAILSCALE_MODE:-disable}" == "enable" ]] && tailscale_host="$(detect_tailscale_https_host 2>/dev/null)"; then
    printf '%s\n' "${tailscale_host}"
    return 0
  fi
  if [[ -n "${explicit_host}" ]]; then
    printf '%s\n' "${explicit_host}"
    return 0
  fi
  if [[ "${ONLINE_TLS_CERT_IP_MODE:-disable}" == "enable" ]] && public_ip="$(detect_public_ipv4 2>/dev/null)"; then
    printf '%s\n' "${public_ip}"
    return 0
  fi
  return 1
}

write_https_public_host() {
  local host_value="$1"
  "${SUDO[@]}" mkdir -p "${CONTROL_DIR}"
  if [[ -n "${host_value}" ]]; then
    printf '%s\n' "${host_value}" | "${SUDO[@]}" tee "${HTTPS_HOST_FILE}" >/dev/null
  else
    "${SUDO[@]}" rm -f "${HTTPS_HOST_FILE}" >/dev/null 2>&1 || true
  fi
}

read_https_public_host() {
  if [[ -r "${HTTPS_HOST_FILE}" ]]; then
    cat "${HTTPS_HOST_FILE}"
  fi
}

is_ipv4_address() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

certbot_live_dir_for_host() {
  printf '/etc/letsencrypt/live/%s\n' "$1"
}

certbot_supports_ip_address() {
  command -v certbot >/dev/null 2>&1 || return 1
  if command -v timeout >/dev/null 2>&1; then
    timeout --foreground --kill-after=2s 15s certbot --help all 2>/dev/null | grep -q -- '--ip-address'
  else
    certbot --help all 2>/dev/null | grep -q -- '--ip-address'
  fi
}

ensure_letsencrypt_ip_certificate() {
  local ip_value="$1"
  local live_dir fullchain privkey install_timeout issue_timeout
  is_ipv4_address "${ip_value}" || return 1
  install_timeout="${CLUB3090_CERTBOT_INSTALL_TIMEOUT_SECONDS:-900}"
  issue_timeout="${CLUB3090_CERTBOT_ISSUE_TIMEOUT_SECONDS:-300}"
  live_dir="$(certbot_live_dir_for_host "${ip_value}")"
  fullchain="${live_dir}/fullchain.pem"
  privkey="${live_dir}/privkey.pem"
  if [[ -r "${fullchain}" && -r "${privkey}" ]]; then
    return 0
  fi
  if ! command -v certbot >/dev/null 2>&1; then
    ensure_command_or_install_with_timeout certbot "${install_timeout}" "Installing Certbot for Let's Encrypt IP certificates..." certbot || true
  fi
  if ! certbot_supports_ip_address; then
    echo "WARNING: Certbot with --ip-address support was not found. Caddy will still serve HTTPS on the direct IP using its local certificate authority." >&2
    return 1
  fi
  "${SUDO[@]}" systemctl stop club3090-caddy.service 2>/dev/null || true
  if command -v timeout >/dev/null 2>&1; then
    "${SUDO[@]}" timeout --foreground --kill-after=15s "${issue_timeout}s" certbot certonly \
      --non-interactive \
      --agree-tos \
      --register-unsafely-without-email \
      --preferred-profile shortlived \
      --standalone \
      --ip-address "${ip_value}" \
      --deploy-hook "systemctl reload club3090-caddy.service >/dev/null 2>&1 || true" || {
      echo "WARNING: Let's Encrypt IP certificate issuance timed out or failed. Caddy will still serve HTTPS on the direct IP using its local certificate authority." >&2
      return 1
    }
  elif ! "${SUDO[@]}" certbot certonly \
      --non-interactive \
      --agree-tos \
      --register-unsafely-without-email \
      --preferred-profile shortlived \
      --standalone \
      --ip-address "${ip_value}" \
      --deploy-hook "systemctl reload club3090-caddy.service >/dev/null 2>&1 || true"; then
    echo "WARNING: Let's Encrypt IP certificate issuance failed. Caddy will still serve HTTPS on the direct IP using its local certificate authority." >&2
    return 1
  fi
  [[ -r "${fullchain}" && -r "${privkey}" ]]
}

ensure_tailscale_certificate() {
  local host_value="$1"
  [[ -n "${host_value}" && "${host_value}" == *.ts.net ]] || return 1
  command -v tailscale >/dev/null 2>&1 || return 1
  "${SUDO[@]}" mkdir -p "${CONTROL_DIR}"
  if "${SUDO[@]}" tailscale cert --cert-file "${TAILSCALE_CERT_FILE}" --key-file "${TAILSCALE_KEY_FILE}" "${host_value}" >/dev/null 2>&1; then
    "${SUDO[@]}" chmod 600 "${TAILSCALE_KEY_FILE}" >/dev/null 2>&1 || true
    "${SUDO[@]}" test -r "${TAILSCALE_CERT_FILE}" -a -r "${TAILSCALE_KEY_FILE}"
    return $?
  fi
  echo "WARNING: Failed to materialize Tailscale certificate for ${host_value}. Ensure Tailscale HTTPS certificates are enabled in the tailnet admin settings." >&2
  return 1
}

ensure_https_certificate() {
  local local_ip public_ip san_list san_file
  if [[ -r "${TLS_CERT_FILE}" && -r "${TLS_KEY_FILE}" ]]; then
    return 0
  fi
  ensure_command_or_install openssl "Installing OpenSSL for HTTPS certificate generation..." openssl >/dev/null 2>&1 || true
  require_command_after_install openssl "HTTPS mode needs OpenSSL to generate a certificate."
  local_ip="$(detect_primary_local_ip)"
  public_ip=""
  if command -v curl >/dev/null 2>&1; then
    public_ip="$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  fi
  san_list="DNS:localhost,DNS:$(hostname)"
  if [[ -n "${local_ip}" ]]; then
    san_list+=",IP:${local_ip}"
  fi
  if [[ -n "${public_ip}" ]]; then
    san_list+=",IP:${public_ip}"
  fi
  san_file="$(mktemp)"
  cat > "${san_file}" <<EOF
[req]
distinguished_name=req_distinguished_name
x509_extensions=v3_req
prompt=no

[req_distinguished_name]
CN=$(hostname)

[v3_req]
subjectAltName=${san_list}
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF
  "${SUDO[@]}" mkdir -p "${CONTROL_DIR}"
  "${SUDO[@]}" openssl req -x509 -nodes -newkey rsa:2048 -days 365 -keyout "${TLS_KEY_FILE}" -out "${TLS_CERT_FILE}" -config "${san_file}" >/dev/null 2>&1 || {
    rm -f "${san_file}"
    echo "ERROR: Failed to generate TLS certificate for HTTPS mode." >&2
    exit 1
  }
  rm -f "${san_file}"
  "${SUDO[@]}" chmod 600 "${TLS_KEY_FILE}" || true
}

detect_primary_local_ip() {
  local ip_value=""
  if command -v ip >/dev/null 2>&1; then
    ip_value="$(ip route get 1.1.1.1 2>/dev/null | awk '/src /{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  fi
  if [[ -z "${ip_value}" ]]; then
    ip_value="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s\n' "${ip_value}"
}

network_now_seconds() {
  date +%s 2>/dev/null || printf '0\n'
}

network_deadline_expired() {
  local deadline="$1"
  local now
  now="$(network_now_seconds)"
  [[ "${deadline}" -gt 0 && "${now}" -ge "${deadline}" ]]
}

run_network_cmd() {
  local timeout_seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=2s "${timeout_seconds}s" "$@" >/dev/null 2>&1
  else
    "$@" >/dev/null 2>&1
  fi
}

run_tailscale_serve_command() {
  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=2s 8s "${SUDO[@]}" tailscale serve "$@"
  else
    "${SUDO[@]}" tailscale serve "$@"
  fi
}

close_runtime_exposure() {
  local cleanup_deadline
  cleanup_deadline="$(( $(network_now_seconds) + 15 ))"
  local runtime_port
  for runtime_port in $(seq 8010 8020) $(seq 8200 8299); do
    if network_deadline_expired "${cleanup_deadline}"; then
      echo "WARNING: Runtime port exposure cleanup exceeded 15 seconds; continuing installer." >&2
      break
    fi
    if command -v ufw >/dev/null 2>&1; then
      run_network_cmd 3 "${SUDO[@]}" ufw delete allow "${runtime_port}"/tcp || true
    elif command -v firewall-cmd >/dev/null 2>&1 && run_network_cmd 3 "${SUDO[@]}" firewall-cmd --state; then
      run_network_cmd 3 "${SUDO[@]}" firewall-cmd --permanent --remove-port="${runtime_port}"/tcp || true
    elif command -v iptables >/dev/null 2>&1; then
      while run_network_cmd 2 "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${runtime_port}" -j ACCEPT; do
        run_network_cmd 2 "${SUDO[@]}" iptables -D INPUT -p tcp --dport "${runtime_port}" -j ACCEPT || break
      done
    fi
    if [[ "${TAILSCALE_HTTPS_EFFECTIVE_ENABLED:-false}" != "true" ]] && command -v upnpc >/dev/null 2>&1; then
      run_network_cmd 3 upnpc -d "${runtime_port}" tcp || true
    fi
  done
  if command -v firewall-cmd >/dev/null 2>&1 && run_network_cmd 3 "${SUDO[@]}" firewall-cmd --state; then
    run_network_cmd 5 "${SUDO[@]}" firewall-cmd --reload || true
  fi
}

configure_online_exposure() {
  local local_ip
  local_ip="$(detect_primary_local_ip)"
  local opened_fw=0
  local opened_upnp=0
  local firewall_manager="none"

  echo "Configuring online exposure for ports ${ADMIN_PORT} (admin) and ${PROXY_PORT} (proxy)..."
  echo "Runtime backend ports like 8010-8020 and 8200+ will remain private."
  close_tracked_online_exposure
  close_runtime_exposure

  if command -v ufw >/dev/null 2>&1; then
    run_network_cmd 10 "${SUDO[@]}" ufw allow "${ADMIN_PORT}"/tcp || true
    run_network_cmd 10 "${SUDO[@]}" ufw allow "${PROXY_PORT}"/tcp || true
    if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
      run_network_cmd 10 "${SUDO[@]}" ufw allow 80/tcp || true
      run_network_cmd 10 "${SUDO[@]}" ufw allow 443/tcp || true
    fi
    opened_fw=1
    firewall_manager="ufw"
  elif command -v firewall-cmd >/dev/null 2>&1 && run_network_cmd 5 "${SUDO[@]}" firewall-cmd --state; then
    run_network_cmd 10 "${SUDO[@]}" firewall-cmd --permanent --add-port="${ADMIN_PORT}"/tcp || true
    run_network_cmd 10 "${SUDO[@]}" firewall-cmd --permanent --add-port="${PROXY_PORT}"/tcp || true
    if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
      run_network_cmd 10 "${SUDO[@]}" firewall-cmd --permanent --add-port=80/tcp || true
      run_network_cmd 10 "${SUDO[@]}" firewall-cmd --permanent --add-port=443/tcp || true
    fi
    run_network_cmd 10 "${SUDO[@]}" firewall-cmd --reload || true
    opened_fw=1
    firewall_manager="firewalld"
  elif command -v iptables >/dev/null 2>&1; then
    run_network_cmd 5 "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT || run_network_cmd 5 "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT || true
    run_network_cmd 5 "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT || run_network_cmd 5 "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT || true
    if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
      run_network_cmd 5 "${SUDO[@]}" iptables -C INPUT -p tcp --dport 80 -j ACCEPT || run_network_cmd 5 "${SUDO[@]}" iptables -I INPUT -p tcp --dport 80 -j ACCEPT || true
      run_network_cmd 5 "${SUDO[@]}" iptables -C INPUT -p tcp --dport 443 -j ACCEPT || run_network_cmd 5 "${SUDO[@]}" iptables -I INPUT -p tcp --dport 443 -j ACCEPT || true
    fi
    opened_fw=1
    firewall_manager="iptables"
  fi

  if [[ "${TAILSCALE_HTTPS_EFFECTIVE_ENABLED:-false}" != "true" ]] && command -v upnpc >/dev/null 2>&1 && [[ -n "${local_ip}" ]]; then
    run_network_cmd 10 upnpc -e "club3090-admin" -a "${local_ip}" "${ADMIN_PORT}" "${ADMIN_PORT}" tcp && opened_upnp=1 || true
    run_network_cmd 10 upnpc -e "club3090-proxy" -a "${local_ip}" "${PROXY_PORT}" "${PROXY_PORT}" tcp && opened_upnp=1 || true
    if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
      run_network_cmd 10 upnpc -e "club3090-http" -a "${local_ip}" 80 80 tcp && opened_upnp=1 || true
      run_network_cmd 10 upnpc -e "club3090-https" -a "${local_ip}" 443 443 tcp && opened_upnp=1 || true
    fi
  fi

  if [[ "${opened_fw}" -eq 0 ]]; then
    echo "WARNING: No supported firewall manager was configured automatically. Admin and proxy ports may still need manual allow rules." >&2
  fi
  if [[ "${opened_upnp}" -eq 0 && "${TAILSCALE_HTTPS_EFFECTIVE_ENABLED:-false}" != "true" ]]; then
    echo "WARNING: UPnP port forwarding was not confirmed. Router support may be unavailable or disabled." >&2
  fi
  write_network_state "${firewall_manager}" "$([[ "${opened_upnp}" -eq 1 ]] && echo true || echo false)" "${ONLINE_TLS_EFFECTIVE_ENABLED}" >/dev/null 2>&1 || true
}

ensure_local_control_access() {
  local firewall_manager="none"
  local opened_fw=0

  echo "Ensuring local/LAN access for ports ${ADMIN_PORT} (admin) and ${PROXY_PORT} (proxy)..."

  if command -v ufw >/dev/null 2>&1; then
    run_network_cmd 10 "${SUDO[@]}" ufw allow "${ADMIN_PORT}"/tcp || true
    run_network_cmd 10 "${SUDO[@]}" ufw allow "${PROXY_PORT}"/tcp || true
    opened_fw=1
    firewall_manager="ufw"
  elif command -v firewall-cmd >/dev/null 2>&1 && run_network_cmd 5 "${SUDO[@]}" firewall-cmd --state; then
    run_network_cmd 10 "${SUDO[@]}" firewall-cmd --permanent --add-port="${ADMIN_PORT}"/tcp || true
    run_network_cmd 10 "${SUDO[@]}" firewall-cmd --permanent --add-port="${PROXY_PORT}"/tcp || true
    run_network_cmd 10 "${SUDO[@]}" firewall-cmd --reload || true
    opened_fw=1
    firewall_manager="firewalld"
  elif command -v iptables >/dev/null 2>&1; then
    run_network_cmd 5 "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT || run_network_cmd 5 "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT || true
    run_network_cmd 5 "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT || run_network_cmd 5 "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT || true
    opened_fw=1
    firewall_manager="iptables"
  fi

  if [[ "${opened_fw}" -eq 0 ]]; then
    echo "WARNING: No supported firewall manager was configured automatically. Admin and proxy ports may still need manual allow rules." >&2
  fi
  write_network_state "${firewall_manager}" "false" "${ONLINE_TLS_EFFECTIVE_ENABLED}" >/dev/null 2>&1 || true
}

log_step "Preparing dependencies for ${PRETTY_NAME:-${ID:-unknown}} (${OS_FAMILY})"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemctl is required because this installer configures systemd services." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker was not found in PATH. Install Docker before running this installer." >&2
  exit 1
elif ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  echo "ERROR: Docker Compose was not detected. club-3090 variants rely on 'docker compose' or 'docker-compose'." >&2
  exit 1
fi

case "${OS_FAMILY}" in
  arch)
    ensure_command_or_install python3 "Installing Python 3..." python
    ensure_command_or_install cpupower "cpupower is recommended for CPU governor power management. Installing it..." cpupower || true
    ensure_pamtester_available
    if [[ "${ONLINE_EFFECTIVE_ENABLED}" == "true" && "${TAILSCALE_HTTPS_EFFECTIVE_ENABLED:-false}" != "true" ]]; then
      ensure_command_or_install upnpc "Installing miniupnpc for online port forwarding..." miniupnpc || true
      ensure_command_or_install ufw "Installing ufw for online firewall management..." ufw || true
    fi
    if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
      ensure_command_or_install openssl "Installing OpenSSL for HTTPS certificate generation..." openssl || true
      ensure_caddy_available
    fi
    ;;
  debian)
    ensure_command_or_install python3 "Installing Python 3..." python3
    ensure_command_or_install cpupower "cpupower is recommended for CPU governor power management. Installing Ubuntu/Debian CPU power tools..." linux-tools-common || ensure_command_or_install cpupower "Falling back to distro-specific cpupower packages..." linux-cpupower || ensure_command_or_install cpupower "Falling back to generic Linux CPU power tools meta-package..." linux-tools-generic || true
    ensure_pamtester_available
    if [[ "${ONLINE_EFFECTIVE_ENABLED}" == "true" && "${TAILSCALE_HTTPS_EFFECTIVE_ENABLED:-false}" != "true" ]]; then
      ensure_command_or_install upnpc "Installing miniupnpc for online port forwarding..." miniupnpc || true
      ensure_command_or_install ufw "Installing ufw for online firewall management..." ufw || true
    fi
    if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
      ensure_command_or_install openssl "Installing OpenSSL for HTTPS certificate generation..." openssl || true
      ensure_caddy_available
    fi
    ;;
esac

ensure_headless_nvidia_dependencies

# Optional: report free/used space on unmounted NTFS volumes when ntfsinfo supports it.
if ! command -v ntfsinfo >/dev/null 2>&1; then
  echo "Installing NTFS utilities for storage metrics..."
  install_packages ntfs-3g || true
fi

if [[ -n "${PYTHON_BIN:-}" ]] && command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v "${PYTHON_BIN}")"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "ERROR: python3 is required but was not found after dependency installation." >&2
  exit 1
fi

log_done "Dependency preparation complete"

if [[ "${ACTION}" == "migrate" ]]; then
  log_step "Preparing resumable migration state"
  prepare_migration_state
  log_done "Migration state prepared"
fi

persist_hf_token_if_available

"${SUDO[@]}" mkdir -p "${CONTROL_DIR}"

# Disable older manual GPU power-limit services from earlier setup; v2.6 manages this dynamically.
"${SUDO[@]}" systemctl disable --now nvidia-tweaks.service 2>/dev/null || true
"${SUDO[@]}" systemctl disable --now set-gpu-power.service 2>/dev/null || true

# On update, stop the previous console follower first so a noisy old version
# does not keep spamming the active TTY while files are being replaced.
if [[ "${ACTION}" == "update" || "${ACTION}" == "migrate" ]]; then
  log_step "Stopping currently managed club-3090 services before ${ACTION}"
  # Stop the control plane before replacing files so a broken/stale Python process
  # cannot keep serving old code while the update is being installed.
  # Keep Caddy and the separate updater service alive so the web UI can continue
  # streaming self-update progress in real time during control-plane restarts.
  "${SUDO[@]}" systemctl stop club3090-console-log.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-control.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-headless-x.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-headless-x-v213.service 2>/dev/null || true
  if [[ "${ACTION}" == "migrate" ]]; then
    "${SUDO[@]}" systemctl stop club3090-vllm.service 2>/dev/null || true
    if [[ -f "${CLUB3090_DIR}/scripts/switch.sh" ]]; then
      (cd "${CLUB3090_DIR}" && "${SUDO[@]}" bash scripts/switch.sh --down) >/dev/null 2>&1 || true
    fi
  fi
  log_done "Old services stopped"
fi

if [[ "${ACTION}" == "migrate" ]]; then
  log_step "Migrating upstream club-3090 checkout"
  migrate_repo_checkout
  log_done "Upstream checkout migrated"
fi

log_step "Writing embedded control backend to ${CONTROL_PY}"
"${SUDO[@]}" "${PYTHON_BIN}" - "${CONTROL_PY}" <<'PYCTRL'
import base64
import gzip
import pathlib
import sys

CONTROL_PAYLOAD = "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"
path = pathlib.Path(sys.argv[1])
path.write_bytes(gzip.decompress(base64.b64decode(CONTROL_PAYLOAD.encode("ascii"))))
PYCTRL

"${SUDO[@]}" chmod +x "${CONTROL_PY}"
log_done "Control backend written"

log_step "Writing embedded updater backend to ${UPDATER_PY}"
"${SUDO[@]}" "${PYTHON_BIN}" - "${UPDATER_PY}" <<'PYUPDATER'
import base64
import gzip
import pathlib
import sys

UPDATER_PAYLOAD = "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"
path = pathlib.Path(sys.argv[1])
path.write_bytes(gzip.decompress(base64.b64decode(UPDATER_PAYLOAD.encode("ascii"))))
PYUPDATER

"${SUDO[@]}" chmod +x "${UPDATER_PY}"
if [[ "${CLUB3090_SELF_UPDATE_RELOAD_UPDATER:-false}" == "true" ]]; then
  "${SUDO[@]}" touch "${SELF_UPDATE_RELOAD_FLAG_FILE}"
else
  "${SUDO[@]}" rm -f "${SELF_UPDATE_RELOAD_FLAG_FILE}" >/dev/null 2>&1 || true
fi
log_done "Updater backend written"

log_step "Writing headless X and runtime helper scripts"
"${SUDO[@]}" tee "${HEADLESS_X_SH}" >/dev/null <<'HEADLESSX'
#!/usr/bin/env bash
set -euo pipefail

CONFIG=/etc/X11/club3090-headless-xorg.conf
DISPLAY_NUM="${CLUB3090_FAN_DISPLAY_NUM:-99}"
LOGFILE=/var/log/club3090-headless-xorg.log

mkdir -p /etc/X11 /var/log

# Canonical private headless Xorg used for manual NVIDIA fan control.
# It keeps the working "do not steal outputs" hardening without carrying a
# second duplicate headless-X path.
if command -v nvidia-xconfig >/dev/null 2>&1; then
  nvidia-xconfig     --enable-all-gpus     --cool-bits=28     --allow-empty-initial-configuration     --use-display-device=None     --virtual=1280x720     --xconfig="${CONFIG}" >/tmp/club3090-nvidia-xconfig.log 2>&1 || true
fi

if [[ -s "${CONFIG}" ]]; then
  PY_PATCH_BIN="$(command -v python || command -v python3 || true)"
  if [[ -n "${PY_PATCH_BIN}" ]]; then
    "${PY_PATCH_BIN}" - "${CONFIG}" <<'PYXCONF' || true
import re, sys
path = sys.argv[1]
text = open(path, encoding='utf-8', errors='ignore').read()
text = re.sub(r'(?im)^\s*Option\s+"ConnectedMonitor".*
?', '', text)
text = re.sub(r'(?im)^\s*Option\s+"UseDisplayDevice".*
?', '', text)
def patch(sec):
    if re.search(r'(?im)^\s*Driver\s+"nvidia"', sec):
        if 'AllowEmptyInitialConfiguration' not in sec:
            sec = sec.rstrip() + '
    Option "AllowEmptyInitialConfiguration" "true"
'
        if 'Coolbits' not in sec and 'CoolBits' not in sec:
            sec = sec.rstrip() + '
    Option "Coolbits" "28"
'
        sec = sec.rstrip() + '
    Option "UseDisplayDevice" "None"
'
    return sec
text = re.sub(r'(?is)Section\s+"Device".*?EndSection', lambda m: patch(m.group(0)), text)
def patch_screen(sec):
    if 'AllowEmptyInitialConfiguration' not in sec:
        sec = sec.rstrip() + '
    Option "AllowEmptyInitialConfiguration" "true"
'
    sec = sec.rstrip() + '
    Option "UseDisplayDevice" "None"
'
    if not re.search(r'(?is)SubSection\s+"Display".*?Virtual\s+\d+\s+\d+.*?EndSubSection', sec):
        sec = sec.rstrip() + '
    SubSection "Display"
        Virtual 1280 720
    EndSubSection
'
    return sec
text = re.sub(r'(?is)Section\s+"Screen".*?EndSection', lambda m: patch_screen(m.group(0)), text)
open(path, 'w', encoding='utf-8').write(text)
PYXCONF
  fi
fi

if [[ ! -s "${CONFIG}" ]]; then
  cat > "${CONFIG}" <<'XCONF'
Section "ServerLayout"
    Identifier "club3090-headless"
    Screen 0 "Screen0"
EndSection

Section "Device"
    Identifier "Device0"
    Driver "nvidia"
    Option "AllowEmptyInitialConfiguration" "true"
    Option "Coolbits" "28"
    Option "UseDisplayDevice" "None"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "Device0"
    Option "AllowEmptyInitialConfiguration" "true"
    Option "UseDisplayDevice" "None"
    SubSection "Display"
        Virtual 1280 720
    EndSubSection
EndSection
XCONF
fi

exec /usr/bin/Xorg :${DISPLAY_NUM}   -config "${CONFIG}"   -noreset   -nolisten tcp   -ac   -novtswitch   -sharevts   +extension GLX +extension RANDR +extension RENDER   -logfile "${LOGFILE}"
HEADLESSX
"${SUDO[@]}" chmod +x "${HEADLESS_X_SH}"

"${SUDO[@]}" tee "${START_SH}" >/dev/null <<'STARTVLLM'
#!/usr/bin/env bash
set -euo pipefail

CONTROL_DIR="/opt/club3090-control"
CONTROL_PY="${CONTROL_DIR}/control.py"

echo "[club3090-vllm] applying active power profile before model startup"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -pm 1 || true
  nvidia-smi -rgc || true
  nvidia-smi -pl "${CLUB3090_GPU_ACTIVE_POWER_LIMIT_W:-280}" || true
fi
if command -v cpupower >/dev/null 2>&1; then
  cpupower frequency-set -g "${CLUB3090_CPU_ACTIVE_GOVERNOR:-performance}" || true
fi

echo "[club3090-vllm] starting enabled club-3090 instances"
exec python3 "${CONTROL_PY}" --boot-enabled-instances
STARTVLLM
"${SUDO[@]}" chmod +x "${START_SH}"

"${SUDO[@]}" tee "${FOLLOW_SH}" >/dev/null <<'LOGFOLLOW' 
#!/usr/bin/env bash
set -euo pipefail

# This service is attached by systemd to one specific TTY, normally /dev/tty1.
# Keep output human-readable: no health-check spam, no identical consecutive lines,
# and at most one printed line per second.
INTERVAL_SECONDS="${CLUB3090_CONSOLE_INTERVAL:-1}"
TAIL_LINES="${CLUB3090_CONSOLE_TAIL:-80}"
last_line=""
last_emit=0

emit() {
  local line="$1"
  [[ -z "${line}" ]] && return 0

  # vLLM logs every internal health poll. These are useless on the physical TTY
  # and can completely flood the screen.
  if [[ "${line}" == *"GET /health HTTP/1.1"* ]]; then
    return 0
  fi

  if [[ "${line}" == "${last_line}" ]]; then
    return 0
  fi

  local now
  now="$(date +%s)"
  if (( now - last_emit < INTERVAL_SECONDS )); then
    return 0
  fi

  printf '[club3090-console] %s\n' "${line}"
  last_line="${line}"
  last_emit="${now}"
}

emit "Docker log follower starting. Waiting for club-3090 runtime container..."
while true; do
  mapfile -t containers < <(docker ps --format '{{.Names}}' | grep -Ei 'club3090-|vllm|qwen|llama-cpp' || true)
  if [[ "${#containers[@]}" -eq 0 ]]; then
    emit "No club-3090 runtime container yet; waiting..."
    sleep 3
    continue
  fi

  emit "Following docker logs for: ${containers[*]}"
  pids=()
  for container in "${containers[@]}"; do
    {
      while IFS= read -r line; do
        emit "[${container}] ${line}"
      done < <(docker logs --tail "${TAIL_LINES}" -f "${container}" 2>&1 || true)
    } &
    pids+=("$!")
  done

  wait -n "${pids[@]}" 2>/dev/null || true
  for pid in "${pids[@]}"; do
    kill "${pid}" 2>/dev/null || true
  done
  emit "A log stream ended; rescanning..."
  sleep 2
done
LOGFOLLOW
"${SUDO[@]}" chmod +x "${FOLLOW_SH}"
log_done "Helper scripts written"

if [[ -r "$0" ]] && grep -q 'Club-3090 Server Installer' "$0" 2>/dev/null; then
  current_script_real="$(readlink -f "$0" 2>/dev/null || printf '%s\n' "$0")"
  cached_script_real="$("${SUDO[@]}" readlink -f "${SELF_UPDATE_SCRIPT_PATH}" 2>/dev/null || printf '%s\n' "${SELF_UPDATE_SCRIPT_PATH}")"
  if [[ "${current_script_real}" != "${cached_script_real}" ]]; then
    log_step "Refreshing local self-update script cache at ${SELF_UPDATE_SCRIPT_PATH}"
    "${SUDO[@]}" install -m 0755 "$0" "${SELF_UPDATE_SCRIPT_PATH}"
    log_done "Local self-update script cache refreshed"
  fi
fi

if [[ ! -f "${ACTIVE_MODE_FILE}" ]]; then
  echo "${DEFAULT_MODE}" | "${SUDO[@]}" tee "${ACTIVE_MODE_FILE}" >/dev/null
fi
if [[ ! -f "${CONTROL_DIR}/last_good_mode" ]]; then
  "${SUDO[@]}" cp "${ACTIVE_MODE_FILE}" "${CONTROL_DIR}/last_good_mode" 2>/dev/null || true
fi

log_step "Refreshing persisted server configuration"
"${SUDO[@]}" "${PYTHON_BIN}" - "${CONTROL_DIR}" "${ONLINE_EFFECTIVE_ENABLED}" "${LOCAL_AUTOMATION_EFFECTIVE_ENABLED}" "${ONLINE_TLS_EFFECTIVE_ENABLED}" "${LOCAL_API_PORT}" "${TLS_CERT_FILE}" "${TLS_KEY_FILE}" <<'PYSERVERCFG'
import json, os, sys
control_dir = sys.argv[1]
online_mode = sys.argv[2]
local_automation_mode = sys.argv[3]
https_mode = sys.argv[4]
local_api_port = int(sys.argv[5])
https_cert_file = sys.argv[6]
https_key_file = sys.argv[7]
path = os.path.join(control_dir, "server_config.json")
current = {
    "allow_proxy_without_api_key": True,
    "online_enabled": False,
    "upnp_enabled": False,
    "https_enabled": False,
    "https_cert_file": https_cert_file,
    "https_key_file": https_key_file,
    "admin_path": "/admin",
    "local_api_enabled": False,
    "local_api_port": local_api_port,
}
had_existing = False
try:
    with open(path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if isinstance(loaded, dict):
        had_existing = True
        current.update({k: loaded[k] for k in current.keys() if k in loaded})
except Exception:
    pass
current["online_enabled"] = online_mode == "true"
current["upnp_enabled"] = online_mode == "true"
current["https_enabled"] = https_mode == "true"
current["https_cert_file"] = https_cert_file
current["https_key_file"] = https_key_file
if online_mode == "true":
    current["allow_proxy_without_api_key"] = bool(current.get("allow_proxy_without_api_key", False)) if had_existing else False
if local_automation_mode == "true":
    current["local_api_enabled"] = True
    current["local_api_port"] = local_api_port
else:
    current["local_api_enabled"] = False
current["admin_path"] = "/admin"
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(current, f, indent=2, sort_keys=True)
os.replace(tmp, path)
PYSERVERCFG
log_done "Server configuration refreshed"

log_step "Validating generated control files"
"${SUDO[@]}" "${BASH_BIN}" -n "${HEADLESS_X_SH}"
"${SUDO[@]}" "${PYTHON_BIN}" -m py_compile "${CONTROL_PY}"
"${SUDO[@]}" "${PYTHON_BIN}" -m py_compile "${UPDATER_PY}"
# Structural validation: catch missing helper functions before replacing a working service.
"${SUDO[@]}" "${PYTHON_BIN}" - "${CONTROL_PY}" <<'PYVERIFY'
import ast, sys
path = sys.argv[1]
tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
required = {"port_open","wait_for_runtime_ready","cleanup_vllm_containers","run_switch","detected_mode","active_port","ensure_vllm_running_for_request","apply_preset","parse_preset_path","set_gpu_fans","set_power_optimizations","set_fan_max_toggle","apply_fan_curve_once","ensure_headless_x_running","run_nvidia_settings","metrics_collector","wake_on_lan","apply_performance_profile","system_stats","read_ui_config","write_ui_config","read_custom_presets","write_custom_presets","get_all_presets","preset_catalog","save_custom_preset","delete_custom_preset","serve","main"}
missing = sorted(required - funcs)
if missing:
    raise SystemExit("control.py missing required functions: " + ", ".join(missing))
PYVERIFY
# Guardrail: status/readiness must not spam runtime HTTP endpoints.
if grep -q 'urlopen.*health\|/health.*urlopen\|urlopen.*v1/models\|v1/models.*urlopen\|def _ready_url_responding' "${CONTROL_PY}"; then
  echo "ERROR: control.py still contains runtime HTTP readiness polling" >&2
  exit 1
fi
log_done "Generated files validated"

if [[ "${ACTION}" == "migrate" ]]; then
  quarantine_non_git_genesis_dirs
  if [[ "${MIGRATION_BOOTSTRAP_INVENTORY_DONE}" != "1" ]]; then
    rebuild_runtime_inventory_cli "MIGRATION_BOOTSTRAP_INVENTORY_DONE" "inventory_bootstrap"
  else
    append_control_log_line "migrate bootstrap inventory already complete; skipping"
  fi
  if [[ "${MIGRATION_SETUP_DONE}" != "1" ]]; then
    if [[ "${MIGRATION_BOOTSTRAP_INVENTORY_DONE}" == "1" ]]; then
      append_control_log_line "migrate setup incomplete; refreshing inventory with current controller before replaying setup commands"
      rebuild_runtime_inventory_cli "" "inventory_bootstrap_refresh"
    fi
    log_step "Running required upstream setup commands for migrate"
    run_required_setup_commands
  else
    append_control_log_line "migrate setup step already complete; skipping"
  fi
  if [[ "${MIGRATION_POST_SETUP_INVENTORY_DONE}" != "1" ]]; then
    rebuild_runtime_inventory_cli "MIGRATION_POST_SETUP_INVENTORY_DONE" "inventory_post_setup"
  else
    append_control_log_line "migrate post-setup inventory already complete; skipping"
  fi
  if [[ "${MIGRATION_UPDATE_DONE}" != "1" ]]; then
    append_control_log_line "migrate update.sh step superseded by direct setup replay on the freshly cloned upstream checkout"
    migration_mark_flag_done "MIGRATION_UPDATE_DONE" "update_step_superseded"
  else
    append_control_log_line "migrate update.sh step already complete; skipping"
  fi
  if [[ "${MIGRATION_FINAL_INVENTORY_DONE}" != "1" ]]; then
    rebuild_runtime_inventory_cli "MIGRATION_FINAL_INVENTORY_DONE" "inventory_final"
  else
    append_control_log_line "migrate final inventory already complete; skipping"
  fi
  log_done "Migration setup commands completed"
else
  rebuild_runtime_inventory_cli
  if [[ "${ACTION}" == "install" ]]; then
    log_step "Running required upstream setup.sh commands for install"
    run_required_setup_commands
    rebuild_runtime_inventory_cli "" "inventory_post_install_setup"
    log_done "Install setup commands completed"
    log_step "Running upstream update.sh at the end of install"
    append_control_log_line "install update.sh command: bash scripts/update.sh"
    run_live_command "upstream update.sh" "${CLUB3090_DIR}" "bash scripts/update.sh"
    rebuild_runtime_inventory_cli "" "inventory_post_install_update"
    log_done "Install repo update completed"
  fi
fi

write_control_units() {
  "${SUDO[@]}" tee /etc/systemd/system/club3090-control.service >/dev/null <<UNIT
[Unit]
Description=club-3090 proxy and admin control panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=CLUB3090_DIR=${CLUB3090_DIR}
Environment=DEFAULT_MODE=${DEFAULT_MODE}
Environment=CLUB3090_SCRIPT_VERSION=${SCRIPT_VERSION}
Environment=CLUB3090_ADMIN_PORT=${ADMIN_PORT}
Environment=CLUB3090_PROXY_PORT=${PROXY_PORT}
Environment=CLUB3090_LOCAL_API_PORT=${LOCAL_API_PORT}
Environment=CLUB3090_ADMIN_BIND_HOST=${CONTROL_ADMIN_BIND_HOST}
Environment=CLUB3090_PROXY_BIND_HOST=${CONTROL_PROXY_BIND_HOST}
Environment=CLUB3090_ADMIN_BIND_PORT=${CONTROL_ADMIN_BIND_PORT}
Environment=CLUB3090_PROXY_BIND_PORT=${CONTROL_PROXY_BIND_PORT}
Environment=CLUB3090_UPDATER_BIND_HOST=${CONTROL_UPDATER_BIND_HOST}
Environment=CLUB3090_UPDATER_BIND_PORT=${CONTROL_UPDATER_BIND_PORT}
Environment=CLUB3090_CONTROL_DIR=${CONTROL_DIR}
Environment=CLUB3090_SELF_UPDATE_REPO_URL=${CLUB3090_SELF_UPDATE_REPO_URL}
Environment=CLUB3090_SELF_UPDATE_REF=${CLUB3090_SELF_UPDATE_REF}
Environment=CLUB3090_SELF_UPDATE_BRANCH=${CLUB3090_SELF_UPDATE_BRANCH}
Environment="CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE=${CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE}"
Environment="CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE=${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE}"
Environment=CLUB3090_POWER_IDLE_AFTER_SECONDS=600
Environment=CLUB3090_CONTAINER_STOP_AFTER_SECONDS=3600
Environment=CLUB3090_GPU_ACTIVE_POWER_LIMIT_W=280
Environment=CLUB3090_GPU_IDLE_POWER_LIMIT_W=120
Environment=CLUB3090_GPU_IDLE_LOCK_CLOCKS=210,900
Environment=CLUB3090_CPU_ACTIVE_GOVERNOR=performance
Environment=CLUB3090_CPU_IDLE_GOVERNOR=powersave
Environment=CLUB3090_FAN_MAX_SPEED=100
Environment=CLUB3090_FAN_MIN_SAFE_SPEED=35
Environment=CLUB3090_WOL_MAC=
Environment=CLUB3090_WOL_BROADCAST=255.255.255.255
ExecStart=${CONTROL_PY}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

  "${SUDO[@]}" tee /etc/systemd/system/club3090-updater.service >/dev/null <<UNIT
[Unit]
Description=club-3090 self-update companion service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=CLUB3090_CONTROL_DIR=${CONTROL_DIR}
Environment=CLUB3090_SCRIPT_VERSION=${SCRIPT_VERSION}
Environment=CLUB3090_ADMIN_PORT=${ADMIN_PORT}
Environment=CLUB3090_ADMIN_BIND_PORT=${CONTROL_ADMIN_BIND_PORT}
Environment=CLUB3090_UPDATER_BIND_HOST=${CONTROL_UPDATER_BIND_HOST}
Environment=CLUB3090_UPDATER_BIND_PORT=${CONTROL_UPDATER_BIND_PORT}
Environment=CLUB3090_HTTPS_ENABLED=${ONLINE_TLS_EFFECTIVE_ENABLED}
Environment=CLUB3090_SELF_UPDATE_REPO_URL=${CLUB3090_SELF_UPDATE_REPO_URL}
Environment=CLUB3090_SELF_UPDATE_REF=${CLUB3090_SELF_UPDATE_REF}
Environment=CLUB3090_SELF_UPDATE_BRANCH=${CLUB3090_SELF_UPDATE_BRANCH}
Environment="CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE=${CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE}"
Environment="CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE=${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE}"
ExecStart=${UPDATER_PY}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

  "${SUDO[@]}" tee /etc/systemd/system/club3090-headless-x.service >/dev/null <<UNIT
[Unit]
Description=club-3090 private headless Xorg for NVIDIA fan control
After=multi-user.target

[Service]
Type=simple
ExecStart=${HEADLESS_X_SH}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

  "${SUDO[@]}" tee /etc/systemd/system/club3090-console-log.service >/dev/null <<UNIT
[Unit]
Description=club-3090 console docker log follower
ConditionKernelCommandLine=club3090.server=1
After=docker.service
Wants=docker.service

[Service]
Type=simple
ExecStart=${FOLLOW_SH}
Restart=always
RestartSec=5
# Send visual feedback to exactly one local TTY instead of the kernel console.
# This avoids spamming every VT while still giving boot-time progress on tty1.
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=no
TTYVHangup=no
TTYVTDisallocate=no

[Install]
WantedBy=multi-user.target
UNIT
}

write_caddy_config() {
  local https_host="" certbot_live_dir="" certbot_fullchain="" certbot_privkey="" tls_line="" emit_host_routes="false" caddy_host_address=""
  https_host="$(read_https_public_host || true)"
  if [[ "${ONLINE_TLS_TAILSCALE_MODE:-disable}" == "enable" && "${https_host}" != *.ts.net ]]; then
    https_host="$(detect_tailscale_https_host 2>/dev/null || true)"
    if [[ -n "${https_host}" ]]; then
      write_https_public_host "${https_host}"
    fi
  fi
  if [[ -n "${https_host}" ]] && is_ipv4_address "${https_host}"; then
    certbot_live_dir="$(certbot_live_dir_for_host "${https_host}")"
    certbot_fullchain="${certbot_live_dir}/fullchain.pem"
    certbot_privkey="${certbot_live_dir}/privkey.pem"
    if "${SUDO[@]}" test -r "${certbot_fullchain}" -a -r "${certbot_privkey}"; then
      tls_line="    tls ${certbot_fullchain} ${certbot_privkey}"
      emit_host_routes="true"
    fi
  elif [[ -n "${https_host}" && "${https_host}" == *.ts.net ]]; then
    if ! "${SUDO[@]}" test -r "${TAILSCALE_CERT_FILE}" -a -r "${TAILSCALE_KEY_FILE}"; then
      ensure_tailscale_certificate "${https_host}" || true
    fi
    if "${SUDO[@]}" test -r "${TAILSCALE_CERT_FILE}" -a -r "${TAILSCALE_KEY_FILE}"; then
      tls_line="    tls ${TAILSCALE_CERT_FILE} ${TAILSCALE_KEY_FILE}"
      emit_host_routes="true"
    else
      echo "WARNING: Tailscale certificate files are unavailable for ${https_host}; Caddy ts.net port routes will not be browser-trusted." >&2
    fi
  fi
  if [[ "${https_host}" == *.ts.net ]]; then
    caddy_host_address="https://${https_host}"
  else
    caddy_host_address="https://${https_host}"
  fi
  "${SUDO[@]}" tee "${CADDYFILE_PATH}" >/dev/null <<CADDY
{
    admin off
}

$(if [[ "${emit_host_routes}" == "true" ]]; then cat <<EOF
${caddy_host_address}:${ADMIN_PORT} {
${tls_line}
    @club3090_updater path /admin/update-stream /admin/update-status
    handle @club3090_updater {
        reverse_proxy 127.0.0.1:${CONTROL_UPDATER_BIND_PORT}
    }
    handle {
        reverse_proxy 127.0.0.1:${CONTROL_ADMIN_BIND_PORT}
    }
}

${caddy_host_address}:${PROXY_PORT} {
${tls_line}
    reverse_proxy 127.0.0.1:${CONTROL_PROXY_BIND_PORT}
}
EOF
fi)

https://:${ADMIN_PORT} {
    tls ${TLS_CERT_FILE} ${TLS_KEY_FILE}
    @club3090_updater path /admin/update-stream /admin/update-status
    handle @club3090_updater {
        reverse_proxy 127.0.0.1:${CONTROL_UPDATER_BIND_PORT}
    }
    handle {
        reverse_proxy 127.0.0.1:${CONTROL_ADMIN_BIND_PORT}
    }
}

https://:${PROXY_PORT} {
    tls ${TLS_CERT_FILE} ${TLS_KEY_FILE}
    reverse_proxy 127.0.0.1:${CONTROL_PROXY_BIND_PORT}
}
CADDY
}

write_caddy_unit() {
  "${SUDO[@]}" tee /etc/systemd/system/club3090-caddy.service >/dev/null <<UNIT
[Unit]
Description=club-3090 HTTPS frontend (Caddy)
After=club3090-control.service network-online.target
Wants=club3090-control.service network-online.target

[Service]
Type=simple
ExecStart=$(command -v caddy) run --config ${CADDYFILE_PATH} --adapter caddyfile
ExecReload=$(command -v caddy) reload --config ${CADDYFILE_PATH} --adapter caddyfile
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
}

configure_https_frontend() {
  local https_host=""
  if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" != "true" ]]; then
    "${SUDO[@]}" systemctl disable --now club3090-caddy.service 2>/dev/null || true
    "${SUDO[@]}" rm -f /etc/systemd/system/club3090-caddy.service "${CADDYFILE_PATH}" >/dev/null 2>&1 || true
    write_https_public_host ""
    return 0
  fi
  https_host="$(resolve_https_public_host || true)"
  write_https_public_host "${https_host}"
  ensure_https_certificate
  if [[ -z "${https_host}" ]]; then
    if [[ "${ONLINE_TLS_TAILSCALE_MODE:-disable}" == "enable" ]]; then
      echo "WARNING: Could not detect a Tailscale MagicDNS hostname. Make sure tailscale is installed, logged in, and MagicDNS/HTTPS certificates are enabled for the tailnet. Falling back to a self-signed certificate." >&2
    else
      echo "WARNING: Could not determine a public DNS hostname for Let's Encrypt. Falling back to a self-signed certificate." >&2
    fi
  elif is_ipv4_address "${https_host}" && [[ "${ONLINE_TLS_CERT_IP_MODE:-disable}" == "enable" || "${CLUB3090_ENABLE_IP_LE:-false}" == "true" ]]; then
    ensure_letsencrypt_ip_certificate "${https_host}" || true
  elif is_ipv4_address "${https_host}"; then
    :
  elif [[ "${https_host}" == *.ts.net ]]; then
    ensure_tailscale_certificate "${https_host}" || true
  else
    :
  fi
  write_caddy_config
  if ! "${SUDO[@]}" caddy fmt --overwrite "${CADDYFILE_PATH}" >/dev/null 2>&1; then
    echo "ERROR: Failed to format generated Caddy configuration." >&2
    exit 1
  fi
  if ! "${SUDO[@]}" caddy validate --config "${CADDYFILE_PATH}" --adapter caddyfile >/dev/null 2>&1; then
    echo "ERROR: Generated Caddy configuration is invalid." >&2
    exit 1
  fi
  write_caddy_unit
}

write_vllm_unit() {
  "${SUDO[@]}" tee /etc/systemd/system/club3090-vllm.service >/dev/null <<UNIT
[Unit]
Description=club-3090 vLLM server
ConditionKernelCommandLine=club3090.server=1
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${CLUB3090_DIR}
Environment=CLUB3090_DIR=${CLUB3090_DIR}
Environment=DEFAULT_MODE=${DEFAULT_MODE}
ExecStart=${START_SH}
TimeoutStartSec=1800
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
}

cleanup_legacy_fan_test_artifacts() {
  "${SUDO[@]}" systemctl disable --now club3090-headless-x-v213.service 2>/dev/null || true
  "${SUDO[@]}" rm -f \
    /etc/systemd/system/club3090-headless-x-v213.service \
    "${CONTROL_DIR}/prepare-headless-x-v213.sh" \
    /etc/X11/club3090-headless-xorg-v213.conf \
    /var/log/club3090-headless-xorg-v213.log >/dev/null 2>&1 || true
}

enable_managed_units() {
  "${SUDO[@]}" systemctl enable club3090-vllm.service
  "${SUDO[@]}" systemctl disable club3090-headless-x.service 2>/dev/null || true
  "${SUDO[@]}" systemctl enable club3090-control.service
  "${SUDO[@]}" systemctl enable club3090-updater.service
  "${SUDO[@]}" systemctl enable club3090-console-log.service
  if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
    "${SUDO[@]}" systemctl enable club3090-caddy.service
  else
    "${SUDO[@]}" systemctl disable club3090-caddy.service 2>/dev/null || true
  fi
}

configure_networking_and_frontend() {
  if [[ "${ONLINE_EFFECTIVE_ENABLED}" == "true" ]]; then
    configure_online_exposure
  else
    ensure_local_control_access
    close_runtime_exposure
  fi
}

configure_tailscale_funnel_if_requested() {
  local admin_target proxy_target
  if [[ "${ONLINE_TLS_TAILSCALE_FUNNEL_MODE:-disable}" != "enable" ]]; then
    return 0
  fi
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "WARNING: Tailscale Funnel requested, but tailscale is not installed. Skipping Funnel setup." >&2
    return 0
  fi
  admin_target="https+insecure://127.0.0.1:${ADMIN_PORT}"
  proxy_target="https+insecure://127.0.0.1:${PROXY_PORT}"
  echo "Configuring Tailscale Funnel for public internet access..."
  if ! run_network_cmd 30 "${SUDO[@]}" tailscale funnel --yes --bg --https=443 "${admin_target}"; then
    echo "WARNING: Failed to enable Tailscale Funnel for admin UI on public port 443. Tailscale may require an interactive approval or tailnet policy update." >&2
  fi
  if ! run_network_cmd 30 "${SUDO[@]}" tailscale funnel --yes --bg --https=8443 "${proxy_target}"; then
    echo "WARNING: Failed to enable Tailscale Funnel for proxy API on public port 8443. Tailscale may require an interactive approval or tailnet policy update." >&2
  fi
}

configure_tailscale_serve_if_requested() {
  local admin_target proxy_target serve_output
  if [[ "${ONLINE_TLS_TAILSCALE_MODE:-disable}" != "enable" || "${ONLINE_TLS_TAILSCALE_FUNNEL_MODE:-disable}" == "enable" ]]; then
    return 0
  fi
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "WARNING: Tailscale HTTPS requested, but tailscale is not installed. Skipping Tailscale Serve setup." >&2
    return 0
  fi
  if ! tailscale status --json >/dev/null 2>&1; then
    echo "WARNING: Tailscale HTTPS requested, but this node is not logged in or tailscaled is not reachable. Skipping Tailscale Serve setup." >&2
    return 0
  fi
  admin_target="127.0.0.1:${CONTROL_ADMIN_BIND_PORT}"
  proxy_target="127.0.0.1:${CONTROL_PROXY_BIND_PORT}"
  echo "Configuring Tailscale Serve for tailnet HTTPS..."
  serve_output="$(run_tailscale_serve_command --yes --bg --https=443 "${admin_target}" 2>&1)" || {
    echo "WARNING: Failed to enable Tailscale Serve for admin UI on https://<ts-name>/admin." >&2
    if [[ -n "${serve_output}" ]]; then
      printf '%s\n' "${serve_output}" | sed 's/^/WARNING: tailscale serve: /' >&2
    fi
    return 0
  }
  serve_output="$(run_tailscale_serve_command --yes --bg --https=8443 "${proxy_target}" 2>&1)" || {
    echo "WARNING: Failed to enable Tailscale Serve for proxy API on https://<ts-name>:8443/v1." >&2
    if [[ -n "${serve_output}" ]]; then
      printf '%s\n' "${serve_output}" | sed 's/^/WARNING: tailscale serve: /' >&2
    fi
    return 0
  }
  if ! run_network_cmd 3 tailscale serve status --json; then
    echo "WARNING: Tailscale Serve commands completed, but status verification failed." >&2
  fi
}

start_control_plane_services_if_booted() {
  start_unit_nonblocking club3090-updater.service
  start_unit_nonblocking club3090-control.service
  if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
    start_unit_nonblocking club3090-caddy.service
  fi
  configure_tailscale_serve_if_requested
  configure_tailscale_funnel_if_requested
  if ! grep -q 'club3090.server=1' /proc/cmdline; then
    return 0
  fi
  start_unit_nonblocking club3090-console-log.service
}

start_unit_nonblocking() {
  local unit="$1"
  if "${SUDO[@]}" systemctl --help 2>/dev/null | grep -q -- '--no-block'; then
    "${SUDO[@]}" systemctl start --no-block "${unit}" >/dev/null 2>&1 || true
    return 0
  fi
  "${SUDO[@]}" systemctl start "${unit}" >/dev/null 2>&1 || true
}

reload_caddy_if_active() {
  if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" != "true" ]]; then
    return 0
  fi
  if "${SUDO[@]}" systemctl is-active --quiet club3090-caddy.service; then
    "${SUDO[@]}" systemctl reload club3090-caddy.service >/dev/null 2>&1 || \
      "${SUDO[@]}" systemctl restart club3090-caddy.service >/dev/null 2>&1 || true
  fi
}

refresh_updater_service_if_safe() {
  if [[ "${CLUB3090_RUNNING_FROM_UPDATER:-0}" == "1" ]]; then
    return 0
  fi
  "${SUDO[@]}" systemctl restart club3090-updater.service >/dev/null 2>&1 || true
}

if [[ "${ACTION}" == "install" ]]; then
  log_step "Writing and enabling systemd units for a fresh install"
  write_vllm_unit
  write_control_units
  cleanup_legacy_fan_test_artifacts
  log_step "Configuring networking and frontend exposure"
  configure_networking_and_frontend
  configure_https_frontend
  log_step "Reloading systemd manager configuration"
  "${SUDO[@]}" systemctl daemon-reload
  log_step "Enabling managed club-3090 services"
  enable_managed_units
  refresh_updater_service_if_safe
  reload_caddy_if_active
  log_step "Starting control-plane services when server boot mode is active"
  start_control_plane_services_if_booted
  log_done "Install actions completed"

  echo
  echo "Installed club-3090 server control services."
  echo "Admin/proxy services can run normally without a kernel switch."
  echo "Use club3090.server=1 only when you want unattended container autoboot plus tty1 console log output during system startup."
elif [[ "${ACTION}" == "update" ]]; then
  log_step "Refreshing systemd units and managed services for update"
  # Update the vLLM unit too so the next reboot uses the last selected mode.
  # Do not restart it here; that would interrupt a running model session.
  write_vllm_unit
  write_control_units
  cleanup_legacy_fan_test_artifacts
  log_step "Refreshing networking and frontend exposure"
  configure_networking_and_frontend
  configure_https_frontend
  log_step "Reloading systemd manager configuration"
  "${SUDO[@]}" systemctl daemon-reload
  log_step "Re-enabling managed club-3090 services"
  enable_managed_units
  refresh_updater_service_if_safe
  reload_caddy_if_active
  log_step "Starting control-plane services if the server boot flag is active"
  start_control_plane_services_if_booted
  log_done "Update actions completed"
  echo
  echo "Updated club-3090 multi-instance control plane, proxy, metrics UI, console log follower, and boot unit."
  echo "Running Docker instances were left unchanged; next server boot will restore enabled entries from ${CONTROL_DIR}/instances.json."
else
  log_step "Refreshing systemd units and managed services after migrate"
  write_vllm_unit
  write_control_units
  cleanup_legacy_fan_test_artifacts
  log_step "Refreshing networking and frontend exposure"
  configure_networking_and_frontend
  configure_https_frontend
  log_step "Reloading systemd manager configuration"
  "${SUDO[@]}" systemctl daemon-reload
  log_step "Re-enabling managed club-3090 services"
  enable_managed_units
  refresh_updater_service_if_safe
  reload_caddy_if_active
  log_step "Starting control-plane services if the server boot flag is active"
  start_control_plane_services_if_booted
  migration_mark_flag_done "MIGRATION_SERVICES_REFRESHED" "services_refreshed_after_migrate"
  finalize_migration_state_success
  log_done "Migrate actions completed"
  echo
  echo "Migrated the upstream club-3090 checkout to a fresh clone, preserved runtime/model assets, rebuilt the dynamic inventory, and refreshed the control plane."
fi

URL_SCHEME="http"
DISPLAY_HOST="SERVER"
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
  URL_SCHEME="https"
  resolved_https_host="$(read_https_public_host || true)"
  if [[ -n "${resolved_https_host}" ]]; then
    DISPLAY_HOST="${resolved_https_host}"
  else
    detected_display_ip="$(detect_public_ipv4 2>/dev/null || true)"
    if [[ -n "${detected_display_ip}" ]]; then
      DISPLAY_HOST="${detected_display_ip}"
    fi
  fi
fi
echo "Admin UI:  ${URL_SCHEME}://${DISPLAY_HOST}:${ADMIN_PORT}/admin"
echo "Proxy API: ${URL_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}/v1/chat/completions"
echo "OpenAI base URL: ${URL_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}/v1"
echo "Per-GPU proxy: ${URL_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}/GPU0/v1/chat/completions"
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
  echo "HTTPS edge: Caddy ${ADMIN_PORT}->127.0.0.1:${CONTROL_ADMIN_BIND_PORT}, ${PROXY_PORT}->127.0.0.1:${CONTROL_PROXY_BIND_PORT}"
fi
if [[ "${LOCAL_AUTOMATION_EFFECTIVE_ENABLED}" == "true" ]]; then
  echo "Local user API: http://127.0.0.1:${LOCAL_API_PORT}/users (token in ${CONTROL_DIR}/local_api_token)"
else
  echo "Local user API: disabled by default, enable with --local-automation"
fi
echo "Fan Control: private on-demand Xorg :99 via club3090-headless-x.service"
echo "Club dir:  ${CLUB3090_DIR}"
echo "Detected OS: ${PRETTY_NAME:-${ID:-unknown}} (${OS_FAMILY})"
echo "GPUs:      ${GPU_COUNT} detected"
echo "Auto mode: ${AUTO_DEFAULT_MODE}"
echo "Default:   ${DEFAULT_MODE}"
echo "Admin port:${ADMIN_PORT}"
echo "Proxy port:${PROXY_PORT}"
echo "Local API: ${LOCAL_API_PORT} ($([[ "${LOCAL_AUTOMATION_EFFECTIVE_ENABLED}" == "true" ]] && echo enabled || echo disabled))"
echo "Instances: ${CONTROL_DIR}/instances.json"
echo "Server cfg: ${CONTROL_DIR}/server_config.json"
echo "Users:     ${CONTROL_DIR}/users.json"
echo "Action:    ${ACTION}"
echo "Version:   ${SCRIPT_VERSION}"
echo "Online:    $([[ "${ONLINE_EFFECTIVE_ENABLED}" == "true" ]] && echo enabled || echo disabled)"
echo "HTTPS:     $([[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]] && echo enabled || echo disabled)"
echo "Preset path styles supported: ${URL_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}/v1/<preset>/chat/completions, ${URL_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}/<preset>/v1/chat/completions, and per-GPU prefixes like ${URL_SCHEME}://${DISPLAY_HOST}:${PROXY_PORT}/GPU0/v1/<preset>/chat/completions"
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" && -z "${resolved_https_host:-}" ]]; then
  echo "HTTPS note: direct IP access uses the self-signed certificate path. Set CLUB3090_HTTPS_HOST to a DNS name that points here for a browser-trusted Let's Encrypt certificate."
elif [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" && "${ONLINE_TLS_TAILSCALE_MODE:-disable}" == "enable" && "${ONLINE_TLS_TAILSCALE_FUNNEL_MODE:-disable}" != "enable" ]]; then
  echo "Tailscale Serve admin: https://${DISPLAY_HOST}/admin"
  echo "Tailscale Serve proxy: https://${DISPLAY_HOST}:8443/v1/chat/completions"
  echo "HTTPS note: direct :${ADMIN_PORT}/:${PROXY_PORT} IP access remains on the self-signed Caddy path; the browser-trusted ts.net path is served by Tailscale itself."
fi
if [[ "${ONLINE_TLS_TAILSCALE_FUNNEL_MODE:-disable}" == "enable" && -n "${resolved_https_host:-}" ]]; then
  echo "Tailscale Funnel public admin: https://${DISPLAY_HOST}/admin"
  echo "Tailscale Funnel public proxy: https://${DISPLAY_HOST}:8443/v1/chat/completions"
fi
