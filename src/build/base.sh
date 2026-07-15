#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="2026-05-18.v0.6.108"
CLUB3090_SELF_UPDATE_REPO_URL="${CLUB3090_SELF_UPDATE_REPO_URL:-https://github.com/VykosX/club-3090-server.git}"
CLUB3090_SELF_UPDATE_REF="${CLUB3090_SELF_UPDATE_REF:-refs/heads/master}"
CLUB3090_SELF_UPDATE_BRANCH="${CLUB3090_SELF_UPDATE_BRANCH:-master}"
CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE="${CLUB3090_SELF_UPDATE_RAW_URL_TEMPLATE:-https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/install-club3090-server.sh}"
CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE="${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE:-https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/metadata.json}"
GPUTEMPS_VENDOR_PAYLOAD_BASE64="" # Injected by build.py for shipped outputs.
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
if [[ "${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE}" != *"{sha}"* ]] || [[ "${CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE}" != https://raw.githubusercontent.com/VykosX/club-3090-server/*/metadata.json ]]; then
  CLUB3090_SELF_UPDATE_METADATA_URL_TEMPLATE="https://raw.githubusercontent.com/VykosX/club-3090-server/{sha}/metadata.json"
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
# Skip optional GDDR6/GDDR6X junction + VRAM temperature helper setup:
#   bash install-club3090-server.sh --skip-temps
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
GPU_EXTRA_TEMPS_MODE="enable"
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
    --skip-temps)
      GPU_EXTRA_TEMPS_MODE="disable"
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
HF_BIN="${HF_BIN:-$(command -v hf || true)}"
if [[ -z "${HF_BIN}" && -x "${HOME:-}/.local/bin/hf" ]]; then
  HF_BIN="${HOME}/.local/bin/hf"
fi
CONTROL_SERVICE_PATH="${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
if [[ -n "${HF_BIN}" ]]; then
  CONTROL_SERVICE_PATH="$(dirname "${HF_BIN}"):${CONTROL_SERVICE_PATH}"
fi
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

log_resolved_pre_sudo_config() {
  local hf_token_state="unset"
  local repo_model_dir repo_hf_home repo_hf_hub_cache repo_huggingface_hub_cache repo_transformers_cache
  local hf_home hf_hub_cache transformers_cache model_root model_dir_source hf_home_source hf_cache_source transformers_cache_source
  repo_model_dir="$(read_repo_env_value "${REPO_ENV_FILE}" "MODEL_DIR" || true)"
  repo_hf_home="$(read_repo_env_value "${REPO_ENV_FILE}" "HF_HOME" || true)"
  repo_hf_hub_cache="$(read_repo_env_value "${REPO_ENV_FILE}" "HF_HUB_CACHE" || true)"
  repo_huggingface_hub_cache="$(read_repo_env_value "${REPO_ENV_FILE}" "HUGGINGFACE_HUB_CACHE" || true)"
  repo_transformers_cache="$(read_repo_env_value "${REPO_ENV_FILE}" "TRANSFORMERS_CACHE" || true)"
  hf_home="${HF_HOME:-${repo_hf_home:-}}"
  hf_hub_cache="${HF_HUB_CACHE:-${HUGGINGFACE_HUB_CACHE:-${repo_hf_hub_cache:-${repo_huggingface_hub_cache:-}}}}"
  transformers_cache="${TRANSFORMERS_CACHE:-${repo_transformers_cache:-}}"
  model_root="${MODEL_DIR:-${repo_model_dir:-models-cache}}"
  model_dir_source="default"
  hf_home_source="unset"
  hf_cache_source="unset"
  transformers_cache_source="unset"
  if [[ -n "${repo_model_dir}" ]]; then
    model_dir_source="${REPO_ENV_FILE}"
  fi
  if [[ -n "${MODEL_DIR:-}" ]]; then
    model_dir_source="environment"
  fi
  if [[ -n "${repo_hf_home}" ]]; then
    hf_home_source="${REPO_ENV_FILE}"
  fi
  if [[ -n "${HF_HOME:-}" ]]; then
    hf_home_source="environment"
  fi
  if [[ -n "${repo_hf_hub_cache}" || -n "${repo_huggingface_hub_cache}" ]]; then
    hf_cache_source="${REPO_ENV_FILE}"
  fi
  if [[ -n "${HF_HUB_CACHE:-}" || -n "${HUGGINGFACE_HUB_CACHE:-}" ]]; then
    hf_cache_source="environment"
  fi
  if [[ -n "${repo_transformers_cache}" ]]; then
    transformers_cache_source="${REPO_ENV_FILE}"
  fi
  if [[ -n "${TRANSFORMERS_CACHE:-}" ]]; then
    transformers_cache_source="environment"
  fi
  if [[ "${model_root}" != /* ]]; then
    model_root="${CLUB3090_DIR}/${model_root}"
  fi
  if [[ -n "${HF_TOKEN_VALUE}" ]]; then
    hf_token_state="set (${#HF_TOKEN_VALUE} chars)"
  fi
  printf '\n[%s] resolved configuration before sudo\n' "$(date +%H:%M:%S)"
  printf '  action: %s\n' "${ACTION}"
  printf '  club-3090 dir: %s\n' "${CLUB3090_DIR}"
  printf '  repo env file: %s\n' "${REPO_ENV_FILE}"
  if [[ -r "${REPO_ENV_FILE}" ]]; then
    printf '  repo env status: loaded\n'
  else
    printf '  repo env status: not found/readable yet\n'
  fi
  printf '  effective MODEL_DIR: %s (%s)\n' "${model_root}" "${model_dir_source}"
  printf '  default mode: %s\n' "${DEFAULT_MODE:-<auto>}"
  printf '  control dir: %s\n' "${CONTROL_DIR}"
  printf '  bash binary: %s\n' "${BASH_BIN:-<not found>}"
  printf '  python binary: %s\n' "${PYTHON_BIN:-<not found>}"
  printf '  hf binary: %s\n' "${HF_BIN:-<not found>}"
  printf '  hf token: %s\n' "${hf_token_state}"
  printf '  effective HF_HOME: %s (%s)\n' "${hf_home:-<unset>}" "${hf_home_source}"
  printf '  effective HF_HUB_CACHE/HUGGINGFACE_HUB_CACHE: %s (%s)\n' "${hf_hub_cache:-<unset>}" "${hf_cache_source}"
  printf '  effective TRANSFORMERS_CACHE: %s (%s)\n' "${transformers_cache:-<unset>}" "${transformers_cache_source}"
  if [[ -z "${PYTHON_BIN}" || ! -r "${CONTROL_DIR}/runtime_inventory.json" ]]; then
    printf '  runtime inventory: %s\n' "${CONTROL_DIR}/runtime_inventory.json not readable yet"
    return 0
  fi
  env CLUB3090_DIR="${CLUB3090_DIR}" MODEL_DIR="${model_root}" DEFAULT_MODE="${DEFAULT_MODE}" HF_HOME="${hf_home}" HF_HUB_CACHE="${hf_hub_cache}" "${PYTHON_BIN}" - "${CONTROL_DIR}/runtime_inventory.json" <<'PYPREFLIGHT' || true
import json
import os
import shlex
import sys

inventory_path = sys.argv[1]
default_mode = str(os.environ.get("DEFAULT_MODE") or "").strip()
club_dir = str(os.environ.get("CLUB3090_DIR") or "").rstrip("/")
model_root = str(os.environ.get("MODEL_DIR") or "").rstrip("/")
hf_home = str(os.environ.get("HF_HOME") or "").strip()
hf_hub_cache = str(os.environ.get("HF_HUB_CACHE") or "").strip()
try:
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
except Exception as exc:
    print(f"  runtime inventory: unreadable ({exc})")
    raise SystemExit(0)
variants = list(inventory.get("variants") or [])
variant = None
if default_mode:
    for row in variants:
        if default_mode in {str(row.get("variant_id") or ""), str(row.get("upstream_tag") or ""), str(row.get("compose_rel_path") or "")}:
            variant = row
            break
print(f"  runtime inventory: {inventory_path}")
if not default_mode:
    print("  selected mode inventory: <auto mode not resolved before setup>")
    raise SystemExit(0)
if not variant:
    print(f"  selected mode inventory: not found for {default_mode}")
    raise SystemExit(0)
print(f"  selected mode inventory: {variant.get('variant_id') or default_mode}")

def host_path(container_path):
    path = str(container_path or "").strip()
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    for prefix in ("/models/", "models/"):
        if normalized.startswith(prefix):
            rel = normalized[len(prefix):].lstrip("/")
            if model_root:
                return os.path.join(model_root, rel)
            return f"{club_dir}/models-cache/{rel}" if club_dir else ""
    cache_prefix = "/root/.cache/huggingface/"
    if normalized.startswith(cache_prefix):
        rel = normalized[len(cache_prefix):].lstrip("/")
        cache_root = hf_hub_cache or (os.path.join(hf_home, "hub") if hf_home else "")
        return os.path.join(cache_root, rel) if cache_root else "<root huggingface cache under sudo>"
    return ""

for label, key in (("model path", "model_path"), ("draft model path", "draft_model_path"), ("projector path", "mmproj_path")):
    value = str(variant.get(key) or "").strip()
    if value:
        mapped = host_path(value)
        if mapped:
            print(f"  {label}: {value} -> {mapped}")
        else:
            print(f"  {label}: {value}")
command = str(variant.get("setup_command") or variant.get("install_command") or "").strip()
if command:
    print(f"  setup/download command: {command}")
    try:
        parts = shlex.split(command)
    except Exception:
        parts = []
    if parts and parts[0] == "hf" and "download" in parts:
        for flag in ("--local-dir", "--cache-dir"):
            if flag in parts:
                idx = parts.index(flag)
                if idx + 1 < len(parts):
                    print(f"  hf {flag[2:]}: {parts[idx + 1]}")
else:
    print("  setup/download command: <none>")
PYPREFLIGHT
}

log_resolved_pre_sudo_config
if [[ "${CLUB3090_ASSUME_YES:-}" != "1" && "${CLUB3090_ASSUME_YES:-}" != "true" && "${CLUB3090_ASSUME_YES:-}" != "yes" ]]; then
  printf '\nProceed with these settings? [Y/n] '
  read -r proceed_reply
  case "${proceed_reply}" in
    ""|Y|y|YES|Yes|yes)
      ;;
    *)
      echo "Aborted before requesting root permissions."
      exit 0
      ;;
  esac
fi
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
  local release sanitized
  release=""
  if [[ -d "${CLUB3090_DIR}/.git" ]] && command -v git >/dev/null 2>&1; then
    release="$(git -C "${CLUB3090_DIR}" describe --tags --always --dirty 2>/dev/null || true)"
  fi
  sanitized="$(printf '%s' "${release}" | tr ' /:\\' '_' | tr -cd 'A-Za-z0-9._-')"
  printf '%s' "${sanitized:-club-3090}"
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
  local run_path="${PATH:-}"
  local preserved_env=()
  if [[ -n "${HF_BIN:-}" ]]; then
    run_path="$(dirname "${HF_BIN}"):${run_path}"
  fi
  for key in MODEL_DIR HF_HOME HF_HUB_CACHE HUGGINGFACE_HUB_CACHE TRANSFORMERS_CACHE HF_TOKEN HUGGINGFACE_HUB_TOKEN; do
    if [[ -n "${!key:-}" ]]; then
      preserved_env+=("${key}=${!key}")
    fi
  done
  status_line "${label}: starting"
  status_line "${label}: command: ${command}"
  "${SUDO[@]}" env PATH="${run_path}" "${preserved_env[@]}" CLUB3090_STATUS_LABEL="${label}" CLUB3090_STATUS_CWD="${cwd}" CLUB3090_STATUS_COMMAND="${command}" CLUB3090_STATUS_HEARTBEAT_SECONDS="2" "${PYTHON_BIN}" - <<'PYRUNLIVE'
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

stage_gputemps_iomem_relaxed() {
  if grep -qw 'iomem=relaxed' /proc/cmdline 2>/dev/null; then
    return 0
  fi
  local changed=0
  if [[ -f /boot/limine.conf ]] && "${SUDO[@]}" test -w /boot/limine.conf 2>/dev/null; then
    "${SUDO[@]}" cp -a /boot/limine.conf "/boot/limine.conf.club3090.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    if "${SUDO[@]}" python3 - <<'PY'
from pathlib import Path
path = Path("/boot/limine.conf")
text = path.read_text(encoding="utf-8")
lines = []
changed = False
for line in text.splitlines(keepends=True):
    stripped = line.lstrip()
    if stripped.startswith("cmdline:") and "iomem=relaxed" not in line:
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        line = body.rstrip() + " iomem=relaxed" + newline
        changed = True
    lines.append(line)
if changed:
    path.write_text("".join(lines), encoding="utf-8")
raise SystemExit(0 if changed else 2)
PY
    then
      changed=1
    fi
  fi
  if [[ -f /etc/default/grub ]] && "${SUDO[@]}" test -w /etc/default/grub 2>/dev/null; then
    "${SUDO[@]}" cp -a /etc/default/grub "/etc/default/grub.club3090.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    if "${SUDO[@]}" python3 - <<'PY'
from pathlib import Path
import re
path = Path("/etc/default/grub")
text = path.read_text(encoding="utf-8")
changed = False
def add_flag(match):
    global changed
    value = match.group(2)
    if "iomem=relaxed" in value.split():
        return match.group(0)
    changed = True
    return f'{match.group(1)}"{value.rstrip()} iomem=relaxed"'
text2 = re.sub(r'^(GRUB_CMDLINE_LINUX_DEFAULT=)"([^"]*)"', add_flag, text, count=1, flags=re.M)
if text2 == text:
    text2 = re.sub(r'^(GRUB_CMDLINE_LINUX=)"([^"]*)"', add_flag, text, count=1, flags=re.M)
if changed:
    path.write_text(text2, encoding="utf-8")
raise SystemExit(0 if changed else 2)
PY
    then
      changed=1
      if command -v update-grub >/dev/null 2>&1; then
        "${SUDO[@]}" update-grub >/dev/null 2>&1 || true
      elif command -v grub-mkconfig >/dev/null 2>&1; then
        if [[ -d /boot/grub ]]; then
          "${SUDO[@]}" grub-mkconfig -o /boot/grub/grub.cfg >/dev/null 2>&1 || true
        elif [[ -d /boot/grub2 ]]; then
          "${SUDO[@]}" grub-mkconfig -o /boot/grub2/grub.cfg >/dev/null 2>&1 || true
        fi
      fi
    fi
  fi
  if [[ "${changed}" -eq 1 ]]; then
    echo "Staged iomem=relaxed in the bootloader so GDDR6/GDDR6X junction + VRAM telemetry can map GPU MMIO after the next reboot."
  fi
}

maybe_print_gputemps_reboot_notice() {
  local target="${CONTROL_DIR}/bin/gputemps"
  if [[ ! -x "${target}" ]]; then
    return 0
  fi
  if grep -qw 'iomem=relaxed' /proc/cmdline 2>/dev/null; then
    if "${SUDO[@]}" "${target}" --json --once >/dev/null 2>&1; then
      return 0
    fi
  fi
  echo
  echo "NOTE: Extra GPU junction/VRAM telemetry is installed, but the running kernel has not enabled the required MMIO access yet."
  echo "Reboot once after this install/update/migrate pass so iomem=relaxed takes effect and the new temperature graphs can populate."
}

unpack_gputemps_vendor_sources() {
  local target_dir="$1"
  if [[ -z "${GPUTEMPS_VENDOR_PAYLOAD_BASE64:-}" ]]; then
    echo "WARNING: Vendored gputemps payload is missing from the installer; extra GPU temperature telemetry will be unavailable." >&2
    return 1
  fi
  "${SUDO[@]}" mkdir -p "${target_dir}"
  "${SUDO[@]}" env GPUTEMPS_VENDOR_PAYLOAD_BASE64="${GPUTEMPS_VENDOR_PAYLOAD_BASE64}" "${PYTHON_BIN}" - "${target_dir}" <<'PY'
import base64
import gzip
import json
import os
import pathlib
import sys

payload = os.environ.get("GPUTEMPS_VENDOR_PAYLOAD_BASE64", "")
target = pathlib.Path(sys.argv[1])
data = json.loads(gzip.decompress(base64.b64decode(payload.encode("ascii"))).decode("utf-8"))
for name in ("gputemps.c", "nvml.h"):
    text = data.get(name)
    if not isinstance(text, str) or not text:
        raise SystemExit(f"missing vendored {name}")
    (target / name).write_text(text, encoding="utf-8")
PY
}

ensure_gputemps_helper_available() {
  if [[ "${GPU_EXTRA_TEMPS_MODE:-enable}" == "disable" ]]; then
    return 0
  fi
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    return 0
  fi
  local target="${CONTROL_DIR}/bin/gputemps"
  stage_gputemps_iomem_relaxed
  if [[ -x "${target}" ]]; then
    maybe_print_gputemps_reboot_notice
    return 0
  fi
  echo "Installing optional GDDR6/GDDR6X junction + VRAM temperature helper..."
  local source_dir="${CONTROL_DIR}/src/gputemps"
  "${SUDO[@]}" mkdir -p "${CONTROL_DIR}/bin" "${CONTROL_DIR}/include" "${source_dir}"
  ensure_command_or_install_with_timeout gcc 90 "Installing gcc for the GPU temperature helper..." gcc >/dev/null 2>&1 || return 0
  case "${OS_FAMILY}" in
    arch)
      install_packages_with_timeout 90 pciutils >/dev/null 2>&1 || true
      ;;
    debian)
      install_packages_with_timeout 90 libpci-dev >/dev/null 2>&1 || true
      ;;
  esac
  local tmp_dir src include_dir include_flags nvml_lib
  tmp_dir="$(mktemp -d)"
  if ! unpack_gputemps_vendor_sources "${source_dir}"; then
    rm -rf "${tmp_dir}"
    return 0
  fi
  src="${source_dir}/gputemps.c"
  if [[ ! -s "${src}" || ! -s "${source_dir}/nvml.h" ]]; then
    echo "WARNING: Vendored gputemps sources were not staged correctly; extra GPU temperature telemetry will be unavailable." >&2
    rm -rf "${tmp_dir}"
    return 0
  fi
  "${SUDO[@]}" install -m 0644 "${source_dir}/nvml.h" "${CONTROL_DIR}/include/nvml.h"
  include_flags=()
  for include_dir in \
    "${CONTROL_DIR}/include" \
    /usr/include \
    /usr/include/nvidia/gdk \
    /usr/local/cuda/include \
    /usr/local/cuda/targets/x86_64-linux/include \
    /opt/cuda/include; do
    if [[ -f "${include_dir}/nvml.h" ]]; then
      include_flags=("-I${include_dir}")
      break
    fi
  done
  if [[ "${#include_flags[@]}" -eq 0 ]]; then
    echo "WARNING: nvml.h was not found after staging the vendored header; extra GPU temperature telemetry will be unavailable." >&2
    rm -rf "${tmp_dir}"
    return 0
  fi
  nvml_lib=""
  for candidate in \
    /usr/lib/x86_64-linux-gnu/libnvidia-ml.so \
    /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1 \
    /usr/lib/libnvidia-ml.so \
    /usr/lib/libnvidia-ml.so.1 \
    /usr/local/cuda/lib64/libnvidia-ml.so; do
    if [[ -r "${candidate}" ]]; then
      nvml_lib="${candidate}"
      break
    fi
  done
  if [[ -n "${nvml_lib}" ]]; then
    gcc "${src}" -o "${tmp_dir}/gputemps" -O3 "${include_flags[@]}" "${nvml_lib}" -lpci >/tmp/club3090-gputemps-build.log 2>&1 || true
  else
    gcc "${src}" -o "${tmp_dir}/gputemps" -O3 "${include_flags[@]}" -lnvidia-ml -lpci >/tmp/club3090-gputemps-build.log 2>&1 || true
  fi
  if [[ ! -x "${tmp_dir}/gputemps" ]]; then
    echo "WARNING: Could not build gputemps helper; extra GPU temperature telemetry will be unavailable." >&2
    rm -rf "${tmp_dir}"
    return 0
  fi
  "${SUDO[@]}" install -m 0755 "${tmp_dir}/gputemps" "${target}"
  rm -rf "${tmp_dir}"
  echo "Installed optional GPU temperature helper at ${target}"
  maybe_print_gputemps_reboot_notice
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
ensure_gputemps_helper_available

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
"${SUDO[@]}" tee "${CONTROL_PY}" >/dev/null <<'PYCTRL'
# Injected by build.py from control.py.
PYCTRL

"${SUDO[@]}" chmod +x "${CONTROL_PY}"
log_done "Control backend written"

log_step "Writing embedded updater backend to ${UPDATER_PY}"
"${SUDO[@]}" tee "${UPDATER_PY}" >/dev/null <<'PYUPDATER'
# Injected by build.py from updater.py.
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
Environment=CLUB3090_HF_BIN=${HF_BIN}
Environment="PATH=${CONTROL_SERVICE_PATH}"
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

restart_control_plane_services_after_refresh() {
  if [[ "${CLUB3090_RUNNING_FROM_UPDATER:-0}" == "1" ]]; then
    return 0
  fi
  "${SUDO[@]}" systemctl restart club3090-control.service >/dev/null 2>&1 || true
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
  restart_control_plane_services_after_refresh
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
  restart_control_plane_services_after_refresh
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
  restart_control_plane_services_after_refresh
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
