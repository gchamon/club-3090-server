#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="2026-06-01.v0.9.26"
CHANGE_LOG_ICONS='{"new_feature":"🟢","fix":"🐞","remove_feature":"🔴","security":"🔒","performance":"⚡","ui_ux":"🖥️","build_pipeline_improvement":"🛠️","test":"🧪","update":"🔄","docs":"📝","backend":"🧰","compatibility":"🧩","modified_feature":"⚙️"}'
CHANGE_LOG_LATEST=$(cat <<'EOF_CHANGE_LOG_LATEST'
• 🐞 Fixed streamed markdown list rendering so split ordered and unordered markers like 3 + . Ruby or - + item are repaired during generation, preserving bold/italic formatting without waiting for the final render pass.
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
