#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="2026-06-02.v0.9.28"
CHANGE_LOG_ICONS='{"new_feature":"🟢","fix":"🐞","remove_feature":"🔴","security":"🔒","performance":"⚡","ui_ux":"🖥️","build_pipeline_improvement":"🛠️","test":"🧪","update":"🔄","docs":"📝","backend":"🧰","compatibility":"🧩","modified_feature":"⚙️"}'
CHANGE_LOG_LATEST=$(cat <<'EOF_CHANGE_LOG_LATEST'
• 🐞 Restored the Metrics GPU subtab chart rendering to the working v0.8.54 behavior so GPU temperature, power, utilization, and VRAM charts draw correctly again while the faster first-load metrics polling remains in place.
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
