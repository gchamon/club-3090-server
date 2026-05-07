#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="2026-05-07.v4.49"

# club-3090 headless server/control installer
# Install:
#   curl -fsSL https://tinyurl.com/club-3090-webserver | bash
# Update control/admin/proxy/console services only:
#   curl -fsSL https://tinyurl.com/club-3090-webserver | bash -s -- --update
# Custom admin/proxy ports:
#   bash install-club3090-server.sh --ports 18008:18009
# Enable loopback-only local automation API:
#   bash install-club3090-server.sh --local-automation
# Overrides:
#   CLUB3090_DIR=/path/to/club-3090 DEFAULT_MODE=vllm/dual-dflash bash install-club3090-server.sh
# If DEFAULT_MODE is unset, the installer auto-selects:
#   - vllm/default on 0-1 detected GPUs
#   - vllm/dual on 2+ detected GPUs

CONTROL_DIR="/opt/club3090-control"
NETWORK_STATE_FILE="${CONTROL_DIR}/network_state.json"
TLS_CERT_FILE="${CONTROL_DIR}/tls.crt"
TLS_KEY_FILE="${CONTROL_DIR}/tls.key"
CADDYFILE_PATH="${CONTROL_DIR}/Caddyfile"

ACTION="install"
ONLINE_MODE="disable"
ONLINE_TLS_MODE="disable"
LOCAL_AUTOMATION_MODE="disable"
PORTS_SPEC=""
while [[ "$#" -gt 0 ]]; do
  case "${1}" in
    --update)
      ACTION="update"
      shift
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
    --local-automation)
      LOCAL_AUTOMATION_MODE="enable"
      shift
      ;;
    --ports)
      if [[ "$#" -lt 2 ]]; then
        echo "ERROR: --ports requires a value like 8008:8009" >&2
        exit 1
      fi
      PORTS_SPEC="${2}"
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

if [[ "${ACTION}" == "update" && -z "${PORTS_SPEC}" ]]; then
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
FOLLOW_SH="${CONTROL_DIR}/follow-vllm-log.sh"
START_SH="${CONTROL_DIR}/start-vllm-last-mode.sh"
HEADLESS_X_SH="${CONTROL_DIR}/prepare-headless-x.sh"
ACTIVE_MODE_FILE="${CONTROL_DIR}/active_mode"
BASH_BIN="${BASH_BIN:-$(command -v bash || true)}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

ONLINE_EFFECTIVE_ENABLED="false"
ONLINE_TLS_EFFECTIVE_ENABLED="false"
LOCAL_AUTOMATION_EFFECTIVE_ENABLED="false"
if [[ "${ONLINE_MODE}" == "enable" ]]; then
  ONLINE_EFFECTIVE_ENABLED="true"
fi
if [[ "${ONLINE_TLS_MODE}" == "enable" ]]; then
  ONLINE_TLS_EFFECTIVE_ENABLED="true"
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
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
  CONTROL_ADMIN_BIND_HOST="127.0.0.1"
  CONTROL_PROXY_BIND_HOST="127.0.0.1"
  CONTROL_ADMIN_BIND_PORT="$(choose_loopback_port 18008 "${ADMIN_PORT}" "${PROXY_PORT}" "${LOCAL_API_PORT}")"
  CONTROL_PROXY_BIND_PORT="$(choose_loopback_port 18009 "${ADMIN_PORT}" "${PROXY_PORT}" "${LOCAL_API_PORT}" "${CONTROL_ADMIN_BIND_PORT}")"
  if [[ -z "${CONTROL_ADMIN_BIND_PORT:-}" || -z "${CONTROL_PROXY_BIND_PORT:-}" ]]; then
    echo "ERROR: Could not allocate internal loopback ports for Caddy-backed HTTPS mode." >&2
    exit 1
  fi
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

case "${DEFAULT_MODE}" in
  vllm/default|vllm/long-vision|vllm/long-text|vllm/bounded-thinking|vllm/tools-text|vllm/minimal|vllm/dual|vllm/dual-turbo|vllm/dual-dflash|vllm/dual-dflash-noviz|llamacpp/default|llamacpp/concurrent) ;;
  *) echo "Invalid DEFAULT_MODE: ${DEFAULT_MODE}" >&2; exit 1 ;;
esac

if [[ ! -d "${CLUB3090_DIR}" ]]; then
  echo "ERROR: CLUB3090_DIR does not exist: ${CLUB3090_DIR}" >&2
  echo "Re-run with: CLUB3090_DIR=/actual/path/to/club-3090 bash install-club3090-server.sh" >&2
  exit 1
fi

if [[ ! -f "${CLUB3090_DIR}/scripts/switch.sh" ]]; then
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

log_step() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

log_done() {
  printf '[%s] done: %s\n' "$(date +%H:%M:%S)" "$*"
}

APT_UPDATED=0
install_packages() {
  if [[ "$#" -eq 0 ]]; then
    return 0
  fi
  case "${OS_FAMILY}" in
    arch)
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
obj = {
    "firewall_manager": firewall_manager,
    "firewall_ports": [int(admin_port), int(proxy_port)],
    "upnp_ports": [int(admin_port), int(proxy_port)] if upnp_enabled == "true" else [],
    "tls_enabled": tls_enabled == "true",
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2, sort_keys=True)
os.replace(tmp, path)
PYNSTATE
}

close_tracked_online_exposure() {
  local old_fw old_ports old_upnp_ports old_port
  old_fw="$(read_network_state_field firewall_manager || true)"
  old_ports="$(read_network_state_field firewall_ports || true)"
  old_upnp_ports="$(read_network_state_field upnp_ports || true)"
  for old_port in ${old_ports//,/ }; do
    [[ "${old_port}" =~ ^[0-9]+$ ]] || continue
    case "${old_fw}" in
      ufw)
        "${SUDO[@]}" ufw delete allow "${old_port}"/tcp >/dev/null 2>&1 || true
        ;;
      firewalld)
        if command -v firewall-cmd >/dev/null 2>&1 && "${SUDO[@]}" firewall-cmd --state >/dev/null 2>&1; then
          "${SUDO[@]}" firewall-cmd --permanent --remove-port="${old_port}"/tcp >/dev/null 2>&1 || true
        fi
        ;;
      iptables)
        if command -v iptables >/dev/null 2>&1; then
          while "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${old_port}" -j ACCEPT >/dev/null 2>&1; do
            "${SUDO[@]}" iptables -D INPUT -p tcp --dport "${old_port}" -j ACCEPT >/dev/null 2>&1 || break
          done
        fi
        ;;
    esac
  done
  for old_port in ${old_upnp_ports//,/ }; do
    [[ "${old_port}" =~ ^[0-9]+$ ]] || continue
    if command -v upnpc >/dev/null 2>&1; then
      upnpc -d "${old_port}" tcp >/dev/null 2>&1 || true
    fi
  done
  if [[ "${old_fw}" == "firewalld" ]] && command -v firewall-cmd >/dev/null 2>&1 && "${SUDO[@]}" firewall-cmd --state >/dev/null 2>&1; then
    "${SUDO[@]}" firewall-cmd --reload >/dev/null 2>&1 || true
  fi
  if [[ -e "${NETWORK_STATE_FILE}" ]]; then
    "${SUDO[@]}" rm -f "${NETWORK_STATE_FILE}" >/dev/null 2>&1 || true
  fi
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

close_runtime_exposure() {
  local runtime_port
  for runtime_port in $(seq 8010 8020) $(seq 8200 8299); do
    if command -v ufw >/dev/null 2>&1; then
      "${SUDO[@]}" ufw delete allow "${runtime_port}"/tcp >/dev/null 2>&1 || true
    elif command -v firewall-cmd >/dev/null 2>&1 && "${SUDO[@]}" firewall-cmd --state >/dev/null 2>&1; then
      "${SUDO[@]}" firewall-cmd --permanent --remove-port="${runtime_port}"/tcp >/dev/null 2>&1 || true
    elif command -v iptables >/dev/null 2>&1; then
      while "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${runtime_port}" -j ACCEPT >/dev/null 2>&1; do
        "${SUDO[@]}" iptables -D INPUT -p tcp --dport "${runtime_port}" -j ACCEPT >/dev/null 2>&1 || break
      done
    fi
    if command -v upnpc >/dev/null 2>&1; then
      upnpc -d "${runtime_port}" tcp >/dev/null 2>&1 || true
    fi
  done
  if command -v firewall-cmd >/dev/null 2>&1 && "${SUDO[@]}" firewall-cmd --state >/dev/null 2>&1; then
    "${SUDO[@]}" firewall-cmd --reload >/dev/null 2>&1 || true
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
    "${SUDO[@]}" ufw allow "${ADMIN_PORT}"/tcp >/dev/null 2>&1 || true
    "${SUDO[@]}" ufw allow "${PROXY_PORT}"/tcp >/dev/null 2>&1 || true
    opened_fw=1
    firewall_manager="ufw"
  elif command -v firewall-cmd >/dev/null 2>&1 && "${SUDO[@]}" firewall-cmd --state >/dev/null 2>&1; then
    "${SUDO[@]}" firewall-cmd --permanent --add-port="${ADMIN_PORT}"/tcp >/dev/null 2>&1 || true
    "${SUDO[@]}" firewall-cmd --permanent --add-port="${PROXY_PORT}"/tcp >/dev/null 2>&1 || true
    "${SUDO[@]}" firewall-cmd --reload >/dev/null 2>&1 || true
    opened_fw=1
    firewall_manager="firewalld"
  elif command -v iptables >/dev/null 2>&1; then
    "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT >/dev/null 2>&1 || "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT >/dev/null 2>&1 || true
    "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT >/dev/null 2>&1 || "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT >/dev/null 2>&1 || true
    opened_fw=1
    firewall_manager="iptables"
  fi

  if command -v upnpc >/dev/null 2>&1 && [[ -n "${local_ip}" ]]; then
    upnpc -e "club3090-admin" -a "${local_ip}" "${ADMIN_PORT}" "${ADMIN_PORT}" tcp >/dev/null 2>&1 && opened_upnp=1 || true
    upnpc -e "club3090-proxy" -a "${local_ip}" "${PROXY_PORT}" "${PROXY_PORT}" tcp >/dev/null 2>&1 && opened_upnp=1 || true
  fi

  if [[ "${opened_fw}" -eq 0 ]]; then
    echo "WARNING: No supported firewall manager was configured automatically. Admin and proxy ports may still need manual allow rules." >&2
  fi
  if [[ "${opened_upnp}" -eq 0 ]]; then
    echo "WARNING: UPnP port forwarding was not confirmed. Router support may be unavailable or disabled." >&2
  fi
  write_network_state "${firewall_manager}" "$([[ "${opened_upnp}" -eq 1 ]] && echo true || echo false)" "${ONLINE_TLS_EFFECTIVE_ENABLED}" >/dev/null 2>&1 || true
}

ensure_local_control_access() {
  local firewall_manager="none"
  local opened_fw=0

  echo "Ensuring local/LAN access for ports ${ADMIN_PORT} (admin) and ${PROXY_PORT} (proxy)..."

  if command -v ufw >/dev/null 2>&1; then
    "${SUDO[@]}" ufw allow "${ADMIN_PORT}"/tcp >/dev/null 2>&1 || true
    "${SUDO[@]}" ufw allow "${PROXY_PORT}"/tcp >/dev/null 2>&1 || true
    opened_fw=1
    firewall_manager="ufw"
  elif command -v firewall-cmd >/dev/null 2>&1 && "${SUDO[@]}" firewall-cmd --state >/dev/null 2>&1; then
    "${SUDO[@]}" firewall-cmd --permanent --add-port="${ADMIN_PORT}"/tcp >/dev/null 2>&1 || true
    "${SUDO[@]}" firewall-cmd --permanent --add-port="${PROXY_PORT}"/tcp >/dev/null 2>&1 || true
    "${SUDO[@]}" firewall-cmd --reload >/dev/null 2>&1 || true
    opened_fw=1
    firewall_manager="firewalld"
  elif command -v iptables >/dev/null 2>&1; then
    "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT >/dev/null 2>&1 || "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${ADMIN_PORT}" -j ACCEPT >/dev/null 2>&1 || true
    "${SUDO[@]}" iptables -C INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT >/dev/null 2>&1 || "${SUDO[@]}" iptables -I INPUT -p tcp --dport "${PROXY_PORT}" -j ACCEPT >/dev/null 2>&1 || true
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
    if [[ "${ONLINE_EFFECTIVE_ENABLED}" == "true" ]]; then
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
    if [[ "${ONLINE_EFFECTIVE_ENABLED}" == "true" ]]; then
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

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "ERROR: python3 is required but was not found after dependency installation." >&2
  exit 1
fi

log_done "Dependency preparation complete"

"${SUDO[@]}" mkdir -p "${CONTROL_DIR}"

# Disable older manual GPU power-limit services from earlier setup; v2.6 manages this dynamically.
"${SUDO[@]}" systemctl disable --now nvidia-tweaks.service 2>/dev/null || true
"${SUDO[@]}" systemctl disable --now set-gpu-power.service 2>/dev/null || true

# On update, stop the previous console follower first so a noisy old version
# does not keep spamming the active TTY while files are being replaced.
if [[ "${ACTION}" == "update" ]]; then
  log_step "Stopping currently managed club-3090 services before update"
  # Stop old services before replacing files so a broken/stale Python process cannot
  # keep serving old code while the update is being installed.
  "${SUDO[@]}" systemctl stop club3090-console-log.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-control.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-caddy.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-headless-x.service 2>/dev/null || true
  "${SUDO[@]}" systemctl stop club3090-headless-x-v213.service 2>/dev/null || true
  log_done "Old services stopped"
fi

log_step "Writing embedded control backend to ${CONTROL_PY}"
"${SUDO[@]}" tee "${CONTROL_PY}" >/dev/null <<'PYCTRL'
#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import base64
import collections
import hashlib
import json
import math
import os
import platform
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

CLUB3090_DIR = os.environ.get("CLUB3090_DIR", "/opt/ai/club-3090")
CONTROL_DIR = "/opt/club3090-control"
SCRIPT_VERSION = os.environ.get("CLUB3090_SCRIPT_VERSION", "unknown")
ACTIVE_MODE_FILE = os.path.join(CONTROL_DIR, "active_mode")
LAST_GOOD_MODE_FILE = os.path.join(CONTROL_DIR, "last_good_mode")
CONTROL_LOG_FILE = os.path.join(CONTROL_DIR, "control.log")
AUDIT_LOG_FILE = os.path.join(CONTROL_DIR, "audit.log")
UI_CONFIG_FILE = os.path.join(CONTROL_DIR, "ui_config.json")
CUSTOM_PRESETS_FILE = os.path.join(CONTROL_DIR, "custom_presets.json")
INSTANCES_CONFIG_FILE = os.path.join(CONTROL_DIR, "instances.json")
SERVER_CONFIG_FILE = os.path.join(CONTROL_DIR, "server_config.json")
USERS_FILE = os.path.join(CONTROL_DIR, "users.json")
GROUPS_FILE = os.path.join(CONTROL_DIR, "groups.json")
LOCAL_API_TOKEN_FILE = os.path.join(CONTROL_DIR, "local_api_token")
INSTANCES_DIR = os.path.join(CONTROL_DIR, "instances")
DEFAULT_MODE = os.environ.get("DEFAULT_MODE", "vllm/default")
ADMIN_PORT = int(os.environ.get("CLUB3090_ADMIN_PORT", "8008"))
PROXY_PORT = int(os.environ.get("CLUB3090_PROXY_PORT", "8009"))
LOCAL_API_PORT = int(os.environ.get("CLUB3090_LOCAL_API_PORT", "10881"))
ADMIN_BIND_HOST = os.environ.get("CLUB3090_ADMIN_BIND_HOST", "0.0.0.0")
PROXY_BIND_HOST = os.environ.get("CLUB3090_PROXY_BIND_HOST", "0.0.0.0")
ADMIN_BIND_PORT = int(os.environ.get("CLUB3090_ADMIN_BIND_PORT", str(ADMIN_PORT)))
PROXY_BIND_PORT = int(os.environ.get("CLUB3090_PROXY_BIND_PORT", str(PROXY_PORT)))
HTTPS_CERT_FILE = os.path.join(CONTROL_DIR, "tls.crt")
HTTPS_KEY_FILE = os.path.join(CONTROL_DIR, "tls.key")

MODES = {
    "vllm/default": 8020,
    "vllm/long-vision": 8020,
    "vllm/long-text": 8020,
    "vllm/bounded-thinking": 8020,
    "vllm/tools-text": 8020,
    "vllm/minimal": 8020,
    "vllm/dual": 8010,
    "vllm/dual-turbo": 8011,
    "vllm/dual-dflash": 8012,
    "vllm/dual-dflash-noviz": 8013,
    "llamacpp/default": 8020,
    "llamacpp/concurrent": 8020,
}
SINGLE_GPU_MODES = (
    "vllm/default",
    "vllm/long-vision",
    "vllm/long-text",
    "vllm/bounded-thinking",
    "vllm/tools-text",
    "vllm/minimal",
    "llamacpp/default",
    "llamacpp/concurrent",
)
DUAL_GPU_MODES = (
    "vllm/dual",
    "vllm/dual-turbo",
    "vllm/dual-dflash",
    "vllm/dual-dflash-noviz",
)
VARIANT_SPECS = {
    "vllm/default": {"engine": "vllm", "compose_dir": "models/qwen3.6-27b/vllm/compose", "compose_file": "docker-compose.yml", "service": "vllm-qwen36-27b"},
    "vllm/long-vision": {"engine": "vllm", "compose_dir": "models/qwen3.6-27b/vllm/compose", "compose_file": "docker-compose.long-vision.yml", "service": "vllm-qwen36-27b-long-vision"},
    "vllm/long-text": {"engine": "vllm", "compose_dir": "models/qwen3.6-27b/vllm/compose", "compose_file": "docker-compose.long-text.yml", "service": "vllm-qwen36-27b-long-text"},
    "vllm/bounded-thinking": {"engine": "vllm", "compose_dir": "models/qwen3.6-27b/vllm/compose", "compose_file": "docker-compose.bounded-thinking.yml", "service": "vllm-qwen36-27b-bounded-thinking"},
    "vllm/tools-text": {"engine": "vllm", "compose_dir": "models/qwen3.6-27b/vllm/compose", "compose_file": "docker-compose.tools-text.yml", "service": "vllm-qwen36-27b"},
    "vllm/minimal": {"engine": "vllm", "compose_dir": "models/qwen3.6-27b/vllm/compose", "compose_file": "docker-compose.minimal.yml", "service": "vllm-qwen36-27b-minimal"},
    "llamacpp/default": {"engine": "llamacpp", "compose_dir": "models/qwen3.6-27b/llama-cpp/compose", "compose_file": "docker-compose.yml", "service": "llama-cpp-qwen36-27b"},
    "llamacpp/concurrent": {"engine": "llamacpp", "compose_dir": "models/qwen3.6-27b/llama-cpp/compose", "compose_file": "docker-compose.concurrent.yml", "service": "llama-cpp-qwen36-27b-concurrent"},
}
INSTANCE_PORT_BASE = int(os.environ.get("CLUB3090_INSTANCE_PORT_BASE", "8200"))
PAIR_INSTANCE_PORT_BASE = int(os.environ.get("CLUB3090_PAIR_INSTANCE_PORT_BASE", "8300"))
COMPOSE_BIN = os.environ.get("CLUB3090_COMPOSE_BIN", "docker compose")

PRESETS = {
    "chat": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5, "repetition_penalty": 1.0,
    },
    "general": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5, "repetition_penalty": 1.0,
    },
    "coding": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "coding_fast": {
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0.8, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 0, "repetition_penalty": 1.0,
    },
    "thinking": {
        "chat_template_kwargs": {"enable_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5,
    },
    "preserve-thinking": {
        "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": True},
        "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0,
        "presence_penalty": 1.5,
    },
}

DEFAULT_PRESET_DESCRIPTIONS = {
    "chat": "No thinking, temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 1.5.",
    "general": "No thinking, lower temperature 0.7, top_p 0.8, top_k 20, presence penalty 1.5.",
    "coding": "Coding-tuned sampling: no thinking, temperature 0.6, top_p 0.95, no presence penalty.",
    "coding_fast": "Faster/looser coding preset: no thinking, temperature 0.8, top_p 0.95, no presence penalty.",
    "thinking": "Enables Qwen thinking with temperature 1.0, top_p 0.95, presence penalty 1.5.",
    "preserve-thinking": "Enables thinking and preserves thinking output with same as above parameters.",
}
LENGTH_PREFIXES = {"short-": 4096, "concise-": 512}
HOP_HEADERS = {"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade","content-length","host"}

switch_lock = threading.Lock()
metrics_lock = threading.Lock()
auth_cache = {}
AUTH_CACHE_SECONDS = 120
startup_time = time.time()
recent_requests = collections.deque(maxlen=120)
series_points = collections.deque(maxlen=240)
request_queue = collections.deque(maxlen=50)
metrics = {"total_requests":0,"active_requests":0,"completed_requests":0,"failed_requests":0,"streaming_requests":0,"queued_requests":0,"cold_starts":0,"failovers":0,"last_latency_s":None,"last_ttft_s":None,"last_tokens_per_second":None,"last_estimated_tokens":None,"last_preset":None,"last_path":None,"last_status":None}
LOG_BOOTSTRAP_MARKER = os.environ.get("CLUB3090_LOG_BOOTSTRAP_MARKER", "Application Started")
LOG_TAIL_MAX_BYTES = int(os.environ.get("CLUB3090_LOG_TAIL_MAX_BYTES", "102400"))
runtime_log_watchers = {}
runtime_log_watchers_lock = threading.Lock()
latest_gpu_rows = []
latest_system_snapshot = {"memory": {}, "cpu": {"cores": []}, "disks": [], "network": {}, "info": {}}
latest_metrics_collected_at = 0.0
disk_stats_cache = {"value": [], "time": 0.0}
system_info_cache = {"value": {}, "time": 0.0}
status_snapshot_cache = {}
status_snapshot_updated_at = 0.0
status_snapshot_lock = threading.Lock()
slow_cache_lock = threading.Lock()
docker_names_cache = {
    "running": {"value": [], "time": 0.0},
    "all": {"value": [], "time": 0.0},
}
service_status_cache = {}
gpu_count_cache = {"value": 0, "time": 0.0}
compose_metadata_cache = {}
runtime_log_metrics_cache = {}
target_request_metrics = {}

POWER_IDLE_AFTER_SECONDS = int(os.environ.get("CLUB3090_POWER_IDLE_AFTER_SECONDS", "600"))
CONTAINER_STOP_AFTER_SECONDS = int(os.environ.get("CLUB3090_CONTAINER_STOP_AFTER_SECONDS", "3600"))
CONTAINER_AUTO_STOP_ENABLED = False
GPU_ACTIVE_POWER_LIMIT_W = int(os.environ.get("CLUB3090_GPU_ACTIVE_POWER_LIMIT_W", "280"))
GPU_IDLE_POWER_LIMIT_W = int(os.environ.get("CLUB3090_GPU_IDLE_POWER_LIMIT_W", "120"))
GPU_IDLE_LOCK_CLOCKS = os.environ.get("CLUB3090_GPU_IDLE_LOCK_CLOCKS", "210,900")
GPU_ACTIVE_LOCK_CLOCKS = os.environ.get("CLUB3090_GPU_ACTIVE_LOCK_CLOCKS", "")
CPU_ACTIVE_GOVERNOR = os.environ.get("CLUB3090_CPU_ACTIVE_GOVERNOR", "performance")
CPU_IDLE_GOVERNOR = os.environ.get("CLUB3090_CPU_IDLE_GOVERNOR", "powersave")
FAN_CURVE = [(30, 35), (35, 40), (40, 45), (45, 55), (50, 65), (55, 75), (60, 85), (65, 95)]
FAN_MAX_SPEED = int(os.environ.get("CLUB3090_FAN_MAX_SPEED", "100"))
FAN_MIN_SAFE_SPEED = int(os.environ.get("CLUB3090_FAN_MIN_SAFE_SPEED", "35"))
WOL_MAC = os.environ.get("CLUB3090_WOL_MAC", "")
WOL_BROADCAST = os.environ.get("CLUB3090_WOL_BROADCAST", "255.255.255.255")
PERFORMANCE_PROFILES = {
    "eco": {"gpu_active": 240, "gpu_idle": 90, "idle_clocks": "210,705", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 300, "stop_after": 1800},
    "balanced": {"gpu_active": GPU_ACTIVE_POWER_LIMIT_W, "gpu_idle": GPU_IDLE_POWER_LIMIT_W, "idle_clocks": GPU_IDLE_LOCK_CLOCKS, "cpu_active": CPU_ACTIVE_GOVERNOR, "cpu_idle": CPU_IDLE_GOVERNOR, "idle_after": POWER_IDLE_AFTER_SECONDS, "stop_after": CONTAINER_STOP_AFTER_SECONDS},
    "default": {"gpu_active": 280, "gpu_idle": 120, "idle_clocks": "", "cpu_active": "schedutil", "cpu_idle": "powersave", "idle_after": 900, "stop_after": 3600},
    "turbo": {"gpu_active": 350, "gpu_idle": 160, "idle_clocks": "", "cpu_active": "performance", "cpu_idle": "schedutil", "idle_after": 1800, "stop_after": 7200},
}
current_profile = "balanced"
last_inference_time = time.time()
power_optimizations_enabled = True
fan_manual_override = False
fan_curve_pause_until = 0.0
power_state = {"gpu":"unknown", "cpu":"unknown", "container":"running", "fans":"auto", "power_optimizations":"enabled", "last_action":"startup", "last_error":""}
cooling_scope_instance_id = "GLOBAL"
fan_curve_resume_token = 0

def log_control(message):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(message).rstrip() + "\n"
    try:
        with open(CONTROL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def log_audit(event_type, **fields):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    entry = {"ts": int(time.time()), "event": str(event_type)}
    for key, value in fields.items():
        try:
            json.dumps(value)
            entry[key] = value
        except Exception:
            entry[key] = str(value)
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception:
        pass


def default_target_request_metrics():
    return {
        "last_status": None,
        "last_latency_s": None,
        "last_ttft_s": None,
        "last_tokens_per_second": None,
        "last_estimated_tokens": None,
        "last_input_tokens": None,
        "last_output_tokens": None,
        "last_total_tokens": None,
        "last_tool_calls": None,
        "last_preset": None,
        "last_path": None,
        "last_request_at": 0,
    }


def snapshot_target_request_metrics():
    with metrics_lock:
        return {key: dict(value) for key, value in target_request_metrics.items()}

def read_ui_config():
    default = {
        "show_global_logs": True,
        "active_tab": "overview",
        "selected_scope": "GPU0",
        "current_log_source": "docker",
    }
    try:
        with open(UI_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        merged = dict(default)
        if "show_global_logs" in data:
            merged["show_global_logs"] = bool(data.get("show_global_logs"))
        if str(data.get("active_tab") or "") in {"overview", "system", "presets", "users", "metrics", "logs", "audit"}:
            merged["active_tab"] = str(data.get("active_tab"))
        if str(data.get("current_log_source") or "") in {"docker", "audit"}:
            merged["current_log_source"] = str(data.get("current_log_source"))
        if data.get("selected_scope") not in (None, ""):
            merged["selected_scope"] = str(data.get("selected_scope"))
        return merged
    except Exception:
        return default

def write_ui_config(data):
    current = read_ui_config()
    if "show_global_logs" in data:
        current["show_global_logs"] = bool(data["show_global_logs"])
    if str(data.get("active_tab") or "") in {"overview", "system", "presets", "users", "metrics", "logs", "audit"}:
        current["active_tab"] = str(data.get("active_tab"))
    if str(data.get("current_log_source") or "") in {"docker", "audit"}:
        current["current_log_source"] = str(data.get("current_log_source"))
    if data.get("selected_scope") not in (None, ""):
        current["selected_scope"] = str(data.get("selected_scope"))
    os.makedirs(CONTROL_DIR, exist_ok=True)
    tmp = UI_CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, separators=(",", ":"))
    os.replace(tmp, UI_CONFIG_FILE)
    return current


def read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return data


def default_server_config():
    return {
        "allow_proxy_without_api_key": True,
        "online_enabled": False,
        "upnp_enabled": False,
        "https_enabled": False,
        "https_cert_file": HTTPS_CERT_FILE,
        "https_key_file": HTTPS_KEY_FILE,
        "admin_path": "/admin",
        "local_api_enabled": False,
        "local_api_port": LOCAL_API_PORT,
        "gpu_pairing_enabled": True,
    }


def read_server_config():
    data = read_json_file(SERVER_CONFIG_FILE, {})
    if not isinstance(data, dict):
        data = {}
    merged = default_server_config()
    for key in merged:
        if key in data:
            merged[key] = data[key]
    merged["allow_proxy_without_api_key"] = bool(merged.get("allow_proxy_without_api_key", True))
    merged["online_enabled"] = bool(merged.get("online_enabled", False))
    merged["upnp_enabled"] = bool(merged.get("upnp_enabled", False))
    merged["https_enabled"] = bool(merged.get("https_enabled", False))
    merged["local_api_enabled"] = bool(merged.get("local_api_enabled", False))
    if "gpu_pairing_enabled" in data:
        merged["gpu_pairing_enabled"] = bool(data.get("gpu_pairing_enabled"))
    else:
        merged["gpu_pairing_enabled"] = detect_gpu_count_runtime() != 2
    try:
        merged["local_api_port"] = int(merged.get("local_api_port", LOCAL_API_PORT))
    except Exception:
        merged["local_api_port"] = LOCAL_API_PORT
    merged["https_cert_file"] = str(merged.get("https_cert_file") or HTTPS_CERT_FILE)
    merged["https_key_file"] = str(merged.get("https_key_file") or HTTPS_KEY_FILE)
    merged["admin_path"] = "/admin"
    return merged


def write_server_config(data):
    current = read_server_config()
    for key in ("allow_proxy_without_api_key", "online_enabled", "upnp_enabled", "https_enabled", "local_api_enabled", "gpu_pairing_enabled"):
        if key in data:
            current[key] = bool(data[key])
    if "local_api_port" in data:
        try:
            current["local_api_port"] = int(data["local_api_port"])
        except Exception:
            pass
    for key in ("https_cert_file", "https_key_file"):
        if key in data and data[key]:
            current[key] = str(data[key])
    current["admin_path"] = "/admin"
    write_json_file(SERVER_CONFIG_FILE, current)
    return current


def ensure_local_api_token():
    try:
        if os.path.exists(LOCAL_API_TOKEN_FILE):
            token = open(LOCAL_API_TOKEN_FILE, "r", encoding="utf-8").read().strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        os.makedirs(CONTROL_DIR, exist_ok=True)
        with open(LOCAL_API_TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token + "\n")
        os.chmod(LOCAL_API_TOKEN_FILE, 0o600)
        return token
    except Exception:
        return ""


def safe_user_name(name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("User name is required")
    if len(name) > 64:
        raise ValueError("User name is too long")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("User names may only contain letters, numbers, dot, underscore, and hyphen")
    return name


def normalize_limit_int(value):
    if value in ("", None, False):
        return None
    n = int(value)
    if n < 0:
        raise ValueError("Limits cannot be negative")
    return n


def normalize_limit_float(value):
    if value in ("", None, False):
        return None
    n = float(value)
    if n < 0:
        raise ValueError("Limits cannot be negative")
    return round(n, 3)


DEFAULT_USAGE_WEIGHTS = {
    "input_tokens": 1.0,
    "output_tokens": 1.0,
    "tool_calls": 4000.0,
    "thinking_seconds": 250.0,
}
USAGE_RETENTION_SECONDS = 8 * 24 * 3600


def first_defined(*values):
    for value in values:
        if value not in ("", None, False):
            return value
    return None


def normalize_weight(value, default=None, fill_defaults=False):
    if value in ("", None, False):
        if fill_defaults:
            return round(float(default or 0.0), 3)
        return None
    n = float(value)
    if n < 0:
        raise ValueError("Weights cannot be negative")
    return round(n, 3)


def normalize_limits(raw, fill_defaults=False):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "score_per_5h": normalize_limit_float(raw.get("score_per_5h")),
        "score_per_week": normalize_limit_float(raw.get("score_per_week")),
        "max_tokens_per_message": normalize_limit_int(raw.get("max_tokens_per_message")),
        "max_tool_calls_per_message": normalize_limit_int(raw.get("max_tool_calls_per_message")),
        "input_token_weight": normalize_weight(raw.get("input_token_weight"), DEFAULT_USAGE_WEIGHTS["input_tokens"], fill_defaults=fill_defaults),
        "output_token_weight": normalize_weight(raw.get("output_token_weight"), DEFAULT_USAGE_WEIGHTS["output_tokens"], fill_defaults=fill_defaults),
        "tool_call_weight": normalize_weight(raw.get("tool_call_weight"), DEFAULT_USAGE_WEIGHTS["tool_calls"], fill_defaults=fill_defaults),
        "thinking_second_weight": normalize_weight(raw.get("thinking_second_weight"), DEFAULT_USAGE_WEIGHTS["thinking_seconds"], fill_defaults=fill_defaults),
    }


def default_user_usage():
    return {
        "events": [],
        "last_request_at": 0,
    }


def usage_weights_from_limits(limits):
    limits = normalize_limits(limits or {}, fill_defaults=True)
    return {
        "input_tokens": float(limits.get("input_token_weight") or DEFAULT_USAGE_WEIGHTS["input_tokens"]),
        "output_tokens": float(limits.get("output_token_weight") or DEFAULT_USAGE_WEIGHTS["output_tokens"]),
        "tool_calls": float(limits.get("tool_call_weight") or DEFAULT_USAGE_WEIGHTS["tool_calls"]),
        "thinking_seconds": float(limits.get("thinking_second_weight") or DEFAULT_USAGE_WEIGHTS["thinking_seconds"]),
    }


def usage_score(metrics, limits):
    weights = usage_weights_from_limits(limits)
    return round(
        max(0, int(metrics.get("input_tokens") or 0)) * weights["input_tokens"]
        + max(0, int(metrics.get("output_tokens") or 0)) * weights["output_tokens"]
        + max(0, int(metrics.get("tool_calls") or 0)) * weights["tool_calls"]
        + max(0.0, float(metrics.get("thinking_seconds") or 0.0)) * weights["thinking_seconds"],
        3,
    )


def normalize_usage_event(event):
    if not isinstance(event, dict):
        return None
    try:
        ts = int(event.get("ts") or 0)
    except Exception:
        ts = 0
    try:
        status = int(event.get("status") or 0)
    except Exception:
        status = 0
    input_tokens = max(0, int(first_defined(event.get("input_tokens"), event.get("prompt_tokens"), 0) or 0))
    output_tokens = max(0, int(first_defined(event.get("output_tokens"), event.get("completion_tokens"), event.get("tokens"), 0) or 0))
    tool_calls = max(0, int(event.get("tool_calls") or 0))
    thinking_seconds = round(max(0.0, float(event.get("thinking_seconds") or 0.0)), 3)
    requests = max(0, int(event.get("requests") or 0))
    if not requests and (input_tokens or output_tokens or tool_calls or thinking_seconds):
        requests = 1
    return {
        "ts": ts,
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "thinking_seconds": thinking_seconds,
        "status": status,
    }


def prune_usage_events(events):
    keep_after = int(time.time()) - USAGE_RETENTION_SECONDS
    clean = []
    for event in events or []:
        normalized = normalize_usage_event(event)
        if normalized and int(normalized.get("ts") or 0) >= keep_after:
            clean.append(normalized)
    return clean


def usage_window_totals(events, since_ts, limits):
    totals = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_calls": 0,
        "thinking_seconds": 0.0,
        "score": 0.0,
    }
    for raw_event in events or []:
        event = normalize_usage_event(raw_event)
        if not event or int(event.get("ts") or 0) < since_ts:
            continue
        totals["requests"] += int(event.get("requests") or 0)
        totals["input_tokens"] += int(event.get("input_tokens") or 0)
        totals["output_tokens"] += int(event.get("output_tokens") or 0)
        totals["tool_calls"] += int(event.get("tool_calls") or 0)
        totals["thinking_seconds"] = round(totals["thinking_seconds"] + float(event.get("thinking_seconds") or 0.0), 3)
        totals["score"] = round(totals["score"] + usage_score(event, limits), 3)
    return totals


def normalize_group_names(value):
    items = value
    if items in ("", None, False):
        return []
    if isinstance(items, str):
        items = [x.strip() for x in items.split(",") if x.strip()]
    if not isinstance(items, list):
        raise ValueError("groups must be a list")
    names = []
    for item in items:
        name = safe_user_name(item)
        if name not in names:
            names.append(name)
    return names


def normalize_group_record(raw_name, raw):
    if not isinstance(raw, dict):
        raise ValueError("Group record must be an object")
    name = safe_user_name(raw.get("name") or raw_name)
    allowed_targets = raw.get("allowed_targets")
    if allowed_targets in (None, "", []):
        allowed_targets = ["*"]
    if isinstance(allowed_targets, str):
        allowed_targets = [x.strip() for x in allowed_targets.split(",") if x.strip()]
    if not isinstance(allowed_targets, list):
        raise ValueError("allowed_targets must be a list")
    allowed_clean = []
    for item in allowed_targets:
        item = str(item or "").strip()
        if not item:
            continue
        item_upper = item.upper()
        item_lower = item.lower()
        if item == "*" or item_lower in ("legacy", "all"):
            allowed_clean.append("*" if item == "*" or item_lower == "all" else "legacy")
            continue
        if re.fullmatch(r"GPU[0-9]+", item_upper):
            allowed_clean.append(item_upper)
            continue
        raise ValueError("Allowed targets must be *, legacy, or GPU<n>")
    if not allowed_clean:
        allowed_clean = ["*"]
    limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
    limits = normalize_limits(limits_raw)
    return {
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": int(raw.get("created_at") or time.time()),
        "description": str(raw.get("description") or "").strip(),
        "allowed_targets": sorted(set(allowed_clean), key=lambda x: ("*" not in x, x)),
        "limits": limits,
    }


def read_groups():
    data = read_json_file(GROUPS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    clean = {}
    for raw_name, raw_group in data.items():
        try:
            grp = normalize_group_record(raw_name, raw_group)
            clean[grp["name"]] = grp
        except Exception:
            continue
    return clean


def write_groups(data):
    normalized = {}
    for raw_name, raw_group in (data or {}).items():
        grp = normalize_group_record(raw_name, raw_group)
        normalized[grp["name"]] = grp
    write_json_file(GROUPS_FILE, normalized)
    return normalized


def public_group_view(group):
    return {
        "name": group["name"],
        "enabled": bool(group.get("enabled", True)),
        "created_at": int(group.get("created_at") or 0),
        "description": str(group.get("description") or ""),
        "allowed_targets": list(group.get("allowed_targets") or ["*"]),
        "limits": dict(group.get("limits") or {}),
        "resolved_limits": normalize_limits(group.get("limits") or {}, fill_defaults=True),
    }


def list_groups_public():
    return [public_group_view(g) for _, g in sorted(read_groups().items())]


def normalize_user_record(raw_name, raw):
    if not isinstance(raw, dict):
        raise ValueError("User record must be an object")
    name = safe_user_name(raw.get("name") or raw_name)
    allowed_targets = raw.get("allowed_targets")
    if allowed_targets in (None, "", []):
        allowed_targets = ["*"]
    if isinstance(allowed_targets, str):
        allowed_targets = [x.strip() for x in allowed_targets.split(",") if x.strip()]
    if not isinstance(allowed_targets, list):
        raise ValueError("allowed_targets must be a list")
    allowed_clean = []
    for item in allowed_targets:
        item = str(item or "").strip()
        if not item:
            continue
        item_upper = item.upper()
        item_lower = item.lower()
        if item == "*" or item_lower in ("legacy", "all"):
            allowed_clean.append("*" if item == "*" or item_lower == "all" else "legacy")
            continue
        if re.fullmatch(r"GPU[0-9]+", item_upper):
            allowed_clean.append(item_upper)
            continue
        raise ValueError("Allowed targets must be *, legacy, or GPU<n>")
    if not allowed_clean:
        allowed_clean = ["*"]
    groups = normalize_group_names(raw.get("groups"))
    limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else raw
    limits = normalize_limits(limits_raw)
    usage = default_user_usage()
    raw_usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    usage["last_request_at"] = int(raw_usage.get("last_request_at") or 0)
    usage["events"] = prune_usage_events(raw_usage.get("events") or [])
    api_key_hash = str(raw.get("api_key_hash") or "").strip()
    api_key_plain = str(raw.get("api_key_plain") or raw.get("api_key") or "").strip()
    if api_key_plain:
        digest = hashlib.sha256(api_key_plain.encode("utf-8")).hexdigest()
        if not api_key_hash or api_key_hash != digest:
            api_key_hash = digest
    return {
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": int(raw.get("created_at") or time.time()),
        "allowed_targets": sorted(set(allowed_clean), key=lambda x: ("*" not in x, x)),
        "groups": groups,
        "limits": limits,
        "usage": usage,
        "api_key_hash": api_key_hash,
        "api_key_plain": api_key_plain,
    }


def read_users():
    data = read_json_file(USERS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    clean = {}
    for raw_name, raw_user in data.items():
        try:
            user = normalize_user_record(raw_name, raw_user)
            clean[user["name"]] = user
        except Exception:
            continue
    return clean


def write_users(data):
    normalized = {}
    for raw_name, raw_user in (data or {}).items():
        user = normalize_user_record(raw_name, raw_user)
        normalized[user["name"]] = user
    write_json_file(USERS_FILE, normalized)
    return normalized


def effective_group_records(user):
    groups = read_groups()
    names = user.get("groups") or []
    return [groups[name] for name in names if name in groups and groups[name].get("enabled", True)]


def effective_allowed_targets(user):
    allowed = set(user.get("allowed_targets") or ["*"])
    for group in effective_group_records(user):
        allowed.update(group.get("allowed_targets") or [])
    if not allowed:
        allowed.add("*")
    return sorted(allowed, key=lambda x: ("*" not in x, x))


def effective_limits(user):
    merged = dict(user.get("limits") or {})
    for group in effective_group_records(user):
        for key, value in (group.get("limits") or {}).items():
            if merged.get(key) is None and value is not None:
                merged[key] = value
    return normalize_limits(merged, fill_defaults=True)


def public_user_view(user):
    usage = user.get("usage") or default_user_usage()
    now = int(time.time())
    effective_targets = effective_allowed_targets(user)
    merged_limits = effective_limits(user)
    window_5h = usage_window_totals(usage.get("events") or [], now - (5 * 3600), merged_limits)
    window_week = usage_window_totals(usage.get("events") or [], now - (7 * 24 * 3600), merged_limits)
    return {
        "name": user["name"],
        "enabled": bool(user.get("enabled", True)),
        "created_at": int(user.get("created_at") or 0),
        "allowed_targets": list(user.get("allowed_targets") or ["*"]),
        "groups": list(user.get("groups") or []),
        "effective_allowed_targets": effective_targets,
        "limits": dict(user.get("limits") or {}),
        "effective_limits": merged_limits,
        "usage": {
            "last_request_at": int(usage.get("last_request_at") or 0),
            "window_5h": window_5h,
            "window_week": window_week,
        },
        "has_api_key": bool(user.get("api_key_hash")),
        "api_key_available": bool(user.get("api_key_plain")),
    }


def list_users_public():
    return [public_user_view(u) for _, u in sorted(read_users().items())]


def issue_api_key_for_user(name):
    users = read_users()
    if name not in users:
        raise ValueError("User not found")
    key = "club3090_" + secrets.token_urlsafe(24)
    users[name]["api_key_hash"] = hashlib.sha256(key.encode("utf-8")).hexdigest()
    users[name]["api_key_plain"] = key
    write_users(users)
    log_control(f"USER reset_api_key name={name}")
    log_audit("user_api_key_reset", user=name)
    return key, public_user_view(users[name])


def show_api_key_for_user(name):
    users = read_users()
    if name not in users:
        raise ValueError("User not found")
    key = str(users[name].get("api_key_plain") or "").strip()
    if not key:
        raise ValueError("This API key was created before v4.46 and cannot be recovered. Reset it once to store a viewable copy.")
    return key, public_user_view(users[name])


def save_user_record(payload):
    if not isinstance(payload, dict):
        raise ValueError("User payload must be an object")
    name = safe_user_name(payload.get("name"))
    users = read_users()
    existing = users.get(name)
    merged = {
        "name": name,
        "enabled": bool(payload.get("enabled", True if existing is None else existing.get("enabled", True))),
        "created_at": int(existing.get("created_at") if existing else time.time()),
        "allowed_targets": payload.get("allowed_targets", existing.get("allowed_targets", ["*"]) if existing else ["*"]),
        "groups": payload.get("groups", existing.get("groups", []) if existing else []),
        "limits": payload.get("limits", existing.get("limits", {}) if existing else {}),
        "usage": existing.get("usage", default_user_usage()) if existing else default_user_usage(),
        "api_key_hash": existing.get("api_key_hash", "") if existing else "",
        "api_key_plain": existing.get("api_key_plain", "") if existing else "",
    }
    users[name] = normalize_user_record(name, merged)
    write_users(users)
    log_control(f"USER saved name={name}")
    log_audit("user_saved", user=name, enabled=users[name]["enabled"], allowed_targets=users[name]["allowed_targets"], limits=users[name]["limits"])
    created_key = None
    if payload.get("generate_api_key") or not users[name].get("api_key_hash"):
        created_key, view = issue_api_key_for_user(name)
        return view, created_key
    return public_user_view(users[name]), None


def delete_user_record(name):
    name = safe_user_name(name)
    users = read_users()
    if name not in users:
        raise ValueError("User not found")
    del users[name]
    write_users(users)
    log_control(f"USER deleted name={name}")
    log_audit("user_deleted", user=name)
    return list_users_public()


def save_group_record(payload):
    if not isinstance(payload, dict):
        raise ValueError("Group payload must be an object")
    name = safe_user_name(payload.get("name"))
    groups = read_groups()
    existing = groups.get(name)
    merged = {
        "name": name,
        "enabled": bool(payload.get("enabled", True if existing is None else existing.get("enabled", True))),
        "created_at": int(existing.get("created_at") if existing else time.time()),
        "description": str(payload.get("description", existing.get("description", "") if existing else "")),
        "allowed_targets": payload.get("allowed_targets", existing.get("allowed_targets", ["*"]) if existing else ["*"]),
        "limits": payload.get("limits", existing.get("limits", {}) if existing else {}),
    }
    groups[name] = normalize_group_record(name, merged)
    write_groups(groups)
    log_control(f"GROUP saved name={name}")
    log_audit("group_saved", group=name, enabled=groups[name]["enabled"], allowed_targets=groups[name]["allowed_targets"], limits=groups[name]["limits"])
    return public_group_view(groups[name])


def delete_group_record(name):
    name = safe_user_name(name)
    groups = read_groups()
    if name not in groups:
        raise ValueError("Group not found")
    del groups[name]
    write_groups(groups)
    users = read_users()
    changed = False
    for user_name, user in users.items():
        current_groups = [g for g in (user.get("groups") or []) if g != name]
        if current_groups != (user.get("groups") or []):
            user["groups"] = current_groups
            users[user_name] = normalize_user_record(user_name, user)
            changed = True
    if changed:
        write_users(users)
    log_control(f"GROUP deleted name={name}")
    log_audit("group_deleted", group=name)
    return list_groups_public()


def extract_api_key(headers):
    auth = headers.get("Authorization", "") or headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    for key in ("X-API-Key", "x-api-key", "api-key"):
        val = headers.get(key, "")
        if val:
            return str(val).strip()
    return ""


def get_user_by_api_key(raw_key):
    if not raw_key:
        return None
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    for user in read_users().values():
        if user.get("enabled", True) and user.get("api_key_hash") == digest:
            return user
    return None


def resolve_target_id(instance_id=None):
    if instance_id:
        return str(instance_id).upper()
    primary = primary_instance()
    return primary["id"] if primary else "legacy"


def target_gpu_labels(target_id):
    parsed = parse_instance_identifier(target_id)
    if not parsed:
        return []
    return [f"GPU{int(idx)}" for idx in parsed.get("gpu_indices") or []]


def user_can_access_target(user, target_id):
    allowed = set(effective_allowed_targets(user))
    if "*" in allowed or target_id in allowed:
        return True
    labels = target_gpu_labels(target_id)
    return bool(labels) and all(label in allowed for label in labels)


def is_quota_counted_path(upstream_path):
    return upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")


def estimate_text_tokens(text):
    text = str(text or "")
    return max(0, int(len(text) / 4)) if text else 0


def collect_request_text_fragments(value, out):
    if value in ("", None, False):
        return
    if isinstance(value, str):
        out.append(value)
        return
    if isinstance(value, list):
        for item in value:
            collect_request_text_fragments(item, out)
        return
    if isinstance(value, dict):
        for key in ("text", "content", "prompt", "input", "instructions", "system", "developer", "user", "assistant"):
            if key in value:
                collect_request_text_fragments(value.get(key), out)


def extract_request_usage(body):
    usage = {
        "input_tokens": 0,
        "requested_output_tokens": 0,
        "estimated_total_tokens": 0,
        "requested_tool_calls": None,
    }
    if not body:
        return usage
    text = body.decode("utf-8", errors="ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    usage["input_tokens"] = estimate_text_tokens(text)
    try:
        obj = json.loads(text)
    except Exception:
        usage["estimated_total_tokens"] = usage["input_tokens"]
        return usage
    if isinstance(obj, dict):
        fragments = []
        for key in ("messages", "prompt", "input", "instructions"):
            if key in obj:
                collect_request_text_fragments(obj.get(key), fragments)
        if fragments:
            usage["input_tokens"] = max(usage["input_tokens"], estimate_text_tokens(" ".join(fragments)))
        try:
            usage["requested_output_tokens"] = max(0, int(first_defined(obj.get("max_completion_tokens"), obj.get("max_tokens")) or 0))
        except Exception:
            usage["requested_output_tokens"] = 0
        try:
            requested_tools = first_defined(obj.get("max_tool_calls"), obj.get("max_parallel_tool_calls"))
            if requested_tools not in ("", None, False):
                usage["requested_tool_calls"] = max(0, int(requested_tools))
            elif isinstance(obj.get("tool_choice"), dict):
                usage["requested_tool_calls"] = 1
            elif str(obj.get("tool_choice") or "").strip().lower() == "required":
                usage["requested_tool_calls"] = 1
        except Exception:
            usage["requested_tool_calls"] = None
    usage["estimated_total_tokens"] = usage["input_tokens"] + usage["requested_output_tokens"]
    return usage


def user_limit_error(user, count_request, request_usage=None):
    if not count_request:
        return None
    usage = user.get("usage") or default_user_usage()
    limits = effective_limits(user)
    request_usage = request_usage or {}
    estimated_total_tokens = max(0, int(request_usage.get("estimated_total_tokens") or 0))
    max_tokens_per_message = limits.get("max_tokens_per_message")
    if max_tokens_per_message is not None and estimated_total_tokens > int(max_tokens_per_message):
        return "per-message token limit reached"
    requested_tool_calls = request_usage.get("requested_tool_calls")
    max_tool_calls_per_message = limits.get("max_tool_calls_per_message")
    if max_tool_calls_per_message is not None and requested_tool_calls is not None and int(requested_tool_calls) > int(max_tool_calls_per_message):
        return "per-message tool-call limit reached"
    now = int(time.time())
    events = usage.get("events") or []
    window_5h = usage_window_totals(events, now - (5 * 3600), limits)
    window_week = usage_window_totals(events, now - (7 * 24 * 3600), limits)
    estimated_score = usage_score({
        "input_tokens": max(0, int(request_usage.get("input_tokens") or 0)),
        "output_tokens": max(0, int(request_usage.get("requested_output_tokens") or 0)),
        "tool_calls": max(0, int(requested_tool_calls or 0)),
        "thinking_seconds": 0.0,
    }, limits)
    if limits.get("score_per_5h") is not None and round(window_5h["score"] + estimated_score, 3) > float(limits["score_per_5h"]):
        return "5-hour usage score limit reached"
    if limits.get("score_per_week") is not None and round(window_week["score"] + estimated_score, 3) > float(limits["score_per_week"]):
        return "weekly usage score limit reached"
    return None


def authorize_proxy_request(headers, instance_id, upstream_path, request_usage=None):
    cfg = read_server_config()
    target_id = resolve_target_id(instance_id)
    count_request = is_quota_counted_path(upstream_path)
    raw_key = extract_api_key(headers)
    user = get_user_by_api_key(raw_key) if raw_key else None
    if user is not None:
        if not user_can_access_target(user, target_id):
            log_audit("proxy_access_denied", reason="target_not_allowed", user=user["name"], target=target_id, path=upstream_path)
            return False, 403, {"error": "API key is not allowed to access this backend", "target": target_id}
        err = user_limit_error(user, count_request=count_request, request_usage=request_usage)
        if err:
            log_audit("proxy_quota_denied", user=user["name"], target=target_id, path=upstream_path, reason=err)
            return False, 429, {"error": err, "user": user["name"]}
        return True, {"mode": "user", "user_name": user["name"], "target_id": target_id, "count_request": count_request}
    if cfg.get("allow_proxy_without_api_key", True):
        return True, {"mode": "anonymous", "user_name": None, "target_id": target_id, "count_request": False}
    log_audit("proxy_auth_denied", reason="missing_or_invalid_api_key", target=target_id, path=upstream_path)
    return False, 401, {"error": "Missing or invalid API key"}


def extract_response_usage(payload):
    usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    try:
        obj = json.loads(payload.decode("utf-8", errors="ignore"))
    except Exception:
        return usage
    if isinstance(obj, dict):
        if isinstance(obj.get("usage"), dict):
            try:
                usage_block = obj["usage"]
                usage["input_tokens"] = max(0, int(first_defined(usage_block.get("prompt_tokens"), usage_block.get("input_tokens")) or 0))
                usage["output_tokens"] = max(0, int(first_defined(usage_block.get("completion_tokens"), usage_block.get("output_tokens")) or 0))
                usage["tokens"] = max(0, int(usage_block.get("total_tokens") or (usage["input_tokens"] + usage["output_tokens"])))
                if usage["output_tokens"] == 0 and usage["tokens"] and usage["input_tokens"] == 0:
                    usage["output_tokens"] = usage["tokens"]
            except Exception:
                usage["tokens"] = 0
        tool_calls = 0
        for choice in obj.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            msg = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            tool_calls += len(msg.get("tool_calls") or [])
        usage["tool_calls"] = tool_calls
    return usage


def record_user_usage(user_name, count_request, status_code, request_usage, response_usage, thinking_seconds):
    if not user_name or not count_request:
        return
    users = read_users()
    user = users.get(user_name)
    if not user:
        return
    usage = user.get("usage") or default_user_usage()
    limits = effective_limits(user)
    now = int(time.time())
    request_usage = request_usage or {}
    response_usage = response_usage or {}
    input_tokens = max(0, int(first_defined(response_usage.get("input_tokens"), request_usage.get("input_tokens"), 0) or 0))
    output_tokens = max(0, int(first_defined(response_usage.get("output_tokens"), response_usage.get("tokens"), 0) or 0))
    tool_calls = max(0, int(response_usage.get("tool_calls") or 0))
    thinking_seconds = round(max(0.0, float(thinking_seconds or 0.0)), 3)
    score = usage_score({
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "thinking_seconds": thinking_seconds,
    }, limits)
    usage["last_request_at"] = now
    usage.setdefault("events", [])
    usage["events"].append({
        "ts": now,
        "requests": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "thinking_seconds": thinking_seconds,
        "status": int(status_code or 0),
        "score": score,
    })
    usage["events"] = prune_usage_events(usage.get("events") or [])
    user["usage"] = usage
    users[user_name] = normalize_user_record(user_name, user)
    write_users(users)
    combined_tokens = input_tokens + output_tokens
    overages = []
    if limits.get("max_tokens_per_message") is not None and combined_tokens > int(limits["max_tokens_per_message"]):
        overages.append("message_tokens")
    if limits.get("max_tool_calls_per_message") is not None and tool_calls > int(limits["max_tool_calls_per_message"]):
        overages.append("message_tool_calls")
    window_5h = usage_window_totals(user["usage"].get("events") or [], now - (5 * 3600), limits)
    window_week = usage_window_totals(user["usage"].get("events") or [], now - (7 * 24 * 3600), limits)
    if limits.get("score_per_5h") is not None and window_5h["score"] > float(limits["score_per_5h"]):
        overages.append("score_5h")
    if limits.get("score_per_week") is not None and window_week["score"] > float(limits["score_per_week"]):
        overages.append("score_week")
    log_audit("proxy_usage", user=user_name, status=int(status_code or 0), input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=combined_tokens, tool_calls=tool_calls, thinking_seconds=thinking_seconds, score=score)
    if overages:
        log_audit("proxy_usage_overage", user=user_name, status=int(status_code or 0), kinds=overages, total_tokens=combined_tokens, tool_calls=tool_calls, thinking_seconds=thinking_seconds, score=score)


def local_api_token_ok(header_value):
    token = ensure_local_api_token()
    supplied = str(header_value or "").strip()
    return bool(token) and bool(supplied) and secrets.compare_digest(token, supplied)


def _safe_preset_name(name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("Preset endpoint name is required")
    if len(name) > 48:
        raise ValueError("Preset endpoint name is too long")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(ch not in allowed for ch in name):
        raise ValueError("Preset endpoint names may only contain letters, numbers, underscore, and hyphen")
    if name.startswith("short-") or name.startswith("concise-"):
        raise ValueError("Preset endpoint names cannot start with short- or concise-")
    if name in PRESETS:
        raise ValueError("Default presets cannot be overwritten")
    return name

def _coerce_preset_value(key, value):
    if value is None or value == "":
        return None
    if key in ("top_k", "max_tokens", "max_completion_tokens", "truncate_prompt_tokens", "seed", "min_tokens", "logprobs", "top_logprobs"):
        return int(value)
    if key in ("temperature", "top_p", "min_p", "presence_penalty", "frequency_penalty", "repetition_penalty", "length_penalty"):
        return float(value)
    return value

def sanitize_custom_preset(raw):
    if not isinstance(raw, dict):
        raise ValueError("Preset body must be an object")
    payload = {}
    numeric_keys = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "frequency_penalty", "repetition_penalty", "length_penalty", "max_tokens", "max_completion_tokens", "min_tokens", "truncate_prompt_tokens", "seed", "logprobs", "top_logprobs")
    for key in numeric_keys:
        if key in raw:
            val = _coerce_preset_value(key, raw.get(key))
            if val is not None:
                payload[key] = val
    boolean_keys = ("ignore_eos", "skip_special_tokens", "spaces_between_special_tokens", "include_stop_str_in_output")
    for key in boolean_keys:
        if key in raw:
            payload[key] = bool(raw.get(key))
    if "stop" in raw:
        stop_val = raw.get("stop")
        if isinstance(stop_val, str):
            stops = [x.strip() for x in stop_val.replace("\r", "").split("\n") if x.strip()]
            if len(stops) == 1 and "," in stops[0]:
                stops = [x.strip() for x in stops[0].split(",") if x.strip()]
            if stops:
                payload["stop"] = stops if len(stops) > 1 else stops[0]
        elif isinstance(stop_val, list):
            stops = [str(x) for x in stop_val if str(x)]
            if stops:
                payload["stop"] = stops
    ctk = {}
    if "enable_thinking" in raw:
        ctk["enable_thinking"] = bool(raw.get("enable_thinking"))
    if "preserve_thinking" in raw:
        ctk["preserve_thinking"] = bool(raw.get("preserve_thinking"))
        if ctk["preserve_thinking"]:
            ctk["enable_thinking"] = True
    if ctk:
        payload["chat_template_kwargs"] = ctk
    desc = str(raw.get("description") or "").strip()
    return {"params": payload, "description": desc}

def read_custom_presets():
    try:
        with open(CUSTOM_PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        clean = {}
        for name, preset in data.items():
            try:
                clean_name = _safe_preset_name(name)
            except Exception:
                continue
            if isinstance(preset, dict) and "params" in preset:
                params = preset.get("params") if isinstance(preset.get("params"), dict) else {}
                desc = str(preset.get("description") or "")
            elif isinstance(preset, dict):
                params = preset
                desc = ""
            else:
                continue
            clean[clean_name] = {"params": params, "description": desc}
        return clean
    except Exception:
        return {}

def write_custom_presets(data):
    os.makedirs(CONTROL_DIR, exist_ok=True)
    tmp = CUSTOM_PRESETS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, CUSTOM_PRESETS_FILE)
    return data

def get_all_presets():
    all_presets = {k: dict(v) for k, v in PRESETS.items()}
    for name, item in read_custom_presets().items():
        params = item.get("params") if isinstance(item, dict) else None
        if isinstance(params, dict):
            all_presets[name] = params
    return all_presets

def preset_catalog():
    defaults = []
    for name in PRESETS:
        defaults.append({"name": name, "endpoint": f"/v1/{name}", "endpoint_alt": f"/{name}", "locked": True, "params": PRESETS[name], "description": DEFAULT_PRESET_DESCRIPTIONS.get(name, "Default preset")})
    customs = []
    for name, item in sorted(read_custom_presets().items()):
        customs.append({"name": name, "endpoint": f"/v1/{name}", "endpoint_alt": f"/{name}", "locked": False, "params": item.get("params", {}), "description": item.get("description", "")})
    return {"defaults": defaults, "custom": customs, "length_prefixes": LENGTH_PREFIXES}

def save_custom_preset(name, preset_data):
    name = _safe_preset_name(name)
    custom = read_custom_presets()
    custom[name] = sanitize_custom_preset(preset_data)
    write_custom_presets(custom)
    log_control(f"PRESET saved name={name}")
    return preset_catalog()

def delete_custom_preset(name):
    name = _safe_preset_name(name)
    custom = read_custom_presets()
    if name not in custom:
        raise ValueError("Custom preset not found")
    del custom[name]
    write_custom_presets(custom)
    log_control(f"PRESET deleted name={name}")
    return preset_catalog()

def compose_cmd():
    try:
        return shlex.split(COMPOSE_BIN)
    except Exception:
        return ["docker", "compose"]

def detect_gpu_count_runtime(force=False, max_age=15):
    now = time.time()
    with slow_cache_lock:
        cached_value = int(gpu_count_cache.get("value") or 0)
        cached_time = float(gpu_count_cache.get("time") or 0.0)
    if not force and cached_time and now - cached_time < max(1.0, float(max_age or 15)):
        return cached_value
    if not shutil.which("nvidia-smi"):
        return cached_value
    value = cached_value
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.DEVNULL, timeout=1.5)
        value = sum(1 for line in out.splitlines() if line.strip())
    except Exception:
        try:
            out = subprocess.check_output(["nvidia-smi", "-L"], text=True, stderr=subprocess.DEVNULL, timeout=1.5)
            value = sum(1 for line in out.splitlines() if line.strip().startswith("GPU "))
        except Exception:
            return cached_value
    with slow_cache_lock:
        gpu_count_cache["value"] = int(value)
        gpu_count_cache["time"] = time.time()
    return int(value)

def gpu_pairing_default_enabled(gpu_count=None):
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    return count != 2

def gpu_pairing_enabled(cfg=None, gpu_count=None):
    config = cfg if isinstance(cfg, dict) else read_server_config()
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    if isinstance(config, dict) and "gpu_pairing_enabled" in config:
        return bool(config.get("gpu_pairing_enabled"))
    return gpu_pairing_default_enabled(count)

def default_instances_config():
    count = detect_gpu_count_runtime()
    rows = []
    for gpu_idx in range(count):
        rows.append({
            "id": f"GPU{gpu_idx}",
            "kind": "single",
            "gpu_indices": [gpu_idx],
            "mode": "vllm/default",
            "enabled": gpu_idx == 0 and DEFAULT_MODE in SINGLE_GPU_MODES,
            "port": INSTANCE_PORT_BASE + gpu_idx,
        })
    if count == 2 and gpu_pairing_enabled(gpu_count=count):
        rows.append({
            "id": "PAIR0_1",
            "kind": "dual",
            "gpu_indices": [0, 1],
            "mode": DEFAULT_MODE if DEFAULT_MODE in DUAL_GPU_MODES else "vllm/dual",
            "enabled": DEFAULT_MODE in DUAL_GPU_MODES,
            "port": PAIR_INSTANCE_PORT_BASE,
        })
    return rows

def normalize_pair_indices(value):
    if not isinstance(value, (list, tuple)):
        return None
    try:
        items = sorted({int(x) for x in value})
    except Exception:
        return None
    if len(items) != 2 or any(x < 0 for x in items):
        return None
    return items

def pair_instance_id(indices):
    pair = normalize_pair_indices(indices)
    if not pair:
        raise ValueError("Dual preset pairs must contain exactly two distinct GPU indices")
    return f"PAIR{pair[0]}_{pair[1]}"

def parse_instance_identifier(instance_id):
    raw = str(instance_id or "").strip().upper()
    if re.fullmatch(r"GPU[0-9]+", raw):
        idx = int(raw[3:])
        return {"id": raw, "kind": "single", "gpu_indices": [idx], "gpu_index": idx}
    match = re.fullmatch(r"PAIR([0-9]+)_([0-9]+)", raw)
    if match:
        pair = normalize_pair_indices([int(match.group(1)), int(match.group(2))])
        if not pair:
            return None
        return {"id": pair_instance_id(pair), "kind": "dual", "gpu_indices": pair, "gpu_index": pair[0]}
    return None

def instance_default_port(kind, gpu_indices):
    if kind == "dual":
        pair = normalize_pair_indices(gpu_indices)
        if not pair:
            return PAIR_INSTANCE_PORT_BASE
        return PAIR_INSTANCE_PORT_BASE + (pair[0] * 100) + pair[1]
    idx = int((gpu_indices or [0])[0])
    return INSTANCE_PORT_BASE + idx

def normalize_instance(raw, used_ids=None, used_ports=None):
    used_ids = used_ids if isinstance(used_ids, set) else set()
    used_ports = used_ports if isinstance(used_ports, set) else set()
    if not isinstance(raw, dict):
        return None
    parsed = parse_instance_identifier(raw.get("id"))
    if not parsed:
        gpu_indices = normalize_pair_indices(raw.get("gpu_indices"))
        if gpu_indices:
            parsed = parse_instance_identifier(pair_instance_id(gpu_indices))
        elif raw.get("gpu_index") not in ("", None, False):
            try:
                parsed = parse_instance_identifier(f"GPU{int(raw.get('gpu_index'))}")
            except Exception:
                parsed = None
    if not parsed:
        return None
    instance_id = parsed["id"]
    kind = parsed["kind"]
    gpu_indices = list(parsed["gpu_indices"])
    gpu_index = int(gpu_indices[0])
    mode = str(raw.get("mode") or ("vllm/dual" if kind == "dual" else "vllm/default")).strip()
    valid_modes = DUAL_GPU_MODES if kind == "dual" else SINGLE_GPU_MODES
    if mode not in valid_modes or mode not in VARIANT_SPECS:
        mode = "vllm/dual" if kind == "dual" else "vllm/default"
    try:
        port = int(raw.get("port"))
    except Exception:
        port = instance_default_port(kind, gpu_indices)
    if port < 1024:
        port = instance_default_port(kind, gpu_indices)
    if instance_id in used_ids:
        return None
    if port in used_ports:
        port = instance_default_port(kind, gpu_indices)
        while port in used_ports:
            port += 1
    used_ids.add(instance_id)
    used_ports.add(port)
    return {
        "id": instance_id,
        "kind": kind,
        "gpu_indices": gpu_indices,
        "gpu_index": gpu_index,
        "mode": mode,
        "enabled": bool(raw.get("enabled", False)),
        "port": port,
    }

def normalize_instances(rows):
    if not isinstance(rows, list):
        rows = []
    used_ids = set()
    used_ports = set()
    clean = []
    for row in rows:
        inst = normalize_instance(row, used_ids, used_ports)
        if inst is not None:
            clean.append(inst)
    count = detect_gpu_count_runtime()
    existing_ids = {inst["id"] for inst in clean}
    for gpu_idx in range(count):
        iid = f"GPU{gpu_idx}"
        if iid in existing_ids:
            continue
        inst = normalize_instance({"id": iid, "kind": "single", "gpu_indices": [gpu_idx], "mode": "vllm/default", "enabled": False, "port": INSTANCE_PORT_BASE + gpu_idx}, used_ids, used_ports)
        if inst is not None:
            clean.append(inst)
            existing_ids.add(inst["id"])
    if count == 2 and gpu_pairing_enabled(gpu_count=count) and "PAIR0_1" not in existing_ids:
        inst = normalize_instance({"id": "PAIR0_1", "kind": "dual", "gpu_indices": [0, 1], "mode": DEFAULT_MODE if DEFAULT_MODE in DUAL_GPU_MODES else "vllm/dual", "enabled": DEFAULT_MODE in DUAL_GPU_MODES, "port": PAIR_INSTANCE_PORT_BASE}, used_ids, used_ports)
        if inst is not None:
            clean.append(inst)
    if not clean:
        clean = default_instances_config()
    clean.sort(key=lambda d: (d.get("gpu_index", 9999), d.get("id", "")))
    return clean

def read_instances_config():
    try:
        with open(INSTANCES_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = normalize_instances(data)
    except Exception:
        rows = normalize_instances([])
    count = detect_gpu_count_runtime()
    changed = False
    if count == 2 and not gpu_pairing_enabled(gpu_count=count):
        filtered = [row for row in rows if row.get("kind") != "dual"]
        changed = len(filtered) != len(rows)
        rows = filtered
    if changed or not os.path.exists(INSTANCES_CONFIG_FILE):
        write_instances_config(rows)
    return rows

def write_instances_config(rows):
    rows = normalize_instances(rows)
    os.makedirs(CONTROL_DIR, exist_ok=True)
    tmp = INSTANCES_CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    os.replace(tmp, INSTANCES_CONFIG_FILE)
    return rows

def instance_container_name(instance):
    return f"club3090-{instance['id'].lower()}-{instance['mode'].replace('/', '-')}"

def instance_project_name(instance):
    return f"club3090-{instance['id'].lower()}"

def instance_paths(instance):
    base = os.path.join(INSTANCES_DIR, instance["id"])
    return {
        "dir": base,
        "env": os.path.join(base, ".env"),
        "override": os.path.join(base, "docker-compose.override.generated.yml"),
    }

def get_instance(instance_id):
    iid = str(instance_id or "").strip().upper()
    for inst in read_instances_config():
        if inst["id"] == iid:
            return inst
    return None

def instance_ready_url(instance):
    return f"http://127.0.0.1:{int(instance['port'])}/v1/models"

def instance_variant_spec(instance):
    spec = VARIANT_SPECS.get(instance["mode"])
    if not spec:
        raise ValueError(f"Unsupported instance mode: {instance['mode']}")
    return spec

def write_instance_artifacts(instance):
    spec = instance_variant_spec(instance)
    paths = instance_paths(instance)
    os.makedirs(paths["dir"], exist_ok=True)
    with open(paths["env"], "w", encoding="utf-8") as f:
        f.write(f"PORT={int(instance['port'])}\n")
        f.write("CUDA_VISIBLE_DEVICES=" + ",".join(str(int(idx)) for idx in (instance.get("gpu_indices") or [instance["gpu_index"]])) + "\n")
    override = (
        "services:\n"
        f"  {spec['service']}:\n"
        f"    container_name: {instance_container_name(instance)}\n"
        "    labels:\n"
        f"      club3090.instance_id: \"{instance['id']}\"\n"
        f"      club3090.kind: \"{instance['kind']}\"\n"
        f"      club3090.mode: \"{instance['mode']}\"\n"
        f"      club3090.gpu_indices: \"{','.join(str(int(idx)) for idx in instance.get('gpu_indices') or [instance['gpu_index']])}\"\n"
    )
    with open(paths["override"], "w", encoding="utf-8") as f:
        f.write(override)
    return paths

def instance_compose_args(instance):
    spec = instance_variant_spec(instance)
    paths = write_instance_artifacts(instance)
    compose_file = os.path.join(CLUB3090_DIR, spec["compose_dir"], spec["compose_file"])
    if not os.path.exists(compose_file):
        raise RuntimeError(f"Compose file missing for {instance['mode']}: {compose_file}")
    return compose_cmd() + ["-p", instance_project_name(instance), "--env-file", paths["env"], "-f", compose_file, "-f", paths["override"]]

def start_instance(instance_id, wait=True):
    instance = get_instance(instance_id)
    if not instance:
        raise ValueError(f"Unknown instance: {instance_id}")
    cmd = instance_compose_args(instance) + ["up", "-d"]
    rc, out = run_cmd(cmd, timeout=1800)
    log_control(f"INSTANCE start {instance['id']} mode={instance['mode']} rc={rc}: {out[-4000:]}")
    if rc != 0:
        raise RuntimeError(out or f"docker compose up failed for {instance['id']}")
    if wait and not wait_for_port(int(instance["port"]), timeout=900):
        raise RuntimeError(f"Timed out waiting for {instance['id']} on port {instance['port']}")
    return {"instance": instance, "output": out[-4000:]}

def stop_instance(instance_id):
    instance = get_instance(instance_id)
    if not instance:
        raise ValueError(f"Unknown instance: {instance_id}")
    cmd = instance_compose_args(instance) + ["down"]
    rc, out = run_cmd(cmd, timeout=600)
    if rc != 0:
        rc2, out2 = run_cmd(["docker", "rm", "-f", instance_container_name(instance)], timeout=120)
        out = (out or "") + f"\nmanual rm rc={rc2} {out2}"
    log_control(f"INSTANCE stop {instance['id']} rc={rc}: {out[-4000:]}")
    return rc, out[-4000:]

def update_instance(instance_id, mode=None, enabled=None):
    rows = read_instances_config()
    updated = None
    for row in rows:
        if row["id"] != str(instance_id or "").strip().upper():
            continue
        if mode is not None:
            valid_modes = DUAL_GPU_MODES if row.get("kind") == "dual" else SINGLE_GPU_MODES
            if mode not in valid_modes:
                raise ValueError("Selected preset type does not match this instance")
            row["mode"] = mode
        if enabled is not None:
            row["enabled"] = bool(enabled)
        updated = dict(row)
        break
    if updated is None:
        raise ValueError(f"Unknown instance: {instance_id}")
    write_instances_config(rows)
    return get_instance(updated["id"])

def save_pair_instance(gpu_indices, mode=None, enabled=None):
    if not gpu_pairing_enabled(gpu_count=detect_gpu_count_runtime()):
        raise ValueError("Enable GPU pairing before creating pair groups")
    pair = normalize_pair_indices(gpu_indices)
    if not pair:
        raise ValueError("Select exactly two distinct GPUs for a dual preset pair")
    pair_id = pair_instance_id(pair)
    rows = read_instances_config()
    existing = None
    for row in rows:
        if row["id"] == pair_id:
            existing = row
            break
    if existing is None:
        rows.append({
            "id": pair_id,
            "kind": "dual",
            "gpu_indices": pair,
            "mode": mode if mode in DUAL_GPU_MODES else "vllm/dual",
            "enabled": bool(enabled),
            "port": instance_default_port("dual", pair),
        })
    else:
        if mode is not None:
            if mode not in DUAL_GPU_MODES:
                raise ValueError("Dual GPU pairs must use a dual preset")
            existing["mode"] = mode
        if enabled is not None:
            existing["enabled"] = bool(enabled)
    write_instances_config(rows)
    return get_instance(pair_id)

def delete_pair_instance(instance_id):
    parsed = parse_instance_identifier(instance_id)
    if not parsed or parsed.get("kind") != "dual":
        raise ValueError("Only dual GPU pair groups can be removed")
    rows = read_instances_config()
    remaining = [row for row in rows if row["id"] != parsed["id"]]
    if len(remaining) == len(rows):
        raise ValueError("Pair group not found")
    try:
        stop_instance(parsed["id"])
    except Exception:
        pass
    write_instances_config(remaining)
    return instances_snapshot()

def detect_legacy_dual_mode():
    if detect_gpu_count_runtime() != 2:
        return None
    file_mode = None
    try:
        file_mode = open(ACTIVE_MODE_FILE, "r", encoding="utf-8").read().strip()
    except Exception:
        file_mode = None
    if file_mode in DUAL_GPU_MODES and port_open(MODES[file_mode], timeout=0.08):
        return file_mode
    open_dual = [mode for mode in DUAL_GPU_MODES if port_open(MODES[mode], timeout=0.08)]
    if len(open_dual) == 1:
        return open_dual[0]
    return None

def instance_uses_legacy_dual_runtime(instance):
    return bool(
        instance
        and instance.get("kind") == "dual"
        and instance.get("id") == "PAIR0_1"
        and detect_gpu_count_runtime() == 2
        and not gpu_pairing_enabled(gpu_count=2)
    )

def visible_instances(rows=None):
    items = list(rows if isinstance(rows, list) else read_instances_config())
    if gpu_pairing_enabled(gpu_count=detect_gpu_count_runtime()):
        return items
    return [inst for inst in items if inst.get("kind") != "dual"]

def instance_runtime_mode(instance):
    mode = str((instance or {}).get("mode") or "")
    if instance_uses_legacy_dual_runtime(instance):
        legacy_mode = detect_legacy_dual_mode()
        if legacy_mode in DUAL_GPU_MODES:
            return legacy_mode
    return mode

def instance_runtime_port(instance):
    if instance_uses_legacy_dual_runtime(instance):
        mode = instance_runtime_mode(instance)
        return int(MODES.get(mode, (instance or {}).get("port") or PAIR_INSTANCE_PORT_BASE))
    return int((instance or {}).get("port") or 0)

def instance_running(instance):
    return port_open(instance_runtime_port(instance), timeout=0.08)

def legacy_runtime_container_name():
    names = vllm_container_names(all_containers=False)
    if not names:
        return ""
    preferred = [name for name in names if "pair0_1" not in name.lower()]
    return preferred[0] if preferred else names[0]

def instance_runtime_container_name(instance):
    if instance_uses_legacy_dual_runtime(instance):
        return legacy_runtime_container_name()
    return instance_container_name(instance)

def legacy_global_target_mode():
    legacy_mode = detect_legacy_dual_mode()
    if legacy_mode in DUAL_GPU_MODES:
        return legacy_mode
    for candidate in (
        read_active_mode_file(),
        read_last_good_mode_file(),
        DEFAULT_MODE,
        "vllm/dual",
    ):
        if candidate in DUAL_GPU_MODES:
            return candidate
    return "vllm/dual"

def legacy_global_disable_mode():
    for row in read_instances_config():
        if row.get("kind") != "single":
            continue
        mode = str(row.get("mode") or "")
        if row.get("enabled") and mode in SINGLE_GPU_MODES:
            return mode
    return "vllm/default"

def legacy_global_enabled():
    file_mode = read_active_mode_file()
    legacy_mode = detect_legacy_dual_mode()
    if file_mode:
        return file_mode in DUAL_GPU_MODES
    return legacy_mode in DUAL_GPU_MODES

def is_legacy_global_instance_id(instance_id):
    return (
        detect_gpu_count_runtime() == 2
        and not gpu_pairing_enabled(gpu_count=2)
        and str(instance_id or "").strip().upper() == "GLOBAL"
    )

def start_legacy_global_instance(wait=True):
    mode = legacy_global_target_mode()
    output = run_switch(mode)
    if wait and not wait_for_port(int(MODES.get(mode, PAIR_INSTANCE_PORT_BASE)), timeout=900):
        raise RuntimeError(f"Timed out waiting for legacy global dual runtime on port {MODES.get(mode, PAIR_INSTANCE_PORT_BASE)}")
    return {"instance": legacy_global_instance_snapshot(), "output": output[-4000:]}

def stop_legacy_global_instance():
    p = subprocess.run(["bash", "scripts/switch.sh", "--down"], cwd=CLUB3090_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    out = (p.stdout or "")[-4000:]
    log_control(f"INSTANCE legacy global stop rc={p.returncode}: {out}")
    return p.returncode, out

def set_legacy_global_enabled(enabled):
    if bool(enabled):
        write_active_mode(legacy_global_target_mode())
    else:
        write_active_mode(legacy_global_disable_mode())
    return legacy_global_instance_snapshot()

def primary_instance():
    rows = visible_instances(read_instances_config())
    if not rows:
        return None
    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2) and detect_legacy_dual_mode():
        return None
    running = [inst for inst in rows if instance_running(inst)]
    if running:
        return sorted(running, key=lambda d: (len(d.get("gpu_indices") or [d["gpu_index"]]), d["gpu_index"], d["id"]))[0]
    enabled = [inst for inst in rows if inst.get("enabled")]
    if enabled:
        return sorted(enabled, key=lambda d: (len(d.get("gpu_indices") or [d["gpu_index"]]), d["gpu_index"], d["id"]))[0]
    return None

def boot_enabled_instances():
    outputs = []
    rows = visible_instances(read_instances_config())
    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2):
        file_mode = read_active_mode_file()
        if file_mode in DUAL_GPU_MODES:
            try:
                result = start_legacy_global_instance(wait=True)
                outputs.append(f"legacy dual started from active mode {file_mode}: {(result.get('output') or '')[-800:]}")
                log_control("BOOT instances: " + " || ".join(outputs))
                return outputs
            except Exception as e:
                outputs.append(f"legacy dual fallback failed: {e}")
    for inst in rows:
        if not inst.get("enabled"):
            continue
        try:
            result = start_instance(inst["id"], wait=True)
            outputs.append(f"{inst['id']} started: {(result.get('output') or '')[-800:]}")
        except Exception as e:
            outputs.append(f"{inst['id']} failed: {e}")
    log_control("BOOT instances: " + " || ".join(outputs))
    return outputs

def mode_gpu_indices(mode, gpu_count=None):
    if mode not in DUAL_GPU_MODES:
        return []
    try:
        count = int(gpu_count if gpu_count is not None else detect_gpu_count_runtime())
    except Exception:
        count = 0
    return [idx for idx in range(max(count, 0))][:2]

def running_dual_mode():
    rows = running_dual_instances()
    if not rows:
        return None
    rows.sort(key=lambda d: (d["gpu_indices"], d["id"]))
    return rows[0]["mode"]

def running_dual_instances():
    rows = []
    legacy = legacy_global_instance_snapshot()
    if legacy and legacy.get("running"):
        rows.append(dict(legacy))
    for inst in visible_instances(read_instances_config()):
        if inst.get("kind") != "dual" or not instance_running(inst):
            continue
        row = dict(inst)
        row["mode"] = instance_runtime_mode(inst)
        rows.append(row)
    rows.sort(key=lambda d: (d.get("gpu_indices") or [], d["id"]))
    return rows

def running_dual_instance_snapshots():
    snaps = []
    for inst in running_dual_instances():
        snaps.append(dict(inst) if "proxy_prefix" in inst else instance_snapshot(inst))
    return snaps

def stop_overlapping_instances(indices, exclude_ids=None):
    wanted = {int(idx) for idx in (indices or [])}
    excluded = {str(x or "").strip().upper() for x in (exclude_ids or [])}
    results = []
    legacy = legacy_global_instance_snapshot()
    if legacy and legacy.get("running") and legacy.get("id") not in excluded:
        legacy_indices = {int(idx) for idx in (legacy.get("gpu_indices") or [])}
        if wanted.intersection(legacy_indices):
            rc, out = stop_legacy_global_instance()
            results.append({"id": legacy["id"], "rc": rc, "output": out[-1200:]})
    for inst in read_instances_config():
        if inst["id"] in excluded:
            continue
        inst_indices = {int(idx) for idx in (inst.get("gpu_indices") or [inst.get("gpu_index", -1)])}
        if not wanted.intersection(inst_indices):
            continue
        if not instance_running(inst):
            continue
        rc, out = stop_instance(inst["id"])
        results.append({"id": inst["id"], "rc": rc, "output": out[-1200:]})
    return results

def stop_global_mode():
    stopped = stop_overlapping_instances([idx for inst in running_dual_instances() for idx in inst.get("gpu_indices") or []])
    return 0, "\n".join((row.get("output") or "") for row in stopped)[-4000:]

def stop_instances_for_gpu_indices(indices):
    return stop_overlapping_instances(indices)

def instance_assignment(instance, dual_mode=None):
    gpu_indices = [int(idx) for idx in (instance.get("gpu_indices") or [instance.get("gpu_index", -1)])]
    if instance.get("kind") == "dual":
        runtime_mode = instance_runtime_mode(instance)
        if instance_running(instance):
            return {
                "scope": "pair",
                "mode": runtime_mode,
                "text": f"GPUs {', '.join(str(idx) for idx in gpu_indices)} are running the dual preset {runtime_mode}",
                "override": False,
            }
        return {
            "scope": "pair",
            "mode": runtime_mode,
            "text": f"GPUs {', '.join(str(idx) for idx in gpu_indices)} are reserved for dual preset {runtime_mode}",
            "override": False,
        }
    for pair in running_dual_instances():
        pair_indices = {int(idx) for idx in pair.get("gpu_indices") or []}
        if set(gpu_indices).intersection(pair_indices):
            return {
                "scope": "pair",
                "mode": pair["mode"],
                "text": f"GPU {gpu_indices[0]} is currently occupied by dual pair {pair['id']} running {pair['mode']}",
                "override": True,
            }
    mode = str(instance.get("mode") or "vllm/default")
    return {
        "scope": "per-gpu",
        "mode": mode,
        "text": f"GPU {gpu_indices[0]} is assigned to the per-GPU preset {mode}",
        "override": False,
    }

def instance_snapshot(instance):
    container = instance_runtime_container_name(instance)
    runtime_mode = instance_runtime_mode(instance)
    runtime_port = instance_runtime_port(instance)
    running = port_open(runtime_port, timeout=0.1)
    assigned = instance_assignment(instance)
    return {
        "id": instance["id"],
        "kind": instance.get("kind", "single"),
        "gpu_index": instance["gpu_index"],
        "gpu_indices": list(instance.get("gpu_indices") or [instance["gpu_index"]]),
        "mode": runtime_mode,
        "enabled": bool(instance.get("enabled")),
        "port": runtime_port,
        "container": container,
        "running": running,
        "ready_url": f"http://127.0.0.1:{runtime_port}/v1/models",
        "proxy_prefix": f"/{instance['id']}",
        "display_name": instance["id"] if instance.get("kind") != "dual" else f"Pair {', '.join(str(idx) for idx in instance.get('gpu_indices') or [])}",
        "assignment_scope": assigned["scope"],
        "assignment_mode": assigned["mode"],
        "assignment_text": assigned["text"],
        "overrides_dual_mode": bool(assigned["override"]),
    }

def instances_snapshot():
    return [instance_snapshot(inst) for inst in visible_instances(read_instances_config())]

def legacy_global_instance_snapshot():
    if detect_gpu_count_runtime() != 2 or gpu_pairing_enabled(gpu_count=2):
        return None
    mode = legacy_global_target_mode()
    running_mode = detect_legacy_dual_mode()
    runtime_mode = running_mode if running_mode in DUAL_GPU_MODES else mode
    runtime_port = int(MODES.get(runtime_mode, PAIR_INSTANCE_PORT_BASE))
    running = bool(running_mode in DUAL_GPU_MODES and port_open(runtime_port, timeout=0.08))
    return {
        "id": "GLOBAL",
        "kind": "dual",
        "gpu_index": 0,
        "gpu_indices": [0, 1],
        "mode": runtime_mode,
        "enabled": legacy_global_enabled(),
        "port": runtime_port,
        "container": legacy_runtime_container_name() if running else "",
        "running": running,
        "ready_url": f"http://127.0.0.1:{runtime_port}/v1/models",
        "proxy_prefix": "/v1",
        "display_name": "Global Dual",
        "assignment_scope": "global",
        "assignment_mode": runtime_mode,
        "assignment_text": f"Global dual runtime uses GPUs 0, 1 with preset {runtime_mode}",
        "overrides_dual_mode": False,
    }

def ready_url_for_mode(mode):
    return f"http://localhost:{MODES[mode]}/v1/models"

def write_active_mode(mode):
    os.makedirs(os.path.dirname(ACTIVE_MODE_FILE), exist_ok=True)
    with open(ACTIVE_MODE_FILE, "w", encoding="utf-8") as f:
        f.write(mode)

def read_active_mode_file():
    try:
        mode = open(ACTIVE_MODE_FILE, "r", encoding="utf-8").read().strip()
        return mode if mode in MODES else None
    except Exception:
        return None

def write_last_good_mode(mode):
    if mode in MODES:
        try:
            with open(LAST_GOOD_MODE_FILE, "w", encoding="utf-8") as f:
                f.write(mode)
        except Exception:
            pass

def read_last_good_mode_file():
    try:
        mode = open(LAST_GOOD_MODE_FILE, "r", encoding="utf-8").read().strip()
        return mode if mode in MODES else None
    except Exception:
        return None

def port_open(port, timeout=0.25):
    # TCP-only readiness check. Do not call /health here; vLLM logs those.
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except Exception:
        return False

def detected_mode():
    primary = primary_instance()
    if primary:
        return primary["mode"]
    # Source of truth is the mode selected by this controller/switch.sh.
    # If the file is stale, use a TCP-only port scan as a fallback. Never call /health.
    file_mode = read_active_mode_file()
    if file_mode in MODES:
        if port_open(MODES[file_mode], timeout=0.08):
            return file_mode
        # During startup/switching the port may not be listening yet; keep the
        # intended mode unless another known mode is definitely listening.
        open_modes = [m for m, p in MODES.items() if port_open(p, timeout=0.08)]
        if len(open_modes) == 1:
            write_active_mode(open_modes[0])
            return open_modes[0]
        return file_mode
    open_modes = [m for m, p in MODES.items() if port_open(p, timeout=0.08)]
    if len(open_modes) == 1:
        write_active_mode(open_modes[0])
        return open_modes[0]
    fallback = DEFAULT_MODE if DEFAULT_MODE in MODES else "vllm/default"
    write_active_mode(fallback)
    return fallback

def active_mode():
    return detected_mode()

def active_port():
    primary = primary_instance()
    if primary:
        return int(primary["port"])
    return MODES.get(active_mode(), 8020)

def password_ok(username, password):
    if not username or not password or not shutil.which("pamtester"):
        return False
    key = (username, password)
    now = time.time()
    if key in auth_cache and now - auth_cache[key] < AUTH_CACHE_SECONDS:
        return True
    try:
        p = subprocess.run(["pamtester", "login", username, "authenticate"], input=password+"\n", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, timeout=8)
        ok = p.returncode == 0
        if ok:
            auth_cache[key] = now
        return ok
    except Exception:
        return False

def check_basic_auth(header):
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ",1)[1], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
        return password_ok(username, password)
    except Exception:
        return False

def docker_names(all_containers=False, force=False, max_age=2.0, timeout=1.5):
    cache_key = "all" if all_containers else "running"
    now = time.time()
    with slow_cache_lock:
        cached = dict(docker_names_cache.get(cache_key) or {})
        cached_value = list(cached.get("value") or [])
        cached_time = float(cached.get("time") or 0.0)
    if not force and cached_time and now - cached_time < max(0.5, float(max_age or 2.0)):
        return cached_value
    try:
        args = ["docker", "ps"]
        if all_containers:
            args.append("-a")
        args += ["--format", "{{.Names}}"]
        out = subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=max(0.5, float(timeout or 1.5)))
        names = [x.strip() for x in out.splitlines() if x.strip()]
        with slow_cache_lock:
            docker_names_cache[cache_key] = {"value": list(names), "time": time.time()}
        return names
    except Exception:
        return cached_value

def is_runtime_container_name(name):
    n = name.lower()
    return (
        ("vllm" in n and ("qwen" in n or "qwen36" in n or "club" in n))
        or ("llama-cpp" in n and ("qwen" in n or "qwen36" in n or "club" in n))
        or "qwen36" in n
        or "qwen3" in n
    )

def vllm_container_names(all_containers=False, force=False, max_age=2.0, timeout=1.5):
    return [n for n in docker_names(all_containers=all_containers, force=force, max_age=max_age, timeout=timeout) if is_runtime_container_name(n)]

def current_container():
    primary = primary_instance()
    if primary and instance_running(primary):
        return instance_runtime_container_name(primary)
    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2) and detect_legacy_dual_mode():
        legacy_name = legacy_runtime_container_name()
        if legacy_name:
            return legacy_name
    names = vllm_container_names(all_containers=False)
    return names[0] if names else ""

def parse_admin_query_params(parsed):
    if not parsed or not parsed.query:
        return {}
    try:
        return {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
    except Exception:
        return {}

def parse_tail_lines_param(params, default=250):
    raw = params.get("tail") if isinstance(params, dict) else None
    try:
        return max(0, min(1000, int(raw)))
    except Exception:
        return int(default)

def resolve_runtime_log_container(requested_instance_id=""):
    requested = str(requested_instance_id or "").strip().upper()
    if is_legacy_global_instance_id(requested):
        return None, current_container()
    instance = get_instance(requested) if requested else primary_instance()
    container = instance_runtime_container_name(instance) if instance else current_container()
    return instance, container


def split_timestamped_docker_log_line(raw):
    text = str(raw or "").rstrip("\n")
    head, sep, tail = text.partition(" ")
    if sep and re.match(r"^\d{4}-\d{2}-\d{2}T", head):
        return head, tail
    return "", text


class RuntimeLogWatcher:
    def __init__(self, container_name):
        self.container_name = str(container_name or "").strip()
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.generation = 0
        self.seq = 0
        self.status_message = ""
        self.bootstrap_lines = []
        self.bootstrap_done = False
        self.tail_lines = collections.deque()
        self.tail_bytes = 0
        self.events = collections.deque(maxlen=4096)
        self.last_timestamp = ""
        self.last_line = ""
        self.thread = threading.Thread(target=self._run, name=f"club3090-log-{self.container_name}", daemon=True)
        self.thread.start()

    def _reset_locked(self, status=""):
        self.generation += 1
        self.seq = 0
        self.status_message = str(status or "")
        self.bootstrap_lines = []
        self.bootstrap_done = False
        self.tail_lines = collections.deque()
        self.tail_bytes = 0
        self.events = collections.deque(maxlen=4096)
        self.last_timestamp = ""
        self.last_line = ""
        self.cond.notify_all()

    def _set_status(self, status):
        with self.cond:
            self.status_message = str(status or "")
            self.cond.notify_all()

    def _snapshot_text_locked(self):
        if self.bootstrap_lines or self.tail_lines:
            text = "\n".join(self.bootstrap_lines + list(self.tail_lines))
            if text and not text.endswith("\n"):
                text += "\n"
            return text
        return ((self.status_message or "waiting for logs...").rstrip("\n") + "\n")

    def snapshot(self):
        with self.cond:
            return {"generation": self.generation, "seq": self.seq, "text": self._snapshot_text_locked()}

    def wait_for_change(self, generation, seq, timeout=15):
        deadline = time.time() + max(1.0, float(timeout or 15))
        with self.cond:
            while self.generation == generation and self.seq == seq:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self.cond.wait(remaining)
            return True

    def collect_updates_since(self, generation, seq):
        with self.cond:
            if self.generation != generation:
                return {"reset": True, "generation": self.generation, "seq": self.seq, "text": self._snapshot_text_locked()}
            if seq >= self.seq:
                return {"reset": False, "generation": self.generation, "seq": self.seq, "text": ""}
            if self.events:
                first_seq = self.events[0][0]
                if seq < first_seq - 1:
                    return {"reset": True, "generation": self.generation, "seq": self.seq, "text": self._snapshot_text_locked()}
            text = "".join(chunk for event_seq, chunk in self.events if event_seq > seq)
            return {"reset": False, "generation": self.generation, "seq": self.seq, "text": text}

    def _append_line(self, line, timestamp=""):
        clean = str(line or "").rstrip("\n")
        if not clean or "GET /health HTTP/1.1" in clean:
            return
        encoded_len = len((clean + "\n").encode("utf-8", errors="replace"))
        with self.cond:
            if timestamp and timestamp == self.last_timestamp and clean == self.last_line:
                return
            self.last_timestamp = timestamp or self.last_timestamp
            self.last_line = clean
            if not self.bootstrap_done:
                self.bootstrap_lines.append(clean)
                if LOG_BOOTSTRAP_MARKER in clean:
                    self.bootstrap_done = True
            else:
                self.tail_lines.append(clean)
                self.tail_bytes += encoded_len
                while self.tail_lines and self.tail_bytes > LOG_TAIL_MAX_BYTES:
                    dropped = self.tail_lines.popleft()
                    self.tail_bytes -= len((dropped + "\n").encode("utf-8", errors="replace"))
            self.status_message = f"following {self.container_name}"
            self.seq += 1
            self.events.append((self.seq, clean + "\n"))
            self.cond.notify_all()

    def _load_initial_snapshot(self):
        try:
            p = subprocess.run(
                ["docker", "logs", "--timestamps", self.container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
            )
            output = p.stdout or ""
        except Exception as e:
            self._set_status(f"could not load docker logs for {self.container_name}: {e}")
            return "", ""
        last_timestamp = ""
        last_line = ""
        for raw in output.splitlines():
            timestamp, clean = split_timestamped_docker_log_line(raw)
            self._append_line(clean, timestamp=timestamp)
            if clean:
                last_timestamp = timestamp or last_timestamp
                last_line = clean
        if not output.strip():
            self._set_status(f"waiting for first log lines from {self.container_name}...")
        return last_timestamp, last_line

    def _run(self):
        while True:
            try:
                if self.container_name not in docker_names(all_containers=False):
                    self._set_status(f"{self.container_name} is not running; waiting...")
                    time.sleep(2)
                    continue
                with self.cond:
                    self._reset_locked(f"loading logs for {self.container_name}...")
                last_timestamp, last_line = self._load_initial_snapshot()
                cmd = ["docker", "logs", "--timestamps", "-f"]
                if last_timestamp:
                    cmd += ["--since", last_timestamp]
                else:
                    cmd += ["--tail", "0"]
                cmd.append(self.container_name)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                try:
                    if p.stdout is not None:
                        for raw in p.stdout:
                            timestamp, clean = split_timestamped_docker_log_line(raw)
                            if timestamp == last_timestamp and clean == last_line:
                                continue
                            self._append_line(clean, timestamp=timestamp)
                            if clean:
                                last_timestamp = timestamp or last_timestamp
                                last_line = clean
                finally:
                    try:
                        p.terminate()
                    except Exception:
                        pass
                self._set_status(f"log stream for {self.container_name} ended; retrying...")
            except Exception as e:
                self._set_status(f"log watcher error for {self.container_name}: {e}")
            time.sleep(2)


def get_runtime_log_watcher(container_name):
    key = str(container_name or "").strip()
    if not key:
        return None
    with runtime_log_watchers_lock:
        watcher = runtime_log_watchers.get(key)
        if watcher is None:
            watcher = RuntimeLogWatcher(key)
            runtime_log_watchers[key] = watcher
        return watcher

def cleanup_vllm_containers():
    results = []
    for inst in read_instances_config():
        try:
            rc, out = stop_instance(inst["id"])
            results.append(f"{inst['id']} down rc={rc} {out[-500:]}")
        except Exception as e:
            results.append(f"{inst['id']} down error {e}")
    names = vllm_container_names(all_containers=True, force=True, timeout=5)
    for name in names:
        if name in [instance_container_name(inst) for inst in read_instances_config()]:
            continue
        rc, out = run_cmd(["docker", "rm", "-f", name], timeout=60)
        results.append(f"docker rm -f {name}: rc={rc} {out[-500:]}")
    if not results:
        return "no club-3090 runtime containers to clean"
    msg = " || ".join(results)
    log_control("CLEANUP " + msg)
    return msg

def service_status(name):
    cache_key = str(name or "").strip()
    now = time.time()
    with slow_cache_lock:
        cached = dict(service_status_cache.get(cache_key) or {})
        cached_value = str(cached.get("value") or "")
        cached_time = float(cached.get("time") or 0.0)
    if cached_time and now - cached_time < 3.0:
        return cached_value or "unknown"
    value = cached_value or "unknown"
    try:
        value = subprocess.check_output(["systemctl","is-active",cache_key], text=True, stderr=subprocess.DEVNULL, timeout=1.0).strip() or "inactive"
    except subprocess.CalledProcessError as e:
        value = (e.output or "inactive").strip() or "inactive"
    except Exception:
        value = cached_value or "unknown"
    with slow_cache_lock:
        service_status_cache[cache_key] = {"value": value, "time": time.time()}
    return value


def compose_variant_metadata(mode):
    cache_key = str(mode or "").strip()
    default = {
        "ctx_size_tokens": None,
        "speculative_method": None,
        "drafted_tokens": None,
    }
    if not cache_key:
        return dict(default)
    with slow_cache_lock:
        cached = compose_metadata_cache.get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)
    meta = dict(default)
    spec = VARIANT_SPECS.get(cache_key) or {}
    compose_dir = str(spec.get("compose_dir") or "").strip()
    compose_file = str(spec.get("compose_file") or "").strip()
    if not compose_dir or not compose_file:
        return meta
    path = os.path.join(CLUB3090_DIR, compose_dir, compose_file)
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return meta
    for idx, raw_line in enumerate(lines):
        line = str(raw_line or "").strip()
        if not line or line.startswith("#"):
            continue
        if meta["ctx_size_tokens"] is None and "--max-model-len" in line:
            for follow in lines[idx + 1: idx + 6]:
                follow_text = str(follow or "").strip()
                if not follow_text or follow_text.startswith("#"):
                    continue
                match = re.search(r"([0-9]{4,})", follow_text)
                if match:
                    meta["ctx_size_tokens"] = int(match.group(1))
                    break
        if meta["speculative_method"] is None and "--speculative-config" in line:
            for follow in lines[idx + 1: idx + 6]:
                follow_text = str(follow or "").strip()
                if not follow_text or follow_text.startswith("#"):
                    continue
                start = follow_text.find("{")
                end = follow_text.rfind("}")
                if start < 0 or end <= start:
                    continue
                try:
                    payload = json.loads(follow_text[start:end + 1])
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    method = str(payload.get("method") or "").strip()
                    if method:
                        meta["speculative_method"] = method
                    drafted = payload.get("num_speculative_tokens")
                    if drafted not in ("", None, False):
                        try:
                            meta["drafted_tokens"] = int(drafted)
                        except Exception:
                            pass
                    break
    with slow_cache_lock:
        compose_metadata_cache[cache_key] = dict(meta)
    return dict(meta)


def _normalize_ratio_percent(value):
    number = safe_float(value)
    if number <= 1.0:
        number *= 100.0
    return round(number, 2)


def parse_runtime_log_metrics(text):
    metrics_out = {
        "prompt_tps": None,
        "generation_tps": None,
        "running_requests": None,
        "waiting_requests": None,
        "pending_requests": None,
        "swapped_requests": None,
        "gpu_kv_cache_usage_pct": None,
        "cpu_kv_cache_usage_pct": None,
        "prefix_cache_hit_rate_pct": None,
        "speculative": {},
    }
    lines = [str(line or "").strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    for line in reversed(lines):
        if metrics_out["prompt_tps"] is None and ("Avg prompt throughput:" in line or "GPU KV cache usage:" in line):
            prompt_match = re.search(r"Avg prompt throughput:\s*([0-9.]+)\s*tokens/s", line)
            gen_match = re.search(r"Avg generation throughput:\s*([0-9.]+)\s*tokens/s", line)
            running_match = re.search(r"Running:\s*([0-9]+)\s*reqs", line)
            waiting_match = re.search(r"Waiting:\s*([0-9]+)\s*reqs", line)
            pending_match = re.search(r"Pending:\s*([0-9]+)\s*reqs", line)
            swapped_match = re.search(r"Swapped:\s*([0-9]+)\s*reqs", line)
            gpu_kv_match = re.search(r"GPU KV cache usage:\s*([0-9.]+)%", line)
            cpu_kv_match = re.search(r"CPU KV cache usage:\s*([0-9.]+)%", line)
            prefix_match = re.search(r"Prefix cache hit rate:\s*(?:GPU:\s*)?([0-9.]+)%", line)
            if prompt_match:
                metrics_out["prompt_tps"] = round(safe_float(prompt_match.group(1)), 2)
            if gen_match:
                metrics_out["generation_tps"] = round(safe_float(gen_match.group(1)), 2)
            if running_match:
                metrics_out["running_requests"] = int(running_match.group(1))
            if waiting_match:
                metrics_out["waiting_requests"] = int(waiting_match.group(1))
            if pending_match:
                metrics_out["pending_requests"] = int(pending_match.group(1))
            if swapped_match:
                metrics_out["swapped_requests"] = int(swapped_match.group(1))
            if gpu_kv_match:
                metrics_out["gpu_kv_cache_usage_pct"] = round(safe_float(gpu_kv_match.group(1)), 2)
            if cpu_kv_match:
                metrics_out["cpu_kv_cache_usage_pct"] = round(safe_float(cpu_kv_match.group(1)), 2)
            if prefix_match:
                metrics_out["prefix_cache_hit_rate_pct"] = round(safe_float(prefix_match.group(1)), 2)
        if not metrics_out["speculative"] and ("Speculative metrics:" in line or "SpecDecoding metrics:" in line):
            spec = {}
            drafted_match = re.search(r"Number of speculative tokens:\s*([0-9]+)", line)
            accepted_match = re.search(r"Number of accepted tokens:\s*([0-9]+)", line)
            draft_tokens_match = re.search(r"Number of draft tokens:\s*([0-9]+)", line)
            emitted_match = re.search(r"Number of emitted tokens:\s*([0-9]+)", line)
            accept_rate_match = re.search(r"(?:Draft acceptance rate|Avg Draft acceptance rate):\s*([0-9.]+)%?", line)
            efficiency_match = re.search(r"System efficiency:\s*([0-9.]+)", line)
            mean_accept_match = re.search(r"Mean acceptance length:\s*([0-9.]+)", line)
            if drafted_match:
                spec["drafted_tokens"] = int(drafted_match.group(1))
            if accepted_match:
                spec["accepted_tokens"] = int(accepted_match.group(1))
            if draft_tokens_match:
                spec["draft_tokens"] = int(draft_tokens_match.group(1))
            if emitted_match:
                spec["emitted_tokens"] = int(emitted_match.group(1))
            if accept_rate_match:
                spec["accept_rate_pct"] = _normalize_ratio_percent(accept_rate_match.group(1))
            if efficiency_match:
                spec["system_efficiency_pct"] = _normalize_ratio_percent(efficiency_match.group(1))
            if mean_accept_match:
                spec["mean_acceptance_length"] = round(safe_float(mean_accept_match.group(1)), 2)
            if spec:
                metrics_out["speculative"] = spec
        if metrics_out["prompt_tps"] is not None and metrics_out["speculative"]:
            break
    return metrics_out


def runtime_log_metrics_for_container(container_name, force=False, max_age=1.0):
    cache_key = str(container_name or "").strip()
    if not cache_key:
        return {}
    now = time.time()
    with slow_cache_lock:
        cached = dict(runtime_log_metrics_cache.get(cache_key) or {})
        cached_value = dict(cached.get("value") or {})
        cached_time = float(cached.get("time") or 0.0)
    if not force and cached_time and now - cached_time < max(0.5, float(max_age or 1.0)):
        return cached_value
    watcher = get_runtime_log_watcher(cache_key)
    if watcher is None:
        return cached_value
    snapshot = watcher.snapshot()
    parsed = parse_runtime_log_metrics(snapshot.get("text") or "")
    with slow_cache_lock:
        runtime_log_metrics_cache[cache_key] = {"value": dict(parsed), "time": time.time()}
    return parsed


def gpu_vendors_by_index():
    vendors = []
    try:
        out = subprocess.check_output(["lspci", "-v", "-m"], text=True, stderr=subprocess.DEVNULL, timeout=4)
        block = []
        for line in out.splitlines() + [""]:
            if line.strip():
                block.append(line)
                continue
            if not block:
                continue
            rec = {}
            for b in block:
                if ":" in b:
                    k, v = b.split(":", 1)
                    rec[k.strip()] = v.strip().strip('"')
            cls = rec.get("Class", "")
            vendor = rec.get("SVendor", "")
            if ("VGA" in cls or "3D" in cls) and vendor:
                first = vendor.split()[0]
                if first and first.lower() not in ("nvidia", "corporation"):
                    vendors.append(first)
            block = []
    except Exception:
        pass
    return {str(i): v for i, v in enumerate(vendors)}

def gpu_stats():
    if not shutil.which("nvidia-smi"):
        return []
    vendor_map = gpu_vendors_by_index()
    fields = "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed,clocks.current.graphics,clocks.current.memory"
    try:
        out = subprocess.check_output(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.STDOUT, timeout=4)
    except Exception as e:
        return [{"error": str(e)}]
    rows = []
    for line in out.splitlines():
        parts = [x.strip() for x in line.split(",")]
        try:
            if len(parts) >= 11:
                idx,name,temp_core,util,mem_used,mem_total,power,power_limit,fan,gfx_clk,mem_clk = parts[:11]
            elif len(parts) >= 9:
                idx,name,temp_core,util,mem_used,mem_total,power,power_limit,fan = parts[:9]
                gfx_clk = mem_clk = "N/A"
            else:
                continue
            used = safe_float(mem_used); total = safe_float(mem_total)
            rows.append({
                "index":idx,
                "name":name,
                "vendor":vendor_map.get(str(idx), ""),
                "temp_c":temp_core,
                "util_pct":util,
                "mem_used_mib":mem_used,
                "mem_total_mib":mem_total,
                "mem_free_mib":round(max(total-used,0),1) if total else 0,
                "mem_pct":round((used/total*100),1) if total else 0,
                "power_w":power,
                "power_limit_w":power_limit,
                "fan_pct":fan,
                "core_clock_mhz":gfx_clk,
                "mem_clock_mhz":mem_clk,
            })
        except Exception as e:
            rows.append({"error": f"parse gpu stat failed: {e}"})
    return rows

def safe_float(value):
    try:
        return float(str(value).replace("N/A", "0").replace("[Not Supported]", "0").strip())
    except Exception:
        return 0.0

_cpu_prev = None

def memory_stats():
    data = {}
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8') as f:
            for line in f:
                k, v = line.split(':', 1)
                data[k] = safe_float(v.split()[0]) / 1024.0
        total = data.get('MemTotal', 0); avail = data.get('MemAvailable', 0); used = max(total-avail,0)
        return {"total_mib":round(total,1),"used_mib":round(used,1),"free_mib":round(avail,1),"used_pct":round((used/total*100),1) if total else 0}
    except Exception as e:
        return {"error": str(e)}

def _read_cpu_times():
    rows=[]
    try:
        with open('/proc/stat','r',encoding='utf-8') as f:
            for line in f:
                if not line.startswith('cpu'):
                    break
                parts=line.split()
                if parts[0]=='cpu': name='total'
                elif parts[0][3:].isdigit(): name=parts[0][3:]
                else: continue
                vals=[int(x) for x in parts[1:]]; idle=vals[3]+(vals[4] if len(vals)>4 else 0); total=sum(vals)
                rows.append((name,idle,total))
    except Exception:
        pass
    return rows

def cpu_stats():
    global _cpu_prev
    cur=_read_cpu_times()
    if not cur: return {"total_pct":0,"cores":[]}
    prev=_cpu_prev; _cpu_prev={n:(i,t) for n,i,t in cur}
    cores=[]; total_pct=0
    for name,idle,total in cur:
        pct=0.0
        if prev and name in prev:
            pi,pt=prev[name]; dt=max(total-pt,1); di=max(idle-pi,0); pct=max(0.0,min(100.0,(1-di/dt)*100))
        if name=='total': total_pct=round(pct,1)
        else: cores.append({"core":name,"usage_pct":round(pct,1)})
    return {"total_pct":total_pct,"cores":cores}

def _fmt_gib(num_bytes):
    try:
        return round(float(num_bytes) / (1024**3), 2)
    except Exception:
        return 0.0



def disk_stats():
    """Return physical disks and volumes with best-effort real filesystem
    usage. Mounted filesystems use shutil.disk_usage; unmounted ext* filesystems
    use dumpe2fs when available; lsblk FSUSED/FSAVAIL is used when populated.
    Physical disks aggregate child volume usage where real usage is known, and
    otherwise fall back to partition allocation without pretending it is FS free.
    """
    def norm_mounts(val):
        if isinstance(val, list):
            return [m for m in val if m and m != '[SWAP]']
        return [m for m in str(val or '').replace('\\x0a','\n').splitlines() if m and m != '[SWAP]']

    def walk(nodes, parent=''):
        out=[]
        for n in nodes or []:
            n=dict(n)
            n['_parent']=parent
            out.append(n)
            out.extend(walk(n.get('children') or [], n.get('name') or parent))
        return out

    def ext_usage(path):
        """Best-effort usage for unmounted ext filesystems via dumpe2fs."""
        if not path or not shutil.which('dumpe2fs'):
            return None
        try:
            p=subprocess.run(['dumpe2fs','-h',path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8)
            if p.returncode != 0:
                return None
            vals={}
            for line in p.stdout.splitlines():
                if ':' in line:
                    k,v=line.split(':',1)
                    vals[k.strip().lower()]=v.strip().split()[0]
            block_count=int(float(vals.get('block count','0')))
            free_blocks=int(float(vals.get('free blocks','0')))
            block_size=int(float(vals.get('block size','0')))
            if block_count > 0 and block_size > 0:
                total=block_count*block_size
                free=max(0, free_blocks*block_size)
                used=max(0, total-free)
                return total, used, free, 'ext filesystem'
        except Exception:
            return None
        return None

    def _first_number(text):
        import re
        m=re.search(r'([0-9][0-9,]*)', str(text or ''))
        return int(m.group(1).replace(',','')) if m else None

    def ntfs_usage(path):
        """Best-effort usage for unmounted NTFS via ntfsinfo. If the
        installed ntfsinfo does not expose free clusters/bytes, return None so
        the UI shows Unknown instead of fake Free=0/Used=Total.
        """
        if not path or not shutil.which('ntfsinfo'):
            return None
        text_parts=[]
        for args in (['ntfsinfo','-m',path], ['ntfsinfo',path]):
            try:
                p=subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
                if p.stdout:
                    text_parts.append(p.stdout)
            except Exception:
                pass
        text='\n'.join(text_parts)
        if not text:
            return None
        vals={}
        for line in text.splitlines():
            if ':' in line:
                k,v=line.split(':',1)
                vals[k.strip().lower()]=v.strip()
        def get(*keys):
            for k in keys:
                if k in vals:
                    n=_first_number(vals[k])
                    if n is not None:
                        return n
            return None
        cluster=get('cluster size','bytes per cluster','bytes/cluster')
        total_clusters=get('volume size in clusters','number of clusters','total clusters','clusters')
        free_clusters=get('free clusters')
        total_bytes=get('volume size','current volume size')
        free_bytes=get('free space','free bytes')
        if total_bytes and free_bytes is not None:
            total=total_bytes; free=max(0, free_bytes); used=max(0, total-free)
            return total, used, free, 'ntfs filesystem'
        if cluster and total_clusters and free_clusters is not None:
            total=cluster*total_clusters; free=max(0, cluster*free_clusters); used=max(0, total-free)
            return total, used, free, 'ntfs filesystem'
        return None

    rows=[]
    try:
        out=subprocess.check_output([
            'lsblk','-b','-J','-a','-o',
            'NAME,PATH,PKNAME,TYPE,FSTYPE,LABEL,PARTLABEL,PARTTYPENAME,PARTTYPE,MOUNTPOINTS,SIZE,MODEL,TRAN,FSUSED,FSAVAIL,FSSIZE'
        ], text=True, stderr=subprocess.DEVNULL, timeout=8)
        data=json.loads(out or '{}')
        flat=walk(data.get('blockdevices') or [])
        by_parent={}
        for rec in flat:
            parent=rec.get('pkname') or rec.get('_parent') or ''
            by_parent.setdefault(parent,[]).append(rec)

        usage_by_name={}
        pending_disks=[]
        for rec in flat:
            typ=(rec.get('type') or '').strip()
            if typ not in ('disk','part','crypt','lvm','raid0','raid1','raid5','raid6','raid10','md'):
                continue
            path=rec.get('path') or ('/dev/'+rec.get('name',''))
            name=rec.get('name') or path
            size=int(safe_float(rec.get('size')))
            mounts=norm_mounts(rec.get('mountpoints'))
            mount=mounts[0] if mounts else ''
            mounted=bool(mount)
            total=size; used=0; free=0; used_pct=0.0
            real_usage=False; usage_basis='allocation'

            if typ == 'disk':
                pending_disks.append(rec)
                continue

            if mounted:
                try:
                    usage=shutil.disk_usage(mount)
                    total=usage.total; used=usage.used; free=usage.free
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True; usage_basis='mounted filesystem'
                except Exception:
                    mounted=False
            if not real_usage:
                fsused=int(safe_float(rec.get('fsused')))
                fsavail=int(safe_float(rec.get('fsavail')))
                fssize=int(safe_float(rec.get('fssize')))
                if fssize > 0 and (fsused > 0 or fsavail > 0):
                    total=fssize; used=fsused; free=fsavail
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True; usage_basis='lsblk filesystem'
            fstype_lower=(rec.get('fstype') or '').lower()
            if not real_usage and fstype_lower.startswith('ext'):
                ext=ext_usage(path)
                if ext:
                    total, used, free, usage_basis = ext
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True
            if not real_usage and fstype_lower in ('ntfs','ntfs3'):
                ntfs=ntfs_usage(path)
                if ntfs:
                    total, used, free, usage_basis = ntfs
                    used_pct=round((used/total*100),1) if total else 0.0
                    real_usage=True
                else:
                    usage_basis='ntfs unmounted; free/used unknown'
            if not real_usage:
                total=size; used=None; free=None; used_pct=None
                if usage_basis == 'allocation':
                    usage_basis='unknown filesystem usage'

            usage_by_name[name]={'total':total,'used':used,'free':free,'real':real_usage,'size':size}
            label=rec.get('label') or rec.get('partlabel') or ''
            part_type=(rec.get('parttypename') or rec.get('parttype') or typ or '').strip()
            fs=(rec.get('fstype') or 'unknown').strip()
            user_facing = bool(
                typ in ('part','crypt','lvm','md') and
                fs.lower() not in ('swap',) and
                not any(x in (mount or '').lower() for x in ('/boot', '/efi')) and
                not any(x in (label or '').lower() for x in ('recovery','reserved','swap','efi','boot')) and
                not any(x in part_type.lower() for x in ('efi','reserved','recovery','bios boot','swap'))
            )
            rows.append({
                'name': name, 'path': path, 'source': path, 'type': typ,
                'kind': 'volume', 'partition_type': part_type or typ,
                'fs': fs, 'label': label, 'mount': mount, 'mounted': mounted,
                'model': (rec.get('model') or '').strip(), 'transport': rec.get('tran') or '',
                'total_gib': _fmt_gib(total) if total is not None else None, 'used_gib': _fmt_gib(used) if used is not None else None, 'free_gib': _fmt_gib(free) if free is not None else None,
                'size': f"{_fmt_gib(total)}G" if total is not None else 'unknown', 'used': f"{_fmt_gib(used)}G" if used is not None else 'unknown', 'avail': f"{_fmt_gib(free)}G" if free is not None else 'unknown',
                'used_pct': used_pct, 'user_facing': user_facing,
                'usage_basis': usage_basis
            })

        for rec in pending_disks:
            name=rec.get('name') or rec.get('path') or ''
            path=rec.get('path') or ('/dev/'+name)
            size=int(safe_float(rec.get('size')))
            children=by_parent.get(name, [])
            allocated=sum(int(safe_float(c.get('size'))) for c in children if (c.get('type') or '') in ('part','crypt','lvm','md','raid0','raid1','raid5','raid6','raid10'))
            real_children=[]
            for c in children:
                u=usage_by_name.get(c.get('name') or '')
                if u and u.get('real'):
                    real_children.append(u)
            if real_children:
                used=sum(int(u.get('used',0)) for u in real_children)
                free=sum(int(u.get('free',0)) for u in real_children)
                total=sum(int(u.get('total',0)) for u in real_children) or size
                basis='child filesystems'
            else:
                used=max(0, min(size, allocated)); free=max(0, size-used); total=size
                basis='partition allocation'
            used_pct=round((used/total*100),1) if total else 0.0
            rows.append({
                'name': name, 'path': path, 'source': path, 'type': 'disk', 'kind': 'disk',
                'partition_type': 'disk', 'fs': 'disk', 'label': '', 'mount': '', 'mounted': False,
                'model': (rec.get('model') or '').strip(), 'transport': rec.get('tran') or '',
                'total_gib': _fmt_gib(total) if total is not None else None, 'used_gib': _fmt_gib(used) if used is not None else None, 'free_gib': _fmt_gib(free) if free is not None else None,
                'size': f"{_fmt_gib(total)}G" if total is not None else 'unknown', 'used': f"{_fmt_gib(used)}G" if used is not None else 'unknown', 'avail': f"{_fmt_gib(free)}G" if free is not None else 'unknown',
                'used_pct': used_pct, 'user_facing': False, 'usage_basis': basis
            })

        order={'disk':0,'part':1,'crypt':2,'lvm':3,'md':4,'raid0':4,'raid1':4,'raid5':4,'raid6':4,'raid10':4}
        rows.sort(key=lambda d:(order.get(d.get('type'),9), d.get('path') or d.get('name') or ''))
    except Exception as e:
        rows.append({'error':str(e)})
    return rows[:128]


def system_info(gpu_rows=None):
    def read_first(path):
        try:
            return open(path, 'r', encoding='utf-8', errors='ignore').read().strip()
        except Exception:
            return ''
    os_name='unknown'
    try:
        vals={}
        with open('/etc/os-release','r',encoding='utf-8',errors='ignore') as f:
            for line in f:
                if '=' in line:
                    k,v=line.rstrip().split('=',1); vals[k]=v.strip('"')
        os_name=vals.get('PRETTY_NAME') or vals.get('NAME') or os_name
    except Exception:
        pass
    cpu_model='unknown'
    try:
        out=subprocess.check_output(['lscpu'], text=True, stderr=subprocess.DEVNULL, timeout=3)
        for line in out.splitlines():
            if line.startswith('Model name:'):
                cpu_model=line.split(':',1)[1].strip(); break
    except Exception:
        pass
    gpu_names=[]
    try:
        source_rows = gpu_rows if gpu_rows is not None else gpu_stats()
        gpu_names=[g.get('name') for g in source_rows if isinstance(g,dict) and g.get('name')]
    except Exception:
        pass
    return {
        'os': os_name,
        'kernel': platform.release(),
        'hostname': socket.gethostname(),
        'username': os.environ.get('USER') or os.environ.get('LOGNAME') or 'unknown',
        'machine': platform.machine(),
        'cpu_model': cpu_model,
        'board': read_first('/sys/devices/virtual/dmi/id/board_name'),
        'product': read_first('/sys/devices/virtual/dmi/id/product_name'),
        'bios': read_first('/sys/devices/virtual/dmi/id/bios_version'),
        'gpus': ', '.join(gpu_names) if gpu_names else 'unknown',
    }

_net_prev = None
_public_ip_cache = {'value':'unknown','time':0}


def _read_net_bytes():
    rows={}
    try:
        with open('/proc/net/dev','r',encoding='utf-8') as f:
            for line in f.readlines()[2:]:
                if ':' not in line:
                    continue
                iface, rest = line.split(':',1)
                iface=iface.strip()
                if iface == 'lo':
                    continue
                vals=rest.split()
                if len(vals) >= 16:
                    rows[iface]={'rx':int(vals[0]),'tx':int(vals[8])}
    except Exception:
        pass
    return rows


def local_ip():
    try:
        s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(('8.8.8.8',80))
        ip=s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return 'unknown'


def public_ip():
    now=time.time()
    # Avoid blocking the status endpoint every few seconds if public IP lookup
    # is unavailable. Successful lookups are cached longer than failures.
    cache_age = now - _public_ip_cache.get('time', 0)
    if _public_ip_cache.get('value') != 'unknown' and cache_age < 900:
        return _public_ip_cache['value']
    if _public_ip_cache.get('value') == 'unknown' and cache_age < 120:
        return 'unknown'
    for url in ('https://ifconfig.me/ip','https://api.ipify.org'):
        try:
            req=urllib.request.Request(url, headers={'User-Agent':'club3090-control'})
            with urllib.request.urlopen(req, timeout=1.5) as r:
                val=r.read(80).decode('utf-8','ignore').strip()
                if val:
                    _public_ip_cache.update({'value':val,'time':now})
                    return val
        except Exception:
            pass
    _public_ip_cache.update({'value':'unknown','time':now})
    return 'unknown'


def network_stats():
    global _net_prev
    now=time.time(); cur=_read_net_bytes(); prev=_net_prev; _net_prev=(now,cur)
    ifaces=[]; total_rx=total_tx=0.0
    for iface, vals in cur.items():
        rx_kbps=tx_kbps=0.0
        if prev and iface in prev[1]:
            dt=max(now-prev[0],0.001)
            rx_kbps=max(0.0,(vals['rx']-prev[1][iface]['rx'])*8/1000/dt)
            tx_kbps=max(0.0,(vals['tx']-prev[1][iface]['tx'])*8/1000/dt)
        total_rx += rx_kbps; total_tx += tx_kbps
        ifaces.append({'iface':iface,'rx_kbps':round(rx_kbps,1),'tx_kbps':round(tx_kbps,1),'rx_mb':round(vals['rx']/1024/1024,1),'tx_mb':round(vals['tx']/1024/1024,1)})
    return {'local_ip':local_ip(),'public_ip':public_ip(),'rx_kbps':round(total_rx,1),'tx_kbps':round(total_tx,1),'interfaces':ifaces}


def cached_disk_stats(max_age=15):
    now = time.time()
    cached = disk_stats_cache
    if cached.get("value") and now - float(cached.get("time", 0) or 0) < max(1.0, float(max_age or 15)):
        return cached.get("value") or []
    value = disk_stats()
    disk_stats_cache["value"] = value
    disk_stats_cache["time"] = now
    return value


def cached_system_info(gpu_rows=None, max_age=30):
    now = time.time()
    cached = system_info_cache
    cached_value = cached.get("value") if isinstance(cached.get("value"), dict) else {}
    gpu_names = ", ".join([g.get("name") for g in (gpu_rows or []) if isinstance(g, dict) and g.get("name")])
    if cached_value and now - float(cached.get("time", 0) or 0) < max(1.0, float(max_age or 30)):
        return {**cached_value, "gpus": gpu_names or cached_value.get("gpus", "unknown")}
    value = system_info(gpu_rows=gpu_rows)
    system_info_cache["value"] = value
    system_info_cache["time"] = now
    return value


def system_stats(gpu_rows=None):
    return {'memory':memory_stats(),'cpu':cpu_stats(),'disks':cached_disk_stats(),'network':network_stats(),'info':cached_system_info(gpu_rows)}

def estimate_tokens_from_stream_bytes(raw):
    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    chars = 0
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
            for choice in obj.get("choices", []):
                delta = choice.get("delta") or {}
                chars += len(delta.get("content") or choice.get("text") or "")
        except Exception:
            pass
    return max(0, int(chars / 4)) if chars else (max(1, len(text)//4) if text else 0)

def build_series_point():
    global latest_gpu_rows, latest_system_snapshot, latest_metrics_collected_at
    gpus = gpu_stats(); sysinfo = system_stats(gpu_rows=gpus)
    util=[]; mem=[]; temps=[]; watts=[]; gpu_points=[]
    for g in gpus:
        if "error" in g: continue
        util_v=safe_float(g.get("util_pct")); mem_v=safe_float(g.get("mem_pct")); temp_v=safe_float(g.get("temp_c")); watt_v=safe_float(g.get("power_w")); fan_v=safe_float(g.get("fan_pct"))
        util.append(util_v); mem.append(mem_v); temps.append(temp_v); watts.append(watt_v)
        gpu_points.append({"index":g.get("index"),"util":util_v,"mem_pct":mem_v,"temp":temp_v,"power":watt_v,"fan":fan_v})
    ram_pct=safe_float((sysinfo.get('memory') or {}).get('used_pct')); cpu_pct=safe_float((sysinfo.get('cpu') or {}).get('total_pct'))
    disks=sysinfo.get('disks') or []; disk_pct=max([safe_float(d.get('used_pct')) for d in disks if isinstance(d,dict)] or [0])
    net=sysinfo.get('network') or {}; rx_kbps=safe_float(net.get('rx_kbps')); tx_kbps=safe_float(net.get('tx_kbps'))
    with metrics_lock:
        point={"t":int(time.time()),"gpu_util":round(sum(util)/len(util),1) if util else 0,"mem_pct":round(sum(mem)/len(mem),1) if mem else 0,"temp_c":round(max(temps),1) if temps else 0,"power_w":round(sum(watts),1) if watts else 0,"ram_pct":round(ram_pct,1),"cpu_pct":round(cpu_pct,1),"disk_pct":round(disk_pct,1),"system_util_pct":round((cpu_pct+ram_pct+(sum(util)/len(util) if util else 0))/3,1),"net_rx_kbps":round(rx_kbps,1),"net_tx_kbps":round(tx_kbps,1),"gpus":gpu_points,"cpu_cores":(sysinfo.get('cpu') or {}).get('cores',[]),"active_requests":metrics.get("active_requests",0),"latency_s":metrics.get("last_latency_s") or 0,"ttft_s":metrics.get("last_ttft_s") or 0,"tps":metrics.get("last_tokens_per_second") or 0}
        series_points.append(point)
        latest_gpu_rows = gpus
        latest_system_snapshot = sysinfo
        latest_metrics_collected_at = time.time()
    return point

def metrics_collector():
    while True:
        try:
            build_series_point()
        except Exception as e:
            log_control(f"metrics collector error: {e}")
        time.sleep(1)


def get_latest_runtime_snapshot(force_refresh=False):
    with metrics_lock:
        gpus = latest_gpu_rows
        system = latest_system_snapshot
        collected_at = latest_metrics_collected_at
    if force_refresh or not collected_at:
        build_series_point()
        with metrics_lock:
            gpus = latest_gpu_rows
            system = latest_system_snapshot
            collected_at = latest_metrics_collected_at
    return gpus, system, collected_at


def build_instance_runtime_metrics_entry(instance, target_metrics_snapshot=None):
    row = dict(instance or {})
    target_metrics_snapshot = target_metrics_snapshot if isinstance(target_metrics_snapshot, dict) else {}
    request_key = str(row.get("id") or "").strip().upper()
    if request_key == "GLOBAL" and "LEGACY" in target_metrics_snapshot:
        request_key = "LEGACY"
    request_metrics = dict(target_metrics_snapshot.get(request_key) or default_target_request_metrics())
    runtime_meta = compose_variant_metadata(row.get("mode"))
    log_metrics = runtime_log_metrics_for_container(row.get("container")) if row.get("running") and row.get("container") else {}
    speculative = dict(log_metrics.get("speculative") or {})
    if speculative.get("drafted_tokens") in (None, "") and runtime_meta.get("drafted_tokens") not in (None, ""):
        speculative["drafted_tokens"] = runtime_meta.get("drafted_tokens")
    prompt_tps = log_metrics.get("prompt_tps")
    input_tokens = first_defined(request_metrics.get("last_input_tokens"), request_metrics.get("last_total_tokens"))
    estimated_prefill_s = None
    try:
        if prompt_tps not in (None, "", 0, 0.0) and input_tokens not in (None, "", 0, 0.0):
            estimated_prefill_s = round(float(input_tokens) / max(float(prompt_tps), 0.001), 3)
    except Exception:
        estimated_prefill_s = None
    return {
        "id": row.get("id"),
        "instance_id": row.get("id"),
        "display_name": row.get("display_name") or row.get("id"),
        "kind": row.get("kind"),
        "mode": row.get("mode"),
        "container": row.get("container") or "",
        "port": row.get("port"),
        "running": bool(row.get("running")),
        "gpu_indices": list(row.get("gpu_indices") or []),
        "ctx_size_tokens": runtime_meta.get("ctx_size_tokens"),
        "speculative_method": runtime_meta.get("speculative_method"),
        "prompt_tps": prompt_tps,
        "generation_tps": log_metrics.get("generation_tps"),
        "running_requests": log_metrics.get("running_requests"),
        "waiting_requests": first_defined(log_metrics.get("waiting_requests"), log_metrics.get("pending_requests")),
        "pending_requests": log_metrics.get("pending_requests"),
        "swapped_requests": log_metrics.get("swapped_requests"),
        "gpu_kv_cache_usage_pct": log_metrics.get("gpu_kv_cache_usage_pct"),
        "cpu_kv_cache_usage_pct": log_metrics.get("cpu_kv_cache_usage_pct"),
        "prefix_cache_hit_rate_pct": log_metrics.get("prefix_cache_hit_rate_pct"),
        "speculative": speculative,
        "last_status": request_metrics.get("last_status"),
        "last_latency_s": request_metrics.get("last_latency_s"),
        "last_ttft_s": request_metrics.get("last_ttft_s"),
        "last_prefill_s": estimated_prefill_s,
        "last_tokens_per_second": request_metrics.get("last_tokens_per_second"),
        "last_estimated_tokens": request_metrics.get("last_estimated_tokens"),
        "last_input_tokens": request_metrics.get("last_input_tokens"),
        "last_output_tokens": request_metrics.get("last_output_tokens"),
        "last_total_tokens": request_metrics.get("last_total_tokens"),
        "last_tool_calls": request_metrics.get("last_tool_calls"),
        "last_preset": request_metrics.get("last_preset"),
        "last_path": request_metrics.get("last_path"),
        "last_request_at": request_metrics.get("last_request_at"),
    }


def build_instance_runtime_metrics_snapshot(instances, legacy_instance, target_metrics_snapshot=None):
    rows = {}
    if legacy_instance:
        rows[str(legacy_instance.get("id") or "").strip().upper()] = build_instance_runtime_metrics_entry(legacy_instance, target_metrics_snapshot)
    for instance in instances or []:
        rows[str(instance.get("id") or "").strip().upper()] = build_instance_runtime_metrics_entry(instance, target_metrics_snapshot)
    return rows


def build_status_snapshot():
    with metrics_lock:
        m = dict(metrics)
        recent = list(recent_requests)
        series = list(series_points)
    ap = active_port()
    cfg = read_server_config()
    gpu_count = detect_gpu_count_runtime()
    instances = instances_snapshot()
    legacy_instance = legacy_global_instance_snapshot()
    target_metrics_snapshot = snapshot_target_request_metrics()
    instance_runtime_metrics = build_instance_runtime_metrics_snapshot(instances, legacy_instance, target_metrics_snapshot)
    dual_rows = []
    if legacy_instance and legacy_instance.get("running"):
        dual_rows.append(dict(legacy_instance))
    for row in instances:
        if row.get("kind") == "dual" and row.get("running"):
            dual_rows.append(dict(row))
    dual_rows.sort(key=lambda d: (d.get("gpu_indices") or [], d.get("id") or ""))
    legacy_dual_mode = legacy_instance.get("mode") if legacy_instance and legacy_instance.get("running") else None
    gpus_snapshot, system_snapshot, _ = get_latest_runtime_snapshot()
    return {
        "active_mode": active_mode(),
        "active_port": ap,
        "container": current_container(),
        "club3090_dir": CLUB3090_DIR,
        "script_version": SCRIPT_VERSION,
        "uptime_seconds": int(time.time() - startup_time),
        "vllm_service": service_status("club3090-vllm.service"),
        "control_service": service_status("club3090-control.service"),
        "caddy_service": service_status("club3090-caddy.service") if cfg.get("https_enabled", False) else "disabled",
        "console_service": service_status("club3090-console-log.service"),
        "metrics": m,
        "recent_requests": recent,
        "gpus": gpus_snapshot,
        "power": power_status(),
        "system": system_snapshot,
        "series": series,
        "ui_config": read_ui_config(),
        "presets": preset_catalog(),
        "gpu_count": gpu_count,
        "instances": instances,
        "legacy_global_instance": legacy_instance,
        "single_gpu_modes": list(SINGLE_GPU_MODES),
        "dual_gpu_modes": list(DUAL_GPU_MODES),
        "running_dual_mode": (dual_rows[0]["mode"] if dual_rows else legacy_dual_mode),
        "running_dual_gpu_indices": (dual_rows[0]["gpu_indices"] if dual_rows else ([0, 1] if legacy_dual_mode else [])),
        "running_dual_instances": dual_rows,
        "instance_runtime_metrics": instance_runtime_metrics,
        "users": list_users_public(),
        "groups": list_groups_public(),
        "server_config": cfg,
        "local_api": {"enabled": cfg.get("local_api_enabled", False), "port": cfg.get("local_api_port", LOCAL_API_PORT)},
        "admin_port": ADMIN_PORT,
        "proxy_port": PROXY_PORT,
    }


def refresh_status_snapshot():
    global status_snapshot_cache, status_snapshot_updated_at
    snapshot = build_status_snapshot()
    with status_snapshot_lock:
        status_snapshot_cache = snapshot
        status_snapshot_updated_at = time.time()
    return snapshot


def get_status_snapshot(force=False):
    with status_snapshot_lock:
        snapshot = status_snapshot_cache
        updated_at = status_snapshot_updated_at
    if force or not snapshot or not updated_at:
        return refresh_status_snapshot()
    return snapshot


def status_snapshot_collector():
    while True:
        try:
            refresh_status_snapshot()
        except Exception as e:
            log_control(f"status snapshot error: {e}")
        time.sleep(1)

def wake_on_lan(mac=None, broadcast=None):
    mac = (mac or WOL_MAC or "").replace("-", ":").strip()
    broadcast = broadcast or WOL_BROADCAST
    if not mac:
        raise ValueError("No MAC address configured or provided")
    hexmac = mac.replace(":", "")
    if len(hexmac) != 12:
        raise ValueError("Invalid MAC address")
    packet = bytes.fromhex("FF" * 6 + hexmac * 16)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(packet, (broadcast, 9))
    finally:
        sock.close()
    log_control(f"WOL sent mac={mac} broadcast={broadcast}")
    return {"mac": mac, "broadcast": broadcast}

def apply_performance_profile(name):
    global current_profile, GPU_ACTIVE_POWER_LIMIT_W, GPU_IDLE_POWER_LIMIT_W, GPU_IDLE_LOCK_CLOCKS, CPU_ACTIVE_GOVERNOR, CPU_IDLE_GOVERNOR, POWER_IDLE_AFTER_SECONDS, CONTAINER_STOP_AFTER_SECONDS
    if name not in PERFORMANCE_PROFILES:
        raise ValueError("Invalid performance profile")
    log_control(f"PROFILE requested name={name}")
    cfg = PERFORMANCE_PROFILES[name]
    GPU_ACTIVE_POWER_LIMIT_W = int(cfg["gpu_active"]); GPU_IDLE_POWER_LIMIT_W = int(cfg["gpu_idle"]); GPU_IDLE_LOCK_CLOCKS = str(cfg["idle_clocks"])
    CPU_ACTIVE_GOVERNOR = str(cfg["cpu_active"]); CPU_IDLE_GOVERNOR = str(cfg["cpu_idle"])
    POWER_IDLE_AFTER_SECONDS = int(cfg["idle_after"]); CONTAINER_STOP_AFTER_SECONDS = int(cfg["stop_after"])
    current_profile = name
    result = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power(), "profile": name}
    log_control(f"PROFILE applied name={name} cpu={result.get('cpu')} gpu={result.get('gpu')}")
    return result



def nvidia_settings_available():
    return shutil.which("nvidia-settings") is not None


def parse_gpu_temps():
    temps = []
    if not shutil.which("nvidia-smi"):
        return temps
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index,temperature.gpu", "--format=csv,noheader,nounits"], timeout=6)
    if rc != 0:
        return temps
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                temps.append((int(parts[0]), int(float(parts[1]))))
            except Exception:
                pass
    return temps


def gpu_indices():
    vals = [idx for idx, _ in parse_gpu_temps()]
    if vals:
        return vals
    if not shutil.which("nvidia-smi"):
        return [0, 1]
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"], timeout=6)
    if rc == 0:
        found = []
        for line in out.splitlines():
            try:
                found.append(int(line.strip()))
            except Exception:
                pass
        if found:
            return found
    return [0, 1]


def parse_gpu_fan_speeds():
    speeds = {}
    if not shutil.which("nvidia-smi"):
        return speeds
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index,fan.speed", "--format=csv,noheader,nounits"], timeout=6)
    if rc != 0:
        return speeds
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            idx = int(parts[0])
        except Exception:
            continue
        raw_speed = parts[1].split()[0]
        if not raw_speed or raw_speed.upper() == "N/A":
            continue
        try:
            speeds[idx] = int(float(raw_speed))
        except Exception:
            continue
    return speeds


def fan_speed_for_temp(temp_c):
    for threshold, speed in FAN_CURVE:
        if temp_c < threshold:
            return max(FAN_MIN_SAFE_SPEED, int(speed))
    return max(FAN_MIN_SAFE_SPEED, 100)


def fan_targets_from_temps():
    temps = parse_gpu_temps()
    if not temps:
        return {idx: 70 for idx in gpu_indices()}
    return {idx: fan_speed_for_temp(temp) for idx, temp in temps}


def fan_targets_from_temps_for_indices(indices=None):
    available_indices = gpu_indices()
    if indices is None:
        target_indices = list(available_indices)
    else:
        target_indices = []
        for idx in indices:
            try:
                target_indices.append(int(idx))
            except Exception:
                pass
        target_indices = [idx for idx in target_indices if idx in available_indices]
    if not target_indices:
        return {}
    wanted = set(target_indices)
    temps = [(idx, temp) for idx, temp in parse_gpu_temps() if idx in wanted]
    if not temps:
        return {idx: 70 for idx in target_indices}
    return {idx: fan_speed_for_temp(temp) for idx, temp in temps}


def wait_for_nvidia_display(display=":99", timeout=10):
    deadline = time.time() + timeout
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.pop("XAUTHORITY", None)
    last = "display not ready"
    while time.time() < deadline:
        try:
            p = subprocess.run(["nvidia-settings", "-q", "gpus"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3, env=env)
            last = (p.stdout or "").strip()
            if p.returncode == 0:
                return True, last
        except Exception as e:
            last = str(e)
        time.sleep(0.5)
    return False, last


def ensure_headless_x_running():
    # Canonical manual fan-control path: keep a single private headless Xorg
    # service for NVIDIA control on DISPLAY=:99 and drive all fan actions through it.
    if not nvidia_settings_available():
        return False, "nvidia-settings not found"
    display = os.environ.get("CLUB3090_FAN_DISPLAY", ":99")
    ok, msg = wait_for_nvidia_display(display, timeout=1)
    if ok:
        return True, "headless X already ready"
    if shutil.which("systemctl"):
        run_cmd(["systemctl", "stop", "club3090-headless-x.service"], timeout=10)
        rc, out = run_cmd(["systemctl", "start", "club3090-headless-x.service"], timeout=20)
        ok, msg = wait_for_nvidia_display(display, timeout=12)
        if ok:
            return True, "started club3090-headless-x.service"
        return False, f"headless X not ready after start rc={rc}: {out[-800:]} / {msg}"
    return False, "systemctl unavailable; cannot start headless X"


def run_nvidia_settings(args):
    if not nvidia_settings_available():
        return 127, "nvidia-settings not found"
    display = os.environ.get("CLUB3090_FAN_DISPLAY", ":99")
    ok, msg = ensure_headless_x_running()
    if not ok:
        return 126, msg
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.pop("XAUTHORITY", None)
    try:
        p = subprocess.run(["nvidia-settings"] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15, env=env)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 999, str(e)


def discover_nvidia_fan_indices():
    if not nvidia_settings_available():
        return []
    rc, out = run_nvidia_settings(["-q", "fans"])
    if rc != 0:
        return []
    found = []
    for match in re.finditer(r"\[fan:(\d+)\]", out or "", re.IGNORECASE):
        idx = int(match.group(1))
        if idx not in found:
            found.append(idx)
    return found


def fan_indices_for_gpu_targets(target_gpu_indices, available_gpu_indices=None, fan_indices=None):
    fan_list = sorted({int(idx) for idx in (fan_indices or [])})
    if not fan_list:
        return []
    gpu_list = [int(idx) for idx in (available_gpu_indices or gpu_indices())]
    if not gpu_list:
        return fan_list
    target_list = [int(idx) for idx in (target_gpu_indices or []) if int(idx) in gpu_list]
    if not target_list or len(target_list) >= len(gpu_list):
        return fan_list
    chunk = max(1, (len(fan_list) + len(gpu_list) - 1) // len(gpu_list))
    mapping = {}
    cursor = 0
    for pos, gpu_idx in enumerate(gpu_list):
        remaining_gpus = len(gpu_list) - pos
        remaining_fans = len(fan_list) - cursor
        if remaining_fans <= 0:
            mapping[gpu_idx] = []
            continue
        take = remaining_fans if remaining_gpus == 1 else min(chunk, remaining_fans)
        mapping[gpu_idx] = fan_list[cursor:cursor + take]
        cursor += take
    selected = []
    for gpu_idx in target_list:
        selected.extend(mapping.get(gpu_idx, []))
    return selected


def run_nvidia_assignments(assignments):
    results = []
    success = 0
    for assignment in assignments:
        rc, out = run_nvidia_settings(["-a", assignment])
        text = (out or "").strip()
        if rc == 0:
            success += 1
        results.append(f"{assignment}: rc={rc} {text[-500:]}")
    return success, results


def run_nvidia_assignment_batch(assignments):
    if not assignments:
        return 0, []
    args = []
    for assignment in assignments:
        args += ["-a", assignment]
    rc, out = run_nvidia_settings(args)
    text = (out or "").strip()
    return rc, [f"batch rc={rc} assignments={assignments}: {text[-1500:]}"]


def restore_gpu_fans_auto(indices=None):
    available_indices = gpu_indices()
    if indices is None:
        indices = list(available_indices)
    else:
        indices = [int(idx) for idx in indices if int(idx) in available_indices]
    if not indices:
        return ["no GPU targets selected for auto restore"]
    assignments = [f"[gpu:{gpu_idx}]/GPUFanControlState=0" for gpu_idx in indices]
    batch_rc, batch_results = run_nvidia_assignment_batch(assignments)
    if batch_rc == 0:
        return batch_results
    success, retry_results = run_nvidia_assignments(assignments)
    return batch_results + retry_results + [f"auto restore success={success}/{len(assignments)}"]


def verify_manual_fan_target(target_gpu_indices, target_speed, timeout=3.0):
    if target_speed is None:
        return False, {}
    wanted = {int(idx) for idx in (target_gpu_indices or [])}
    if not wanted:
        return False, {}
    deadline = time.time() + float(timeout)
    last = {}
    threshold = max(0, int(target_speed) - 15)
    while time.time() < deadline:
        speeds = parse_gpu_fan_speeds()
        last = {idx: speeds.get(idx) for idx in wanted if idx in speeds}
        if last and all(speed is not None and int(speed) >= threshold for speed in last.values()):
            return True, last
        time.sleep(0.4)
    return False, last


def set_gpu_fans(speed=None, auto=False, indices=None):
    # Canonical scoped fan-control path using the private headless-X / nvidia-settings flow.
    results = []
    available_indices = gpu_indices()
    if indices is None:
        indices = list(available_indices)
    else:
        clean = []
        for idx in indices:
            try:
                clean.append(int(idx))
            except Exception:
                pass
        indices = [idx for idx in clean if idx in available_indices]
    if not indices:
        return ["no GPU targets selected"]
    fan_objects = discover_nvidia_fan_indices()
    if auto:
        assignments = [f"[gpu:{gpu_idx}]/GPUFanControlState=0" for gpu_idx in indices]
        batch_rc, batch_results = run_nvidia_assignment_batch(assignments)
        results.extend(batch_results)
        success, retry_results = run_nvidia_assignments(assignments) if batch_rc != 0 else (len(assignments), [])
        results.extend(retry_results)
        ok = (batch_rc == 0) or (success == len(assignments))
        with metrics_lock:
            power_state["fans"] = "auto" if ok else "auto_failed"
            power_state["last_action"] = "fans_auto"
            power_state["last_error"] = "" if ok else " | ".join([r for r in results if "rc=0" not in r])[-1000:]
        log_control("FANS auto: " + " || ".join(results))
        return results

    if speed is None:
        targets = fan_targets_from_temps_for_indices(indices)
        # Be deliberately aggressive: use the hottest-card target for all detected
        # fan controllers. This avoids ambiguous fan<->GPU mapping issues on dual
        # 3090 cards and matches the cooling priority.
        target = max(targets.values()) if targets else 70
        mode_label = "manual_curve"
    else:
        targets = {idx: int(speed) for idx in indices}
        target = int(speed)
        mode_label = "manual_max" if target >= FAN_MAX_SPEED else "manual_fixed"

    target = max(FAN_MIN_SAFE_SPEED, min(100, int(target)))
    mapped_fans = fan_indices_for_gpu_targets(indices, available_gpu_indices=available_indices, fan_indices=fan_objects)
    if not mapped_fans:
        guessed_fans = fan_objects or list(range(0, max(2, min(8, len(available_indices) * 2))))
        mapped_fans = fan_indices_for_gpu_targets(indices, available_gpu_indices=available_indices, fan_indices=guessed_fans)
        if not mapped_fans and len(indices) >= len(available_indices):
            mapped_fans = guessed_fans
    enable_assignments = [f"[gpu:{gpu_idx}]/GPUFanControlState=1" for gpu_idx in indices]
    direct_assignments = [f"[gpu:{gpu_idx}]/GPUTargetFanSpeed={target}" for gpu_idx in indices]
    fan_assignments = [f"[fan:{fan_idx}]/GPUTargetFanSpeed={target}" for fan_idx in mapped_fans]
    batch_assignments = list(enable_assignments)
    if direct_assignments:
        batch_assignments.extend(direct_assignments)
    if fan_assignments:
        batch_assignments.extend(fan_assignments)
    batch_rc, batch_results = run_nvidia_assignment_batch(batch_assignments)
    results.extend(batch_results)

    enable_success, enable_results = run_nvidia_assignments(enable_assignments) if batch_rc != 0 else (len(enable_assignments), [])
    results.extend(enable_results)

    direct_success, direct_results = run_nvidia_assignments(direct_assignments) if batch_rc != 0 else (len(direct_assignments), [])
    results.extend(direct_results)

    fan_success = 0
    if fan_assignments and batch_rc != 0:
        fan_success, fan_results = run_nvidia_assignments(fan_assignments)
        results.extend(fan_results)
    elif fan_assignments:
        fan_success = len(fan_assignments)

    verified, observed = verify_manual_fan_target(indices, target)
    results.append(f"fan verify target={target} observed={observed}: rc={0 if verified else 1}")
    ok = (batch_rc == 0 or enable_success == len(enable_assignments)) and (direct_success > 0 or fan_success > 0 or verified)
    if not ok:
        legacy_fan_assignments = [f"[fan:{fan_idx}]/GPUTargetFanSpeed={target}" for fan_idx in range(0, 8)]
        legacy_batch_assignments = list(enable_assignments) + legacy_fan_assignments
        legacy_batch_rc, legacy_batch_results = run_nvidia_assignment_batch(legacy_batch_assignments)
        results.extend(legacy_batch_results)
        legacy_fan_success = 0
        if legacy_batch_rc != 0:
            legacy_fan_success, legacy_fan_results = run_nvidia_assignments(legacy_fan_assignments)
            results.extend(legacy_fan_results)
        else:
            legacy_fan_success = len(legacy_fan_assignments)
        legacy_verified, legacy_observed = verify_manual_fan_target(indices, target, timeout=4.0)
        results.append(f"fan legacy verify target={target} observed={legacy_observed}: rc={0 if legacy_verified else 1}")
        ok = (legacy_batch_rc == 0 or legacy_fan_success > 0 or legacy_verified)
    if not ok:
        failover_results = restore_gpu_fans_auto(indices)
        results.extend([f"manual failover -> {line}" for line in failover_results])
    with metrics_lock:
        power_state["fans"] = mode_label if ok else "manual_failed"
        power_state["last_action"] = "fans_set"
        power_state["last_error"] = "" if ok else " | ".join([r for r in results if "rc=0" not in r])[-1200:]
    log_control("FANS set: " + " || ".join(results))
    return results

def apply_fan_curve_once():
    if fan_manual_override or not power_optimizations_enabled:
        return []
    if time.time() < fan_curve_pause_until:
        return [f"fan curve paused for {int(fan_curve_pause_until-time.time())}s"]
    target_indices = fan_target_gpu_indices(cooling_scope_instance_id)
    if not target_indices:
        return ["no GPU targets selected for fan curve"]
    return set_gpu_fans(speed=None, auto=False, indices=target_indices)

def run_cmd(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 999, str(e)


def set_cpu_governor(governor):
    if not governor:
        return []
    results = []
    if shutil.which("cpupower"):
        rc, out = run_cmd(["cpupower", "frequency-set", "-g", governor], timeout=20)
        results.append(f"cpupower governor {governor}: rc={rc} {out[-500:]}")
        if rc == 0:
            return results
    base = "/sys/devices/system/cpu"
    try:
        for name in os.listdir(base):
            if not name.startswith("cpu") or not name[3:].isdigit():
                continue
            path = os.path.join(base, name, "cpufreq", "scaling_governor")
            if os.path.exists(path):
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(governor)
                except Exception as e:
                    results.append(f"{path}: {e}")
    except Exception as e:
        results.append(str(e))
    return results


def apply_gpu_idle_power(skip_fans=False):
    if not power_optimizations_enabled:
        return ["power optimizations disabled"]
    results = []
    if not shutil.which("nvidia-smi"):
        return ["nvidia-smi not found"]
    for cmd in (["nvidia-smi", "-pm", "1"], ["nvidia-smi", "-pl", str(GPU_IDLE_POWER_LIMIT_W)], ["nvidia-smi", "-lgc", GPU_IDLE_LOCK_CLOCKS]):
        rc, out = run_cmd(cmd, timeout=20)
        results.append(f"{' '.join(cmd)}: rc={rc} {out[-500:]}")
    if not skip_fans:
        results += apply_fan_curve_once()
    with metrics_lock:
        power_state["gpu"] = "idle"
        power_state["last_action"] = "gpu_idle"
        power_state["last_error"] = " | ".join([r for r in results if "rc=0" not in r and "disabled" not in r])[-1000:]
    log_control("POWER gpu idle: " + " || ".join(results))
    return results


def apply_gpu_active_power(skip_fans=False):
    if not power_optimizations_enabled:
        return ["power optimizations disabled"]
    results = []
    if not shutil.which("nvidia-smi"):
        return ["nvidia-smi not found"]
    cmds = [["nvidia-smi", "-pm", "1"], ["nvidia-smi", "-rgc"], ["nvidia-smi", "-pl", str(GPU_ACTIVE_POWER_LIMIT_W)]]
    if GPU_ACTIVE_LOCK_CLOCKS:
        cmds.append(["nvidia-smi", "-lgc", GPU_ACTIVE_LOCK_CLOCKS])
    for cmd in cmds:
        rc, out = run_cmd(cmd, timeout=20)
        results.append(f"{' '.join(cmd)}: rc={rc} {out[-500:]}")
    if not skip_fans:
        results += apply_fan_curve_once()
    with metrics_lock:
        power_state["gpu"] = "active"
        power_state["last_action"] = "gpu_active"
        power_state["last_error"] = " | ".join([r for r in results if "rc=0" not in r and "disabled" not in r])[-1000:]
    log_control("POWER gpu active: " + " || ".join(results))
    return results


def apply_cpu_idle_power():
    results = set_cpu_governor(CPU_IDLE_GOVERNOR)
    with metrics_lock:
        power_state["cpu"] = "idle"
        power_state["last_action"] = "cpu_idle"
    log_control("POWER cpu idle: " + " || ".join(results))
    return results


def apply_cpu_active_power():
    results = set_cpu_governor(CPU_ACTIVE_GOVERNOR)
    with metrics_lock:
        power_state["cpu"] = "active"
        power_state["last_action"] = "cpu_active"
    log_control("POWER cpu active: " + " || ".join(results))
    return results


def stop_vllm_container(reason="idle", instance_id=None):
    with switch_lock:
        target = get_instance(instance_id) if instance_id else primary_instance()
        if target is None:
            log_control(f"POWER legacy stop requested reason={reason}")
            p = subprocess.run(["bash", "scripts/switch.sh", "--down"], cwd=CLUB3090_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
            return p.returncode, (p.stdout or "")[-4000:]
        log_control(f"POWER stop container requested reason={reason} instance={target['id']}")
        rc, out = stop_instance(target["id"])
        with metrics_lock:
            power_state["container"] = "stopped" if rc == 0 else "stop_failed"
            power_state["last_action"] = "container_stop"
            power_state["last_error"] = out if rc != 0 else ""
        log_control(f"POWER stop container rc={rc}: {out}")
        return rc, out


def ensure_vllm_running_for_request(instance_id=None):
    global last_inference_time
    with metrics_lock:
        last_inference_time = time.time()
    apply_cpu_active_power()
    apply_gpu_active_power(skip_fans=True)
    target = get_instance(instance_id) if instance_id else primary_instance()
    if target is None:
        mode = active_mode()
        port = MODES.get(mode, 8020)
        if port_open(port, timeout=0.25):
            with metrics_lock:
                power_state["container"] = "running"
            return
        log_control(f"POWER auto-starting legacy default mode={mode}")
        run_switch(mode)
        with metrics_lock:
            power_state["container"] = "running"
        return
    port = int(target["port"])
    if port_open(port, timeout=0.25):
        with metrics_lock:
            power_state["container"] = "running"
        return
    log_control(f"POWER auto-starting container for request instance={target['id']} mode={target['mode']}")
    start_instance(target["id"], wait=True)
    with metrics_lock:
        power_state["container"] = "running"


def idle_watchdog():
    idle_power_applied = False
    while True:
        try:
            now = time.time()
            with metrics_lock:
                idle_for = now - last_inference_time
                active = metrics.get("active_requests", 0)
            if active == 0 and idle_for >= POWER_IDLE_AFTER_SECONDS and not idle_power_applied:
                apply_cpu_idle_power()
                apply_gpu_idle_power()
                idle_power_applied = True
            if active > 0 or idle_for < POWER_IDLE_AFTER_SECONDS:
                idle_power_applied = False
            if power_optimizations_enabled and not fan_manual_override:
                # Refresh manual fan curve periodically even while idle; Linux/NVIDIA
                # auto fan behavior can leave 3090 fans off until temps are too high.
                apply_fan_curve_once()
        except Exception as e:
            log_control(f"POWER watchdog error: {e}")
        time.sleep(15)



def reset_gpu_power_defaults():
    results = []
    if not shutil.which("nvidia-smi"):
        return ["nvidia-smi not found"]
    for cmd in (["nvidia-smi", "-rgc"], ["nvidia-smi", "-pm", "0"]):
        rc, out = run_cmd(cmd, timeout=20)
        results.append(f"{' '.join(cmd)}: rc={rc} {out[-700:]}")
    # Reset fans to automatic too; disabling optimizations should put the system
    # back under default NVIDIA control as much as Linux allows.
    results += set_gpu_fans(auto=True)
    with metrics_lock:
        power_state["gpu"] = "default"
        power_state["fans"] = "auto"
        power_state["last_action"] = "power_defaults"
        power_state["last_error"] = " | ".join([r for r in results if "rc=0" not in r])[-1000:]
    log_control("POWER defaults: " + " || ".join(results))
    return results


def cancel_pending_fan_curve_resume():
    global fan_curve_resume_token
    fan_curve_resume_token += 1
    return fan_curve_resume_token


def schedule_fan_curve_resume(indices=None, delay=1.0):
    target_indices = [int(idx) for idx in (indices or [])]
    token = cancel_pending_fan_curve_resume()
    def worker():
        global fan_curve_pause_until
        time.sleep(max(0.0, float(delay or 0.0)))
        if token != fan_curve_resume_token:
            return
        if fan_manual_override or not power_optimizations_enabled:
            return
        fan_curve_pause_until = 0.0
        resume_targets = target_indices or fan_target_gpu_indices(cooling_scope_instance_id)
        if not resume_targets:
            log_control("FANS auto-resume skipped: no GPU targets selected")
            return
        results = set_gpu_fans(speed=None, auto=False, indices=resume_targets)
        log_control("FANS auto-resume: " + " || ".join(results))
    threading.Thread(target=worker, name="club3090-fan-resume", daemon=True).start()


def set_power_optimizations(enabled, instance_id=None):
    global power_optimizations_enabled, fan_curve_pause_until, cooling_scope_instance_id
    if instance_id is not None:
        cooling_scope_instance_id = str(instance_id or "GLOBAL").strip().upper() or "GLOBAL"
    cancel_pending_fan_curve_resume()
    power_optimizations_enabled = bool(enabled)
    with metrics_lock:
        power_state["power_optimizations"] = "enabled" if power_optimizations_enabled else "disabled"
    if power_optimizations_enabled:
        fan_curve_pause_until = 0.0
        return {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power(skip_fans=True), "fans": apply_fan_curve_once()}
    fan_curve_pause_until = time.time() + 10**9
    return {"cpu": set_cpu_governor("performance"), "gpu": reset_gpu_power_defaults()}


def fan_target_gpu_indices(instance_id=None):
    raw = str(instance_id or "").strip().upper()
    if raw in ("", "GLOBAL"):
        return gpu_indices()
    instance = get_instance(raw)
    if instance:
        return [int(idx) for idx in (instance.get("gpu_indices") or [instance.get("gpu_index", 0)])]
    parsed = parse_instance_identifier(raw)
    if parsed:
        return [int(idx) for idx in (parsed.get("gpu_indices") or [])]
    return gpu_indices()

def set_fan_max_toggle(enable, instance_id=None):
    global fan_manual_override, fan_curve_pause_until, cooling_scope_instance_id
    if instance_id is not None:
        cooling_scope_instance_id = str(instance_id or "GLOBAL").strip().upper() or "GLOBAL"
    target_indices = fan_target_gpu_indices(instance_id)
    cancel_pending_fan_curve_resume()
    fan_manual_override = bool(enable)
    if fan_manual_override:
        fan_curve_pause_until = 0.0
        return set_gpu_fans(speed=FAN_MAX_SPEED, auto=False, indices=target_indices)
    fan_curve_pause_until = time.time() + (1 if power_optimizations_enabled else 0)
    results = set_gpu_fans(auto=True, indices=target_indices)
    if power_optimizations_enabled:
        schedule_fan_curve_resume(indices=target_indices, delay=1.0)
    else:
        fan_curve_pause_until = 0.0
    return results

def power_status():
    with metrics_lock:
        idle_for = int(time.time() - last_inference_time)
        fan_curve_text = ", ".join([f"<{temp}C={speed}%" for temp, speed in FAN_CURVE]) + ", >=65C=100%"
        return {**power_state, "profile": current_profile, "idle_for_seconds": idle_for, "idle_power_after_seconds": POWER_IDLE_AFTER_SECONDS, "container_stop_after_seconds": 0, "container_auto_stop_enabled": CONTAINER_AUTO_STOP_ENABLED, "gpu_active_power_limit_w": GPU_ACTIVE_POWER_LIMIT_W, "gpu_idle_power_limit_w": GPU_IDLE_POWER_LIMIT_W, "gpu_idle_lock_clocks": GPU_IDLE_LOCK_CLOCKS, "cpu_active_governor": CPU_ACTIVE_GOVERNOR, "cpu_idle_governor": CPU_IDLE_GOVERNOR, "optimizations_enabled": power_optimizations_enabled, "fan_manual_override": fan_manual_override, "fan_curve": fan_curve_text, "fan_min_safe_speed": FAN_MIN_SAFE_SPEED}

def wait_for_port(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port, timeout=0.25):
            return True
        time.sleep(0.5)
    return False

def run_switch(mode, allow_fallback=True):
    if mode not in MODES:
        raise ValueError(f"Invalid mode: {mode}")
    switch_path = os.path.join(CLUB3090_DIR, "scripts", "switch.sh")
    if not os.path.exists(switch_path):
        raise RuntimeError(f"Missing switch script: {switch_path}")

    previous_mode = active_mode()
    fallback_mode = read_last_good_mode_file() or (previous_mode if previous_mode in MODES else None) or (DEFAULT_MODE if DEFAULT_MODE in MODES else "vllm/default")

    def attempt(target_mode, label):
        env = os.environ.copy()
        env["READY_URL"] = ready_url_for_mode(target_mode)
        env["PORT"] = str(int(MODES[target_mode]))
        apply_cpu_active_power()
        apply_gpu_active_power(skip_fans=True)
        log_control(f"SWITCH {label} cleanup before mode={target_mode}")
        cleanup_msg = cleanup_vllm_containers()
        log_control(f"SWITCH {label} start mode={target_mode} port={env['PORT']} ready_url={env['READY_URL']}")
        p = subprocess.run(["bash", "scripts/switch.sh", target_mode], cwd=CLUB3090_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
        output = p.stdout or ""
        port_ok = wait_for_port(MODES[target_mode], timeout=25)
        if p.returncode != 0 or not port_ok:
            log_control(f"SWITCH {label} failed mode={target_mode} rc={p.returncode} port_ok={port_ok}")
            cleanup_vllm_containers()
            raise RuntimeError((output[-12000:] or f"switch.sh exited with {p.returncode}") + f"\nport_open={port_ok}\ncleanup={cleanup_msg}")
        write_active_mode(target_mode)
        write_last_good_mode(target_mode)
        with metrics_lock:
            power_state["container"] = "running"
            power_state["last_action"] = f"switch_{target_mode}"
            power_state["last_error"] = ""
        log_control(f"SWITCH {label} complete mode={target_mode}")
        return output[-12000:]

    with switch_lock:
        try:
            return attempt(mode, "primary")
        except Exception as first_error:
            if not allow_fallback or fallback_mode == mode:
                raise
            log_control(f"SWITCH primary failed; falling back to {fallback_mode}: {first_error}")
            try:
                fallback_output = attempt(fallback_mode, "fallback")
                return "REQUESTED MODE FAILED; FALLBACK STARTED\n\n" + str(first_error)[-4000:] + "\n\n----- fallback output -----\n" + fallback_output
            except Exception as fallback_error:
                raise RuntimeError("Requested mode failed and fallback also failed.\n\nRequested error:\n" + str(first_error)[-6000:] + "\n\nFallback error:\n" + str(fallback_error)[-6000:])

def parse_preset_path(path):
    parsed = urlsplit(path)
    clean = parsed.path
    suffix = ("?" + parsed.query) if parsed.query else ""
    parts = [p for p in clean.split("/") if p]
    if not parts:
        return path, None, None

    # Supported preset URL forms:
    #   /v1/<preset>/chat/completions
    #   /v1/<preset>/v1/chat/completions   (clients that append /v1/...)
    #   /<preset>/chat/completions
    #   /<preset>/v1/chat/completions      (clients with base URL :8009/<preset>)
    # This preserves raw OpenAI paths like /v1/chat/completions.
    if len(parts) >= 3 and parts[0] == "v1" and parts[1] == "chat" and parts[2] == "completions":
        return path, None, None

    all_presets = get_all_presets()

    def split_candidate(raw):
        cap = None
        candidate = raw
        for prefix, value in LENGTH_PREFIXES.items():
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):]
                cap = value
                break
        if candidate in all_presets:
            return candidate, cap
        return None, None

    def upstream_from_rest(rest):
        # If a client appended /v1/... to a preset base URL, remove that nested v1.
        if rest and rest[0] == "v1":
            rest = rest[1:]
        if not rest:
            return "/v1"
        if rest == ["models"]:
            return "/v1/models"
        if rest[:2] == ["chat", "completions"]:
            return "/v1/chat/completions" + (("/" + "/".join(rest[2:])) if len(rest) > 2 else "")
        if rest[0] == "completions":
            return "/v1/completions" + (("/" + "/".join(rest[1:])) if len(rest) > 1 else "")
        return "/v1/" + "/".join(rest)

    # Normal current style: /v1/<preset>/...
    if parts[0] == "v1" and len(parts) >= 2:
        candidate, cap = split_candidate(parts[1])
        if candidate:
            return upstream_from_rest(parts[2:]) + suffix, candidate, cap
        return path, None, None

    # Compatibility style: /<preset>/... so clients can safely append /v1/...
    candidate, cap = split_candidate(parts[0])
    if candidate:
        return upstream_from_rest(parts[1:]) + suffix, candidate, cap

    return path, None, None

def apply_preset(body, preset_name, max_token_cap):
    try:
        data = json.loads(body or b"{}")
    except Exception:
        return body
    preset = get_all_presets().get(preset_name)
    if not preset:
        return body
    for key, value in preset.items():
        if key == "chat_template_kwargs":
            current = data.get("chat_template_kwargs")
            if not isinstance(current, dict):
                current = {}
            data["chat_template_kwargs"] = {**current, **value}
        else:
            data[key] = value
    if max_token_cap is not None:
        capped_any = False
        for token_key in ("max_tokens", "max_completion_tokens"):
            if token_key in data:
                try:
                    data[token_key] = min(int(data[token_key]), max_token_cap)
                except Exception:
                    data[token_key] = max_token_cap
                capped_any = True
        if not capped_any:
            data["max_tokens"] = max_token_cap
    return json.dumps(data, separators=(",", ":")).encode("utf-8")

def parse_instance_path(path):
    parsed = urlsplit(path)
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parse_instance_identifier(parts[0]):
        instance_id = parse_instance_identifier(parts[0])["id"]
        trimmed = "/" + "/".join(parts[1:]) if len(parts) > 1 else "/"
        if parsed.query:
            trimmed += "?" + parsed.query
        return instance_id, trimmed
    return None, path

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>club-3090 Control</title><style>:root{color-scheme:dark;--bg:#0b0f14;--panel:#121923;--line:#273243;--text:#e8eef7;--muted:#9dafc3;--blue:#72c7ff;--green:#2fc46b;--red:#ff5b6c;--amber:#ffcb6b;--orange:#ff8a2a;--field:#081018;--cyan:#7dd3fc;--turquoise:#26d6c6}*{box-sizing:border-box}body,html{min-height:100%;margin:0}body{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text);overflow-y:auto;overflow-x:hidden}header{position:sticky;top:0;z-index:10;padding:10px 12px;background:#111925f7;backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}.top{display:flex;justify-content:space-between;align-items:center;gap:8px}.brand{font-size:18px;font-weight:800}.pill{color:var(--muted);font-size:12px;border:1px solid var(--line);border-radius:999px;padding:4px 8px;background:#0a1119;margin-top:4px}.subtabs,.tabs{display:flex;gap:6px;overflow-x:auto}.tabs{padding-top:10px}.subtabs{margin-bottom:10px}.btn,.subtab,.tab{border:1px solid #34445a;background:#1b2635;color:#eef4ff;border-radius:10px;padding:9px 11px;font-size:13px;cursor:pointer;white-space:nowrap}.subtab.active,.tab.active{background:#203149;border-color:#3d6fa3}.btn:disabled{opacity:.5;cursor:not-allowed}.green{background:#113d25;border-color:#2c8a54}.turquoise{background:#079c9c;border-color:#4df5e8;color:#041316}.red{background:#4a1118;border-color:#8a2b35}.amber{background:#4a3511;border-color:#8a652b}.orange{background:#c45512;border-color:#ffae42;color:#fff}.blue{background:#12314d;border-color:#2a72a8}.purple{background:#4b1f75;border-color:#9460df;color:#fff}.default-profile{background:#1d5f96;border-color:#78c7ff;color:#fff}.container{display:flex;flex-direction:column;gap:10px;padding:10px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;box-shadow:0 8px 30px #0004;margin-bottom:10px}.panel h2{font-size:14px;margin:0 0 10px}.chartgrid+.panel{margin-top:10px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.stat{background:#0b1119;border:1px solid #222d3c;border-radius:10px;padding:8px}.label{color:var(--muted);font-size:11px}label.label{display:inline-flex;align-items:center;gap:8px}label.label input[type=checkbox]{margin:0;flex:0 0 auto}.value{font-weight:700;font-size:13px;overflow-wrap:anywhere}.value-subline{display:block;margin-top:4px;color:var(--muted);font-size:12px;font-weight:600;line-height:1.35}.actions{display:flex;gap:7px;flex-wrap:wrap}.hidden{display:none!important}.tabpane{display:none}.tabpane.active{display:block}.metricpane{display:none}.metricpane.active{display:block}.logs{min-height:0;display:flex;flex-direction:column;margin-bottom:0}.loghead{display:flex;justify-content:space-between;align-items:center;padding-bottom:7px;gap:10px}.logheadchecks{display:flex;align-items:center;gap:12px;white-space:nowrap}.log{width:100%;height:clamp(360px,calc(100dvh - 430px),560px);min-height:320px;resize:vertical;white-space:pre-wrap;overflow-wrap:anywhere;background:#030608;color:#a5ffa5;border:1px solid #26313f;border-radius:12px;padding:12px;font-family:Consolas,monospace;font-size:12px;line-height:1.35}.log-card-hidden{display:none!important}.logs-tab .container{min-height:calc(100dvh - 108px)}.logs-tab .logs.panel{height:calc(100dvh - 252px);min-height:500px;margin-bottom:0}.logs-tab .log{height:auto;min-height:0;flex:1;resize:none}.logs-tab .content-tab{display:none!important}.logtools{display:none}.audit-tab .logtools,.logs-tab .logtools{display:block;margin-bottom:10px}.logtools h2{display:block;margin:0 0 10px}.logtools .searchbox{display:flex}.searchbox{display:flex;align-items:center;gap:6px;flex-wrap:nowrap;width:100%}.searchbox input{flex:1 1 auto;min-width:80px;background:var(--field);color:var(--text);border:1px solid #2c3a4f;border-radius:9px;padding:9px}.chartgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.gpu-chartgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.chart{height:145px;background:#081018;border:1px solid #213044;border-radius:12px;padding:8px}.chart.tall{height:220px}canvas{width:100%;height:100%}.msg{color:var(--amber);font-size:12px;min-height:18px;padding-top:6px}.smallgap{margin-bottom:5px}#auditSummary{margin-top:10px}.gpu-cards{display:grid;grid-template-columns:1fr;gap:10px}.gpu-card{background:#101722;border:1px solid #26313f;border-radius:14px;padding:12px}.gpu-title{font-weight:800;color:#d9ecff;margin-bottom:10px;border-bottom:1px solid #26313f;padding-bottom:7px}.gpu-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.gpu-section-title{color:#9dafc3;font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}.gpu-line{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:2px 0}.meter{height:7px;background:#081018;border-radius:99px;overflow:hidden;margin-top:5px}.meter span{display:block;height:100%;background:#2fc46b}.coregrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:6px}.storage-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}.storage-section{display:flex;flex-direction:column;gap:10px}.storage-card.user-facing{background:#10243a;border-color:#2a72a8}.storage-card{background:#0b1119;border:1px solid #243144;border-radius:12px;padding:10px;min-width:0}.storage-title{font-weight:800;color:#d9ecff;margin-bottom:6px;overflow-wrap:anywhere}.storage-meta{color:#9dafc3;font-size:12px;margin-bottom:6px;overflow-wrap:anywhere}.storage-sizes{display:grid;grid-template-columns:minmax(85px,0.8fr) minmax(85px,0.8fr) minmax(95px,0.9fr);gap:6px;margin-bottom:8px}.storage-sizes .stat{padding:6px}.diskbar{height:8px;background:#081018;border-radius:99px;overflow:hidden;width:100%;margin-bottom:3px;margin-top:3px}.diskbar span{display:block;height:100%;background:#72c7ff}.netgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px}.temp-blue{color:#60a5fa}.temp-green{color:#2fc46b}.temp-yellow{color:#ffde59}.temp-orange{color:#ff8a2a}.temp-red{color:#ff5b6c}.temp-crimson{color:#dc143c;font-weight:900}.machine-row{margin-top:7px}.api-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}.api-card{background:#0b1119;border:1px solid #243144;border-radius:12px;padding:10px}.api-card h3{font-size:13px;margin:0 0 6px;color:#d9ecff}.api-card p{margin:0;color:var(--muted);font-size:12px;line-height:1.35}.api-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.preset-actions{display:flex;gap:4px}.iconbtn{border:1px solid #34445a;background:#182231;color:#eef4ff;border-radius:8px;padding:5px 7px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px}.iconbtn svg{width:16px;height:16px;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.preset-editor{display:none}.preset-editor.open{display:block}.formgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}.formgrid label{display:flex;flex-direction:column;gap:4px;color:var(--muted);font-size:12px}.formgrid input,.formgrid select{background:var(--field);color:var(--text);border:1px solid #2c3a4f;border-radius:9px;padding:8px}.preset-help{color:var(--muted);font-size:12px;line-height:1.35;margin-bottom:10px}.profile-balanced{background:#0faeb0;border-color:#5ff5e8;color:#031516}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}.panel-head h2{margin:0}.add-preset-btn{width:30px;height:30px;border-radius:999px;border:1px solid #55ee91;background:#128a45;color:#fff;display:inline-flex;align-items:center;justify-content:center;padding:0;box-shadow:none}.add-preset-btn:hover{background:#18a957}.add-preset-btn svg{width:15px;height:15px;stroke:#fff;stroke-width:3;stroke-linecap:round}.preset-form-actions{display:flex;justify-content:center;gap:18px;margin-top:14px}.preset-intro{color:var(--muted);font-size:13px;line-height:1.45;margin:4px 0 2px}.preset-intro.hidden{display:none}.scope-strip{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 10px}.scope-strip .subtabs{margin:0}.club-modal{position:fixed;inset:0;background:rgba(2,7,14,.82);display:flex;align-items:center;justify-content:center;padding:16px;z-index:1000}.club-modal-card{width:min(720px,100%);background:#101824;border:1px solid #31455f;border-radius:14px;box-shadow:0 20px 70px rgba(0,0,0,.45);padding:14px}.modal-keybox{width:100%;min-height:120px;resize:vertical;border:1px solid #31455f;border-radius:10px;background:#07101a;color:#d9ecff;padding:10px;font:600 13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}.busy-note{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px;line-height:1.35}.spinner{width:12px;height:12px;border:2px solid #34445a;border-top-color:var(--blue);border-radius:999px;animation:.8s linear infinite club3090-spin;flex:0 0 auto}.instance-panel-busy{border-color:#35506d}.instance-panel-busy .actions,.instance-panel-busy .subtabs,.instance-panel-busy .value{opacity:.82}@keyframes club3090-spin{to{transform:rotate(360deg)}}@media (max-width:900px){.chartgrid{grid-template-columns:1fr}.gpu-chartgrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.grid{grid-template-columns:1fr 1fr}.gpu-grid{grid-template-columns:1fr}.log{height:clamp(320px,calc(100dvh - 410px),520px)}.logs-tab .logs.panel{height:calc(100dvh - 250px);min-height:500px}.logs-tab .log{height:auto;min-height:0}}</style></head><body><header><div class="top"><div><div class="brand">club-3090 Control &bull; __SCRIPT_VERSION__</div><div class="pill" id="summary">loading...</div></div></div><div class="tabs"><button class="tab active" onclick="tab(event, 'overview')">Main</button><button class="tab" onclick="tab(event, 'system')">System</button><button class="tab" onclick="tab(event, 'presets')">Presets</button><button class="tab" id="usersTabBtn" onclick="tab(event, 'users')">Users</button><button class="tab" onclick="tab(event, 'metrics')">Metrics</button><button class="tab" onclick="tab(event, 'logs')">Logs</button></div></header><main class="container"><section id="overview" class="tabpane content-tab active"><div class="panel"><h2>Status</h2><div class="grid"><div class="stat"><div class="label">Mode</div><div class="value" id="mode">-</div></div><div class="stat"><div class="label">Container</div><div class="value" id="container">-</div></div><div class="stat"><div class="label">Requests</div><div class="value" id="req">-</div></div><div class="stat"><div class="label">Uptime</div><div class="value" id="uptime">-</div></div><div class="stat"><div class="label">Power</div><div class="value" id="powerbox">-</div></div><div class="stat"><div class="label">Last</div><div class="value" id="last">-</div></div></div><div class="msg" id="msg"></div></div><div id="gpuCards" class="gpu-cards"></div></section><section id="system" class="tabpane content-tab"><div class="panel"><h2>Services</h2><div class="value" id="services">-</div></div><div class="panel"><h2>Audit Overview</h2><div class="grid"><div class="stat"><div class="label">Admin UI</div><div class="value" id="auditAdminEndpoint">-</div></div><div class="stat"><div class="label">Proxy</div><div class="value" id="auditProxyEndpoint">-</div></div><div class="stat"><div class="label">Exposure</div><div class="value" id="auditExposure">-</div></div><div class="stat"><div class="label">Local Automation</div><div class="value" id="auditLocalApi">-</div></div></div><div class="value smallgap" id="auditSummary">-</div><div class="msg" id="auditMsg"></div></div><div class="panel"><h2>Access Policy</h2><div class="actions" id="accessPolicyRow"><label class="label"><input type="checkbox" id="auditAllowAnonymousProxy" onchange="mirrorAuthToggles(this.checked)"> allow requests without per-user API keys</label><button class="btn blue" onclick="saveAuthSettings()">Save Policy</button></div><div class="value smallgap" style="margin-top: 10px" id="auditPolicyText">-</div></div><div class="panel"><h2>Instances</h2><div class="subtabs" id="instanceTabs"></div><div class="value smallgap" id="instanceSummary">-</div><div class="actions"><button class="btn blue" onclick="instanceAction('start_instance')">Start</button><button class="btn amber" onclick="instanceAction('restart_instance')">Restart</button><button class="btn red" onclick="instanceAction('stop_container')">Stop</button><button class="btn green" id="instanceEnableBtn" onclick="toggleInstanceEnabled()">Disable Boot Autostart</button></div><div class="msg" id="instanceMsg"></div></div><div class="panel"><h2>System</h2><div class="actions"><button class="btn amber" onclick="wol()">Wake-on-LAN</button></div><div class="actions machine-row"><button class="btn red" onclick="machineAction('reboot')">Restart Machine</button><button class="btn red" onclick="machineAction('shutdown')">Shutdown Machine</button></div></div><div class="panel"><h2>Profiles</h2><div class="actions"><button class="btn green" onclick="profile('eco')">Eco</button><button class="btn profile-balanced" onclick="profile('balanced')">Balanced</button><button class="btn default-profile" onclick="profile('default')">Default</button><button class="btn orange" onclick="profile('turbo')">Turbo</button></div></div><div class="panel"><h2>Power + Cooling</h2><div class="actions"><button class="btn green" id="optToggle" onclick="togglePowerOptimizations()">Disable Power Optimizations</button><button class="btn green" id="fanToggle" onclick="toggleFansMax()">Set Fans to Max</button></div></div></section><section id="presets" class="tabpane content-tab"><div class="panel"><h2>Per-Instance Docker Presets</h2><div class="preset-help">Assign a single-card preset to the currently selected GPU instance. Each instance gets its own GPU binding, docker override, port, and proxy prefix such as <code>:8009/GPU0/</code>.</div><div class="actions"><button class="btn blue" onclick="switchMode('vllm/default')">default</button><button class="btn blue" onclick="switchMode('vllm/long-vision')">long-vision</button><button class="btn blue" onclick="switchMode('vllm/long-text')">long-text</button><button class="btn blue" onclick="switchMode('vllm/bounded-thinking')">bounded-thinking</button><button class="btn blue" onclick="switchMode('vllm/tools-text')">tools-text</button><button class="btn blue" onclick="switchMode('vllm/minimal')">minimal</button><button class="btn blue" onclick="switchMode('llamacpp/default')">llamacpp-default</button><button class="btn blue" onclick="switchMode('llamacpp/concurrent')">llamacpp-concurrent</button></div></div><div class="panel"><h2>API Presets</h2><div class="preset-help">Default presets are locked. Custom presets are exposed as <code>:8009/v1/&lt;name&gt;</code> and <code>:8009/&lt;name&gt;</code>. Both forms work with <code>short-</code> and <code>concise-</code> prefixes.</div><div id="apiPresetGrid" class="api-grid"></div></div><div class="panel"><div class="panel-head"><h2>Custom Preset Templates</h2><button class="add-preset-btn" title="Create preset" aria-label="Create preset" onclick="openPresetEditor()"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div id="presetIntro" class="preset-intro">Create custom endpoint templates for different workloads or clients. Each preset saves generation parameters like temperature, sampling, thinking mode, penalties, and token limits, then exposes them as custom OpenAI-compatible endpoints such as <code>:8009/v1/my_preset</code> and <code>:8009/my_preset</code>. Short and concise prefixes work with custom presets too.</div><div id="presetEditor" class="preset-editor"><div class="formgrid"><label>Endpoint name<input id="presetName" placeholder="my_coding"></label><label>Description<input id="presetDescription" placeholder="What this preset is for"></label><label>Temperature<input id="presetTemperature" type="number" step="0.01" placeholder="0.7"></label><label>Top P<input id="presetTopP" type="number" step="0.01" placeholder="0.95"></label><label>Top K<input id="presetTopK" type="number" step="1" placeholder="20"></label><label>Min P<input id="presetMinP" type="number" step="0.01" placeholder="0"></label><label>Thinking<select id="presetThinking"><option value="false">Disabled</option><option value="true">Enabled</option></select></label><label>Preserve Thinking<select id="presetPreserveThinking"><option value="false">No</option><option value="true">Yes</option></select></label><label>Repetition penalty<input id="presetRepetitionPenalty" type="number" step="0.01" placeholder="1.0"></label><label>Presence penalty<input id="presetPresencePenalty" type="number" step="0.01" placeholder="0"></label><label>Frequency penalty<input id="presetFrequencyPenalty" type="number" step="0.01" placeholder="0"></label><label>Max context / prompt tokens<input id="presetMaxCtx" type="number" step="1" placeholder="truncate_prompt_tokens"></label><label>Max reply tokens<input id="presetMaxTokens" type="number" step="1" placeholder="max_tokens"></label><label>Seed<input id="presetSeed" type="number" step="1" placeholder="optional"></label><label>Min reply tokens<input id="presetMinTokens" type="number" step="1" placeholder="min_tokens"></label><label>Logprobs<input id="presetLogprobs" type="number" step="1" placeholder="optional"></label><label>Top logprobs<input id="presetTopLogprobs" type="number" step="1" placeholder="optional"></label><label>Length penalty<input id="presetLengthPenalty" type="number" step="0.01" placeholder="optional"></label><label>Ignore EOS<select id="presetIgnoreEos"><option value="">Default</option><option value="false">No</option><option value="true">Yes</option></select></label><label>Skip special tokens<select id="presetSkipSpecial"><option value="">Default</option><option value="true">Yes</option><option value="false">No</option></select></label><label>Include stop text<select id="presetIncludeStop"><option value="">Default</option><option value="false">No</option><option value="true">Yes</option></select></label><label>Stop strings<input id="presetStop" placeholder="one per line or comma-separated"></label></div><div class="preset-form-actions"><button id="presetSaveBtn" class="btn green" onclick="savePresetFromForm()">💾 Save</button><button class="btn red" onclick="closePresetEditor()">❌ Cancel</button></div></div></div></section><section id="users" class="tabpane content-tab"></section><section id="metrics" class="tabpane content-tab"><div class="panel"><h2>Metrics</h2><div class="subtabs"><button class="subtab active" onclick="metricTab(event, 'mMain')">Main</button><button class="subtab" onclick="metricTab(event, 'mGpu')">GPUs</button><button class="subtab" onclick="metricTab(event, 'mRam')">RAM</button><button class="subtab" onclick="metricTab(event, 'mCpu')">CPU</button><button class="subtab" onclick="metricTab(event, 'mSystem')">System</button><button class="subtab" onclick="metricTab(event, 'mNetwork')">Network</button></div><div id="mMain" class="metricpane active"><div class="chartgrid"><div class="chart"><canvas id="cGpu"></canvas></div><div class="chart"><canvas id="cMem"></canvas></div><div class="chart"><canvas id="cLatency"></canvas></div><div class="chart"><canvas id="cTps"></canvas></div></div></div><div id="mGpu" class="metricpane"><div id="gpuMetricCharts" class="gpu-chartgrid"></div></div><div id="mRam" class="metricpane"><div id="ramInfo" class="value smallgap"></div><div class="chartgrid"><div class="chart tall"><canvas id="cRam"></canvas></div></div></div><div id="mCpu" class="metricpane"><div class="chartgrid"><div class="chart"><canvas id="cCpu"></canvas></div></div><div id="cpuCores" class="coregrid"></div></div><div id="mSystem" class="metricpane"><div class="chartgrid"><div class="chart"><canvas id="cSystemUtil"></canvas></div></div><div class="panel"><h2>System Information</h2><div id="systemInfo" class="value"></div></div><div class="panel"><h2>Storage</h2><div id="diskInfo"></div></div></div><div id="mNetwork" class="metricpane"><div id="netInfo" class="netgrid"></div><div class="chartgrid"><div class="chart"><canvas id="cNetDown"></canvas></div><div class="chart"><canvas id="cNetUp"></canvas></div></div></div></div></section><section id="logs" class="tabpane"></section><section class="panel logtools"><h2>Log Management</h2><div class="searchbox"><button class="btn" id="searchPrev" onclick="previousMatch()" disabled="disabled">⏪</button><input id="searchQuery" placeholder="Search log text" onkeydown="if (event.key === 'Enter') runSearchOrNext();"><button class="btn" id="searchNext" onclick="runSearchOrNext()">🔍</button><span style="border-left: 1px solid #34445a; height: 28px"></span><button class="btn" id="refreshBtn" onclick="refreshStatus()">♻️</button><button class="btn" id="clearBtn" onclick="clearOrCancelLog()">🗑️</button></div></section><section class="logs panel"><div class="loghead"><h2 id="logTitle">Docker Logs</h2><div class="logheadchecks"><span class="label" id="logInstanceLabel">instance: primary</span><label class="label"><input type="checkbox" id="showGlobalLogs" checked="checked" onchange="setShowGlobalLogs(this.checked)"> show globally</label><label class="label"><input type="checkbox" id="autoscroll" checked="checked"> auto-scroll</label></div></div><textarea id="log" class="log" readonly="readonly" wrap="soft">
Connecting...</textarea></section></main><script>const searchState={active:!1,query:"",matches:[],index:-1,prevAutoscroll:!0};let lastStatus=null,activeTabName="overview",showGlobalLogs=!0;function $(e){return document.getElementById(e)}function setMsg(e){$("msg").textContent=e||""}function clearLog(){$("log").value=""}function appendLog(e){const t=$("log");t.value+=e+"\n",t.value.length>9e5&&(t.value=t.value.slice(-75e4)),searchState.active?recalculateMatches(!1):$("autoscroll").checked&&(t.scrollTop=t.scrollHeight)}function clearOrCancelLog(){searchState.active?cancelSearch():clearLog()}function recalculateMatches(e=!0){const t=$("searchQuery").value;if(!searchState.active||!t)return;const n=$("log").value.toLowerCase(),a=t.toLowerCase();let s=0,o=[];for(;a;){const e=n.indexOf(a,s);if(e<0)break;o.push(e),s=e+a.length}searchState.matches=o,o.length?searchState.index=e?Math.min(Math.max(searchState.index,0),o.length-1):0:searchState.index=-1,updateSearchUI(!1)}function runSearchOrNext(){if(searchState.active&&searchState.matches.length)return void nextMatch();$("searchQuery").value&&(searchState.prevAutoscroll=$("autoscroll").checked,searchState.active=!0,$("autoscroll").checked=!1,$("autoscroll").disabled=!0,recalculateMatches(!1),searchState.matches.length?gotoMatch(0):updateSearchUI(!1))}function gotoMatch(e){if(!searchState.matches.length)return;searchState.index=(e+searchState.matches.length)%searchState.matches.length;const t=searchState.matches[searchState.index],n=t+searchState.query.length,a=$("log");a.focus(),a.setSelectionRange(t,n);const s=a.value.slice(0,t).split("\n").length-1;a.scrollTop=Math.max(0,16*s-a.clientHeight/2),updateSearchUI(!1)}function nextMatch(){searchState.active&&searchState.matches.length&&gotoMatch(searchState.index+1)}function previousMatch(){searchState.active&&searchState.matches.length&&gotoMatch(searchState.index-1)}function cancelSearch(){searchState.active=!1,searchState.query="",searchState.matches=[],searchState.index=-1,$("searchQuery").value="",$("autoscroll").disabled=!1,$("autoscroll").checked=searchState.prevAutoscroll,$("log").setSelectionRange($("log").selectionStart,$("log").selectionStart),updateSearchUI(!0)}function updateSearchUI(e){searchState.active?(searchState.query=$("searchQuery").value,$("searchPrev").disabled=searchState.matches.length<2,$("searchNext").textContent=searchState.matches.length>1?"⏩":"🔍",$("refreshBtn").disabled=!0,$("refreshBtn").textContent=searchState.matches.length?`${searchState.index+1}/${searchState.matches.length}`:"0/0",$("clearBtn").textContent="❌"):($("searchPrev").disabled=!0,$("searchNext").textContent="🔍",$("refreshBtn").disabled=!1,$("refreshBtn").textContent="♻️",$("clearBtn").textContent="🗑️")}function fmtUptime(e){return e=Number(e||0),Math.floor(e/3600)+"h "+Math.floor(e%3600/60)+"m"}function mibToGiB(e){return(Number(e||0)/1024).toFixed(2)}function inferGpuStatus(e){const t=Number(e.util_pct||0);return lastStatus&&lastStatus.metrics&&lastStatus.metrics.active_requests>0?t>20?"Token Generation":"Prompt Processing":t>5?"Active":"Idle"}function tempClass(e){return(e=Number(e||0))<35?"temp-blue":e<50?"temp-green":e<60?"temp-yellow":e<70?"temp-orange":e<80?"temp-red":"temp-crimson"}function tempColor(e){return(e=Number(e||0))<35?"#60a5fa":e<50?"#2fc46b":e<60?"#ffde59":e<70?"#ff8a2a":e<80?"#ff5b6c":"#dc143c"}function tempLabel(e){return`${e||"N/A"} °C${Number(e||0)>=80?" ⚠️":""}`}function renderGpuCards(e){e&&e.length?$("gpuCards").innerHTML=e.map(e=>e.error?`<div class="gpu-card">${e.error}</div>`:`<div class="gpu-card"><div class="gpu-title">GPU ${e.index} - ${e.name||"RTX 3090"}${e.vendor?" ("+e.vendor+")":""}</div><div class="gpu-grid"><div><div class="gpu-section-title">Temperature</div><div class="gpu-line"><span>Core</span><b class="${tempClass(e.temp_c)}">${tempLabel(e.temp_c)}</b></div></div><div><div class="gpu-section-title">VRAM</div><div class="gpu-line"><span>Free</span><b>${mibToGiB(e.mem_free_mib)} GB</b></div><div class="gpu-line"><span>Used</span><b>${mibToGiB(e.mem_used_mib)} GB</b></div><div class="gpu-line"><span>Max</span><b>${mibToGiB(e.mem_total_mib)} GB</b></div><div class="meter"><span style="width:${Number(e.mem_pct||0)}%"></span></div></div><div><div class="gpu-section-title">Power</div><div class="gpu-line"><span>Draw</span><b>${e.power_w||"N/A"} W</b></div><div class="gpu-line"><span>Max Power</span><b>${e.power_limit_w||"N/A"} W</b></div></div><div><div class="gpu-section-title">Fans</div><div class="gpu-line"><span>Speed</span><b>${e.fan_pct||"N/A"}%</b></div></div><div><div class="gpu-section-title">Clocks</div><div class="gpu-line"><span>Core</span><b>${e.core_clock_mhz||"N/A"} MHz</b></div><div class="gpu-line"><span>Mem</span><b>${e.mem_clock_mhz||"N/A"} MHz</b></div></div><div><div class="gpu-section-title">Usage</div><div class="gpu-line"><span>Load</span><b>${e.util_pct||"N/A"}%</b></div><div class="gpu-line"><span>Status</span><b>${inferGpuStatus(e)}</b></div></div></div></div>`).join(""):$("gpuCards").innerHTML='<div class="panel">No GPU data</div>'}let editingPresetName=null;function presetParamSummary(e){e=e||{};const t=[];if(["temperature","top_p","top_k","min_p","presence_penalty","frequency_penalty","repetition_penalty","length_penalty","max_tokens","max_completion_tokens","min_tokens","truncate_prompt_tokens","seed","logprobs","top_logprobs"].forEach(n=>{void 0!==e[n]&&null!==e[n]&&""!==e[n]&&t.push(`${n}: ${e[n]}`)}),void 0!==e.ignore_eos&&t.push("ignore_eos: "+(e.ignore_eos?"on":"off")),void 0!==e.skip_special_tokens&&t.push("skip special: "+(e.skip_special_tokens?"on":"off")),void 0!==e.include_stop_str_in_output&&t.push("include stop: "+(e.include_stop_str_in_output?"on":"off")),void 0!==e.stop&&t.push(`stop: ${Array.isArray(e.stop)?e.stop.join("|"):e.stop}`),e.chat_template_kwargs){const n=e.chat_template_kwargs;void 0!==n.enable_thinking&&t.push("thinking: "+(n.enable_thinking?"on":"off")),n.preserve_thinking&&t.push("preserve thinking: on")}return t.join(", ")||"No explicit parameters"}function renderPresetCatalog(e){const t=$("apiPresetGrid");if(!t||!e)return;const n=[...e.defaults||[],...e.custom||[]];t.innerHTML=n.map(e=>{const t=e.locked;return`<div class="api-card"><div class="api-card-head"><h3>${e.endpoint}<br><span class="label">${e.endpoint_alt||"/"+e.name}</span></h3>${t?'<span class="label">default</span>':`<span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editPreset('${e.name}')">✏️</button><button class="iconbtn" title="Delete" onclick="deletePreset('${e.name}')">❌</button></span>`}</div><p>${e.description||""}</p><p class="label">${presetParamSummary(e.params)}</p></div>`}).join("")+'<div class="api-card"><h3>/v1/short-* / /short-* and /v1/concise-* / /concise-*</h3><p>Prefix any default or custom preset to cap replies: short = 4096 tokens, concise = 512 tokens. Presets work both under /v1/name and /name for clients that append /v1 automatically.</p></div>'}function openPresetEditor(e){editingPresetName=e&&e.name?e.name:null,$("presetEditor").classList.add("open"),$("presetIntro")&&$("presetIntro").classList.add("hidden"),$("presetSaveBtn").textContent=editingPresetName?"💾 Save changes":"💾 Save",$("presetName").disabled=!!editingPresetName,$("presetName").value=e?.name||"",$("presetDescription").value=e?.description||"";const t=e?.params||{},n=t.chat_template_kwargs||{};$("presetTemperature").value=t.temperature??"",$("presetTopP").value=t.top_p??"",$("presetTopK").value=t.top_k??"",$("presetMinP").value=t.min_p??"",$("presetThinking").value=String(!!n.enable_thinking),$("presetPreserveThinking").value=String(!!n.preserve_thinking),$("presetRepetitionPenalty").value=t.repetition_penalty??"",$("presetPresencePenalty").value=t.presence_penalty??"",$("presetFrequencyPenalty").value=t.frequency_penalty??"",$("presetMaxCtx").value=t.truncate_prompt_tokens??"",$("presetMaxTokens").value=t.max_tokens??"",$("presetSeed").value=t.seed??"",$("presetMinTokens").value=t.min_tokens??"",$("presetLogprobs").value=t.logprobs??"",$("presetTopLogprobs").value=t.top_logprobs??"",$("presetLengthPenalty").value=t.length_penalty??"",$("presetIgnoreEos").value=void 0===t.ignore_eos?"":String(!!t.ignore_eos),$("presetSkipSpecial").value=void 0===t.skip_special_tokens?"":String(!!t.skip_special_tokens),$("presetIncludeStop").value=void 0===t.include_stop_str_in_output?"":String(!!t.include_stop_str_in_output),$("presetStop").value=Array.isArray(t.stop)?t.stop.join("\n"):t.stop??"",$("presetEditor").scrollIntoView({behavior:"smooth",block:"center"})}function closePresetEditor(){editingPresetName=null,$("presetEditor").classList.remove("open"),$("presetIntro")&&$("presetIntro").classList.remove("hidden")}function collectPresetForm(){function e(e){return $(e).value.trim()}const t={description:e("presetDescription"),enable_thinking:"true"===$("presetThinking").value,preserve_thinking:"true"===$("presetPreserveThinking").value};[["temperature","presetTemperature"],["top_p","presetTopP"],["top_k","presetTopK"],["min_p","presetMinP"],["repetition_penalty","presetRepetitionPenalty"],["presence_penalty","presetPresencePenalty"],["frequency_penalty","presetFrequencyPenalty"],["truncate_prompt_tokens","presetMaxCtx"],["max_tokens","presetMaxTokens"],["seed","presetSeed"],["min_tokens","presetMinTokens"],["logprobs","presetLogprobs"],["top_logprobs","presetTopLogprobs"],["length_penalty","presetLengthPenalty"]].forEach(([n,a])=>{const s=function(t){const n=e(t);return""===n?void 0:Number(n)}(a);Number.isFinite(s)&&(t[n]=s)}),[["ignore_eos","presetIgnoreEos"],["skip_special_tokens","presetSkipSpecial"],["include_stop_str_in_output","presetIncludeStop"]].forEach(([n,a])=>{const s=e(a);""!==s&&(t[n]="true"===s)});const n=e("presetStop");return n&&(t.stop=n),t}async function savePresetFromForm(){const e=editingPresetName||$("presetName").value.trim();try{const t=await fetch("/admin/presets",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"save",name:e,preset:collectPresetForm()})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"save failed");renderPresetCatalog(n.presets),closePresetEditor(),setMsg("Saved preset "+e),await refreshStatus()}catch(e){alert("Preset save failed: "+e)}}function editPreset(e){const t=(lastStatus?.presets?.custom||[]).find(t=>t.name===e);t&&openPresetEditor(t)}async function deletePreset(e){if(confirm("Delete custom preset "+e+"?"))try{const t=await fetch("/admin/presets",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"delete",name:e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"delete failed");renderPresetCatalog(n.presets),setMsg("Deleted preset "+e),await refreshStatus()}catch(e){alert("Preset delete failed: "+e)}}function draw(e,t,n,a,s){const o=$(e);if(!o)return;const r=o.getContext("2d"),i=devicePixelRatio||1,l=o.width=o.clientWidth*i,c=o.height=o.clientHeight*i;if(r.clearRect(0,0,l,c),r.fillStyle=s||"#9dafc3",r.font=11*i+"px system-ui",r.fillText(a,8*i,14*i),!t.length)return;const u=t.map(e=>Number(e[n]||0)),d=1.1*Math.max(1,...u);r.strokeStyle=s,r.lineWidth=2*i,r.beginPath(),u.forEach((e,t)=>{const n=t/(u.length-1||1)*l,a=c-e/d*(c-24*i)-4*i;t?r.lineTo(n,a):r.moveTo(n,a)}),r.stroke(),r.fillStyle="#e8eef7",r.fillText(String(u[u.length-1]||0),l-62*i,14*i)}function drawGpuSeries(e,t,n,a,s,o){draw(e,t.map(e=>{const t=(e.gpus||[]).find(e=>String(e.index)===String(n));return{[a]:t?Number(t[a]||0):0}}),a,s,o)}function renderMetrics(e){const t=e.series||[];draw("cGpu",t,"gpu_util","GPU util %","#72c7ff"),draw("cMem",t,"mem_pct","VRAM %","#2fc46b"),draw("cLatency",t,"latency_s","Latency s","#ffcb6b"),draw("cTps",t,"tps","TPS est","#ff5b6c"),draw("cRam",t,"ram_pct","System RAM %","#2fc46b"),draw("cCpu",t,"cpu_pct","CPU total %","#72c7ff"),draw("cSystemUtil",t,"system_util_pct","System utilization %","#a78bfa"),draw("cNetDown",t,"net_rx_kbps","Download kbps","#2fc46b"),draw("cNetUp",t,"net_tx_kbps","Upload kbps","#72c7ff"),$("ramInfo")&&($("ramInfo").textContent=e.system&&e.system.memory?`Used ${mibToGiB(e.system.memory.used_mib)} / ${mibToGiB(e.system.memory.total_mib)} GB (${e.system.memory.used_pct}%)`:"");const n=e.system&&e.system.cpu&&e.system.cpu.cores||[];$("cpuCores")&&($("cpuCores").innerHTML=n.map(e=>`<div class="stat"><div class="label">Core ${e.core}</div><div class="value">${e.usage_pct}%</div><div class="meter"><span style="width:${e.usage_pct}%"></span></div></div>`).join(""));const a=e.system&&e.system.disks||[];function s(e){if(e.error)return`<div class="storage-card"><div class="storage-title">Error</div><div class="value">${e.error}</div></div>`;const t=`${e.path||e.source||e.name||"disk"}${e.label?" — "+e.label:""}`,n=`${e.model||""} ${e.transport?"· "+e.transport:""} · ${e.type||"-"} / ${e.partition_type||"-"} · ${e.fs||"-"} · ${e.mount||"not mounted"}${e.usage_basis?" · "+e.usage_basis:""}`,a=e=>null==e?"Unknown":`${e} GB`,s=a(e.free_gib),o=a(e.used_gib),r=a(e.total_gib),i=null===e.used_pct||void 0===e.used_pct?0:Number(e.used_pct||0),l=null===e.used_pct||void 0===e.used_pct?"usage unknown":`${i}% used`;return`<div class="${e.user_facing?"storage-card user-facing":"storage-card"}"><div class="storage-title">${t}</div><div class="storage-meta">${n}</div><div class="storage-sizes"><div class="stat"><div class="label">Free</div><div class="value">${s}</div></div><div class="stat"><div class="label">Used</div><div class="value">${o}</div></div><div class="stat"><div class="label">Total</div><div class="value">${r}</div></div></div><div class="diskbar"><span style="width:${i}%"></span></div><div class="label">${l}</div></div>`}if($("diskInfo")){const e=a.filter(e=>"disk"===e.kind||"disk"===e.type),t=a.filter(e=>!("disk"===e.kind||"disk"===e.type));$("diskInfo").innerHTML=`<div class="storage-section"><div class="panel"><h2>Disks</h2><div class="storage-list">${e.map(s).join("")||'<div class="value">No physical disks found</div>'}</div></div><div class="panel"><h2>Volumes</h2><div class="storage-list">${t.map(s).join("")||'<div class="value">No volumes found</div>'}</div></div></div>`}const o=e.system&&e.system.network||{};$("netInfo")&&($("netInfo").innerHTML=`<div class="stat"><div class="label">Local IP</div><div class="value">${o.local_ip||"unknown"}</div></div><div class="stat"><div class="label">Internet IP</div><div class="value">${o.public_ip||"unknown"}</div></div><div class="stat"><div class="label">Download</div><div class="value">${o.rx_kbps||0} kbps</div></div><div class="stat"><div class="label">Upload</div><div class="value">${o.tx_kbps||0} kbps</div></div>`);const r=e.system&&e.system.info||{};$("systemInfo")&&($("systemInfo").innerHTML=`OS: ${r.os||"unknown"}<br>Kernel: ${r.kernel||"unknown"}<br>Host: ${r.hostname||"unknown"}<br>User: ${r.username||"unknown"}<br>Machine: ${r.machine||"unknown"}<br>CPU: ${r.cpu_model||"unknown"}<br>Board/Product: ${r.board||"-"} / ${r.product||"-"}<br>BIOS: ${r.bios||"-"}<br>GPUs: ${r.gpus||"unknown"}`);const i=$("gpuMetricCharts");if(i&&e.gpus){const n=[{key:"util",suffix:"Util",label:"util %",color:"#72c7ff"},{key:"mem_pct",suffix:"Mem",label:"VRAM %",color:"#2fc46b"},{key:"temp",suffix:"Temp",label:"core temp °C",color:"#ffde59"},{key:"power",suffix:"Power",label:"power W",color:"#ff5b6c"}];i.innerHTML=n.map(t=>e.gpus.map(e=>`<div class="chart"><canvas id="cGpu${e.index}${t.suffix}"></canvas></div>`).join("")).join(""),n.forEach(n=>e.gpus.forEach(e=>{const a=n.color,s=`GPU${e.index} ${n.label}`;drawGpuSeries(`cGpu${e.index}${n.suffix}`,t,e.index,n.key,s,a)}))}}let selectedInstance="GPU0",logEs=null,selectedUserName="",selectedOverviewInstanceId="",selectedLogInstanceId="";function escapeHtml(e){return String(e??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;")}function svgIcon(e){return"edit"===e?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10-10-4-4L4 16v4zM14 6l4 4" fill="none"/></svg>':"key"===e?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 7a4 4 0 1 0 0 8a4 4 0 0 0 0-8Zm0 0h6m-2 0v3m-3 0h6" fill="none"/></svg>':"reset"===e?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v6h-6" fill="none"/></svg>':"delete"===e?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 7V5h6v2m-7 3v7m4-7v7m4-7v7M7 7l1 12h8l1-12" fill="none"/></svg>':"copy"===e?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 9h10v10H9zM5 15H4V5h10v1" fill="none"/></svg>':""}function renderIconButton({title:e,action:t,icon:n,className:a=""}){return`<button class="${`iconbtn ${a}`.trim()}" title="${escapeHtml(e)}" aria-label="${escapeHtml(e)}" onclick="${t}">${svgIcon(n)}</button>`}async function copyTextValue(e){const t=String(e||"");if(!t)return!1;if(navigator.clipboard&&navigator.clipboard.writeText)try{return await navigator.clipboard.writeText(t),!0}catch(e){}const n=document.createElement("textarea");n.value=t,n.setAttribute("readonly","readonly"),n.style.position="fixed",n.style.opacity="0",document.body.appendChild(n),n.focus(),n.select();let a=!1;try{a=document.execCommand("copy")}catch(e){a=!1}return n.remove(),a}function ensureApiKeyModal(){if($("apiKeyModal"))return;const e=document.createElement("div");e.id="apiKeyModal",e.className="club-modal hidden",e.innerHTML=`<div class="club-modal-card" role="dialog" aria-modal="true" aria-labelledby="apiKeyModalTitle"><div class="panel-head"><h2 id="apiKeyModalTitle">API Key</h2><button class="iconbtn" title="Close" aria-label="Close" onclick="closeApiKeyModal()">${svgIcon("delete")}</button></div><div class="preset-help" id="apiKeyModalHint">Use Copy to place the key on the clipboard.</div><textarea id="apiKeyModalValue" class="modal-keybox" readonly wrap="off"></textarea><div class="preset-form-actions"><button class="btn amber" onclick="copyApiKeyModalValue()">Copy</button><button class="btn blue" onclick="closeApiKeyModal()">Close</button></div><div class="msg" id="apiKeyModalMsg"></div></div>`,e.addEventListener("click",t=>{t.target===e&&closeApiKeyModal()}),document.body.appendChild(e)}function openApiKeyModal(e,t,n=""){ensureApiKeyModal(),$("apiKeyModalTitle").textContent=e||"API Key",$("apiKeyModalHint").textContent=n||"Use Copy to place the key on the clipboard.",$("apiKeyModalValue").value=t||"",$("apiKeyModalMsg").textContent="",$("apiKeyModal").classList.remove("hidden")}function closeApiKeyModal(){ensureApiKeyModal(),$("apiKeyModal").classList.add("hidden")}async function copyApiKeyModalValue(){ensureApiKeyModal();const e=await copyTextValue($("apiKeyModalValue").value||"");$("apiKeyModalMsg").textContent=e?"Copied API key to clipboard.":"Copy failed on this browser."}function setInstanceMsg(e){$("instanceMsg")&&($("instanceMsg").textContent=e||"")}function getInstanceList(){return lastStatus&&lastStatus.instances||[]}function setUsersMsg(e){$("usersMsg")&&($("usersMsg").textContent=e||"")}async function saveUserForm(){try{const e=await fetch("/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"save",user:collectUserForm()})}),t=await e.json();if(!e.ok||!t.ok)throw new Error(t.error||"save failed");t.api_key&&openApiKeyModal("API key for "+t.user.name,t.api_key,"This key is now stored so it can be viewed again from the user card."),resetUserForm(),setUsersMsg("Saved user "+t.user.name),await refreshStatus()}catch(e){alert("User save failed: "+e)}}async function showUserApiKey(e){try{const t=await fetch("/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"show_key",name:e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"show failed");openApiKeyModal("API key for "+e,n.api_key,"Use Copy to place the current key on the clipboard.")}catch(e){alert("API key lookup failed: "+e)}}async function resetUserKey(e){if(confirm("Reset API key for "+e+"?"))try{const t=await fetch("/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"reset_key",name:e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"reset failed");openApiKeyModal("New API key for "+e,n.api_key,"The previous key is no longer valid. Use Copy if you need to share the replacement key."),setUsersMsg("Reset API key for "+e),await refreshStatus()}catch(e){alert("API key reset failed: "+e)}}async function deleteUserByName(e){if(confirm("Delete user "+e+"?"))try{const t=await fetch("/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"delete",name:e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"delete failed");selectedUserName===e&&resetUserForm(),setUsersMsg("Deleted user "+e),await refreshStatus()}catch(e){alert("User delete failed: "+e)}}let currentLogSource="docker";function setAuditMsg(e){$("auditMsg")&&($("auditMsg").textContent=e||"")}function mirrorAuthToggles(e){$("auditAllowAnonymousProxy")&&($("auditAllowAnonymousProxy").checked=!!e)}let selectedGroupName="";function setGroupsMsg(e){$("groupsMsg")&&($("groupsMsg").textContent=e||"")}function findPanelByHeading(e,t){return[...document.querySelectorAll(`#${e} .panel`)].find(e=>{const n=e.querySelector(".panel-head h2,h2");return(n&&n.textContent||"").trim()===t})||null}let selectedScope="GPU0";function currentScope(){return selectedScope||selectedInstance||"GPU0"}function scopeIsGlobal(){return"GLOBAL"===currentScope()}function ensureV413Layout(){const e=document.querySelector(".tabs"),t=e&&e.querySelector('.tab[onclick*="audit"]'),n=e&&e.querySelector('.tab[onclick*="logs"]');t&&t.remove(),e&&n&&e.appendChild(n);const a=$("system"),s=$("presets"),o=$("logs"),r=$("audit");if(a&&r){const e=findPanelByHeading("audit","Access Policy");e&&!e.dataset.v413Moved&&(e.dataset.v413Moved="1",a.insertBefore(e,a.children[1]||null));const t=findPanelByHeading("audit","Audit Overview");t&&o&&!t.dataset.v413Moved&&(t.dataset.v413Moved="1",o.insertBefore(t,o.firstChild||null));const n=findPanelByHeading("audit","Global Controls");n&&n.remove();const s=findPanelByHeading("audit","Audit Stream");s&&s.remove(),0!==r.childElementCount&&r.querySelector(".panel")||r.remove()}const i=findPanelByHeading("system","Access Policy");if(i){const e=[...i.querySelectorAll("button")].find(e=>(e.textContent||"").includes("Open Users Management"));e&&e.remove()}const l=[...document.querySelectorAll("#presets .panel")].find(e=>{const t=e.querySelector(".panel-head h2,h2");return t&&((t.textContent||"").includes("Per-Instance Docker Presets")||(t.textContent||"").includes("Single GPU Docker Presets"))});if(l){l.id="singlePresetCard";const e=l.querySelector("h2");e&&(e.textContent="Single GPU Docker Presets")}const c=[...document.querySelectorAll("#presets .panel .panel-head h2")].find(e=>"Custom Preset Templates"===(e.textContent||"").trim());if(c&&(c.textContent="Custom Configuration Endpoints"),s&&!$("presetScopePanel")){const e=document.createElement("div");e.className="panel",e.id="presetScopePanel",e.innerHTML='<h2>GPU Scope</h2><div class="subtabs" id="presetScopeTabs"></div><div class="value smallgap" id="presetScopeSummary">-</div>',s.insertBefore(e,s.firstChild||null)}if(s&&!$("dualPresetCard")){const e=document.createElement("div");e.className="panel",e.id="dualPresetCard",e.innerHTML='<h2>Dual GPU Docker Presets</h2><div class="preset-help">Apply a dual-GPU runtime across the first two detected cards. Use Global scope for these presets.</div><div class="actions"><button class="btn blue" onclick="switchDualMode(\'vllm/dual\')">dual</button><button class="btn blue" onclick="switchDualMode(\'vllm/dual-turbo\')">dual-turbo</button><button class="btn blue" onclick="switchDualMode(\'vllm/dual-dflash\')">dual-dflash</button><button class="btn blue" onclick="switchDualMode(\'vllm/dual-dflash-noviz\')">dual-dflash-noviz</button></div>';const t=$("singlePresetCard");t&&t.parentNode===s?s.insertBefore(e,t.nextSibling):s.insertBefore(e,s.children[1]||null)}if(o&&!$("logsSourcePanel")){const e=document.createElement("div");e.className="panel",e.id="logsSourcePanel",e.innerHTML='<h2>Log Sources</h2><div class="subtabs"><button class="subtab" id="logSourceDocker" onclick="setCurrentLogSource(\'docker\')">Docker Logs</button><button class="subtab" id="logSourceAudit" onclick="setCurrentLogSource(\'audit\')">Audit Logs</button></div><div class="value smallgap" id="logsSourceSummary">-</div>',o.appendChild(e)}const u=findPanelByHeading("system","Profiles");if(u&&!$("profileScopeNote")){const e=document.createElement("div");e.className="preset-help",e.id="profileScopeNote",u.insertBefore(e,u.querySelector(".actions")||u.firstChild)}const d=findPanelByHeading("system","Power + Cooling");if(d&&!$("powerScopeNote")){const e=document.createElement("div");e.className="preset-help",e.id="powerScopeNote",d.insertBefore(e,d.querySelector(".actions")||d.firstChild)}}function quotaLimitText(e,t=""){return null==e||""===e?"unlimited":`${e}${t}`}function quotaWeightText(e){return null==e||""===e?"default":String(Number(e).toFixed(3)).replace(/\.?0+$/,"")}function quotaWindowText(e){return`${(e=e||{}).requests||0} msgs · score ${Number(e.score||0).toFixed(1)} · in ${e.input_tokens||0} · out ${e.output_tokens||0} · tools ${e.tool_calls||0} · thinking ${Number(e.thinking_seconds||0).toFixed(1)}s`}function quotaWeightLine(e){return`in ${quotaWeightText((e=e||{}).input_token_weight)} · out ${quotaWeightText(e.output_token_weight)} · tools ${quotaWeightText(e.tool_call_weight)} · thinking ${quotaWeightText(e.thinking_second_weight)}`}function quotaBudgetLine(e){return`5h ${quotaLimitText((e=e||{}).score_per_5h)} · week ${quotaLimitText(e.score_per_week)} · /msg tokens ${quotaLimitText(e.max_tokens_per_message)} · /msg tools ${quotaLimitText(e.max_tool_calls_per_message)}`}function parseQuotaNumber(e){const t=$(e);if(!t)return null;const n=t.value.trim();return""===n?null:Number(n)}function scopeItems(){const e=getInstanceList().slice();return e.sort((e,t)=>{const n="dual"===e.kind?1:0,a="dual"===t.kind?1:0;if(n!==a)return n-a;return((e.gpu_indices||[e.gpu_index])[0]||0)-((t.gpu_indices||[t.gpu_index])[0]||0)||String(e.id).localeCompare(String(t.id))}),e}function singleScopeItems(){return scopeItems().filter(e=>"dual"!==e.kind)}function pairScopeItems(){return scopeItems().filter(e=>"dual"===e.kind)}function gpuCount(){return Number(lastStatus&&lastStatus.gpu_count||0)}function canonicalPairId(e,t){const n=[Number(e),Number(t)].filter(e=>Number.isInteger(e)&&e>=0).sort((e,t)=>e-t);return 2!==n.length||n[0]===n[1]?"":`PAIR${n[0]}_${n[1]}`}function exactTwoPairTarget(){return pairScopeItems().find(e=>"[0,1]"===JSON.stringify((e.gpu_indices||[]).slice().sort((e,t)=>e-t)))||null}function currentScopeInstance(e=!1){return"GLOBAL"===currentScope()?e?null:exactTwoPairTarget():scopeItems().find(e=>e.id===currentScope())||singleScopeItems()[0]||pairScopeItems()[0]||null}function currentScopeKind(){const e=currentScopeInstance(!0);return e?e.kind:"GLOBAL"===currentScope()?"global":"single"}function dockerLogTarget(){return trackedLogRuntime()||currentScopeInstance(!1)||scopeItems()[0]||null}function scopeLabel(e){return e?"dual"===e.kind?`Pair ${(e.gpu_indices||[]).join(" + ")}`:e.id:"Global"}function scopeAllowsSinglePresets(){const e=currentScopeInstance(!0);return!!e&&"dual"!==e.kind}function scopeAllowsDualPresets(){const e=currentScopeInstance(!1);return!!e&&"dual"===e.kind}function runtimeTrackingItems(){const e=Object.values(lastStatus&&lastStatus.instance_runtime_metrics||{}).filter(e=>e&&e.running);return e.sort((e,t)=>{const n=Array.isArray(e.gpu_indices)?e.gpu_indices:[],a=Array.isArray(t.gpu_indices)?t.gpu_indices:[];return(n[0]??999)-(a[0]??999)||n.length-a.length||String(e.id||e.instance_id||"").localeCompare(String(t.id||t.instance_id||""))}),e}function normalizeTrackedRuntimeId(e){const t=runtimeTrackingItems();if(!t.length)return"";const n=String(e||"").trim().toUpperCase();if(n){const e=t.find(e=>String(e.id||e.instance_id).toUpperCase()===n);if(e)return String(e.id||e.instance_id)}return String(t[0].id||t[0].instance_id)}function trackedOverviewRuntime(){const e=normalizeTrackedRuntimeId(selectedOverviewInstanceId);return e?(selectedOverviewInstanceId=e,runtimeTrackingItems().find(t=>String(t.id||t.instance_id)===String(e))||null):null}function trackedLogRuntime(){const e=normalizeTrackedRuntimeId(selectedLogInstanceId);return e?(selectedLogInstanceId=e,runtimeTrackingItems().find(t=>String(t.id||t.instance_id)===String(e))||null):null}function setOverviewTrackedInstance(e){selectedOverviewInstanceId=normalizeTrackedRuntimeId(e),renderOverviewTracker(),lastStatus&&renderOverviewStatus(lastStatus)}function setLogTrackedInstance(e){selectedLogInstanceId=normalizeTrackedRuntimeId(e),renderLogTracker(),applyLogVisibility(),connectLogs(!0)}function formatCtxTokens(e){const t=Number(e||0);return!Number.isFinite(t)||t<=0?"-":t>=1e6?`${(t/1e6).toFixed(2).replace(/\.?0+$/,"")}M`:t>=1e3?`${(t/1e3).toFixed(t>=1e5?0:1).replace(/\.?0+$/,"")}K`:String(Math.round(t))}function formatNumber(e,t=2){const n=Number(e);return Number.isFinite(n)?n.toFixed(t).replace(/\.?0+$/,""):"-"}function formatLastStatusCard(e,t){const n=e||{},a=[n.last_status??t.last_status??"-"],s=n.last_latency_s??t.last_latency_s,o=n.last_ttft_s??t.last_ttft_s,r=n.last_tokens_per_second??t.last_tokens_per_second;null!=s&&a.push(`latency=${formatNumber(s,3)}s`),null!=o&&a.push(`ttft=${formatNumber(o,3)}s`),null!==n.last_prefill_s&&void 0!==n.last_prefill_s&&a.push(`prefill~=${formatNumber(n.last_prefill_s,3)}s`),null!=r&&a.push(`tk/s=${formatNumber(r,2)}`);const i=[];null!==n.gpu_kv_cache_usage_pct&&void 0!==n.gpu_kv_cache_usage_pct?i.push(`kv=${formatNumber(n.gpu_kv_cache_usage_pct,1)}% / ${formatCtxTokens(n.ctx_size_tokens)} ctx`):n.ctx_size_tokens&&i.push(`ctx=${formatCtxTokens(n.ctx_size_tokens)}`);const l=n.speculative||{},c=[];null!==l.drafted_tokens&&void 0!==l.drafted_tokens&&c.push(`drafted=${l.drafted_tokens}`),null!==l.accept_rate_pct&&void 0!==l.accept_rate_pct&&c.push(`accept=${formatNumber(l.accept_rate_pct,1)}%`),null!==l.accepted_tokens&&void 0!==l.accepted_tokens&&null!==l.draft_tokens&&void 0!==l.draft_tokens&&c.push(`accepted=${l.accepted_tokens}/${l.draft_tokens}`),null!==l.mean_acceptance_length&&void 0!==l.mean_acceptance_length&&c.push(`avg=${formatNumber(l.mean_acceptance_length,2)}`),null!==l.system_efficiency_pct&&void 0!==l.system_efficiency_pct&&c.push(`eff=${formatNumber(l.system_efficiency_pct,1)}%`);const u=[`<div>${a.join(" &middot; ")}</div>`];return i.length&&u.push(`<div class="value-subline">${i.join(" &middot; ")}</div>`),c.length&&u.push(`<div class="value-subline">spec ${c.join(" &middot; ")}</div>`),u.join("")}function formatRequestCard(e,t){const n=`total=${t.total_requests??0}, active=${t.active_requests??0}, fail=${t.failed_requests??0}, queue=${t.queued_requests??0}`;if(!e)return n;const a=[];return null!==e.running_requests&&void 0!==e.running_requests&&a.push(`run=${e.running_requests}`),null!==e.waiting_requests&&void 0!==e.waiting_requests&&a.push(`wait=${e.waiting_requests}`),null!==e.pending_requests&&void 0!==e.pending_requests&&a.push(`pending=${e.pending_requests}`),a.length?`${n}<div class="value-subline">instance ${a.join(" &middot; ")}</div>`:n}function renderOverviewTracker(){const e=findPanelByHeading("overview","Status");if(!e)return;let t=$("overviewTrackerRow");if(!t){t=document.createElement("div"),t.id="overviewTrackerRow",t.className="scope-strip";const n=e.querySelector(".grid");e.insertBefore(t,n||e.querySelector(".msg")||null)}const n=runtimeTrackingItems();if(n.length<=1)return t.innerHTML="",void t.classList.add("hidden");t.classList.remove("hidden");const a=normalizeTrackedRuntimeId(selectedOverviewInstanceId);selectedOverviewInstanceId=a,t.innerHTML=`<span class="label">Track instance</span><div class="subtabs">${n.map(e=>`<button class="subtab ${String(e.id||e.instance_id)===a?"active":""}" onclick="setOverviewTrackedInstance('${String(e.id||e.instance_id)}')">${escapeHtml(String(e.id||e.instance_id))}</button>`).join("")}</div>`}function renderLogTracker(){const e=document.querySelector(".logs.panel");if(!e)return;let t=$("logTrackerRow");t||(t=document.createElement("div"),t.id="logTrackerRow",t.className="scope-strip",e.insertBefore(t,$("log")||e.lastChild||null));const n=runtimeTrackingItems();if("audit"===currentLogSource||n.length<=1)return t.innerHTML="",void t.classList.add("hidden");t.classList.remove("hidden");const a=normalizeTrackedRuntimeId(selectedLogInstanceId);selectedLogInstanceId=a,t.innerHTML=`<span class="label">Track instance</span><div class="subtabs">${n.map(e=>`<button class="subtab ${String(e.id||e.instance_id)===a?"active":""}" onclick="setLogTrackedInstance('${String(e.id||e.instance_id)}')">${escapeHtml(String(e.id||e.instance_id))}</button>`).join("")}</div>`}function renderOverviewStatus(e){const t=e&&e.metrics||{},n=e&&e.power||{},a=trackedOverviewRuntime();$("summary")&&($("summary").textContent=a?`${a.id||a.instance_id} | ${a.mode||e.active_mode} | ${a.container||"no container"} | ${n.profile||"balanced"} | GPUs ${e.gpu_count??0}`:`${e.active_mode} | ${e.container||"no container"} | ${n.profile||"balanced"} | GPUs ${e.gpu_count??0}`),$("mode")&&($("mode").textContent=`${a?.mode||e.active_mode} / ${a?.port||e.active_port}`),$("container")&&($("container").textContent=a?.container||e.container||"none"),$("req")&&($("req").innerHTML=formatRequestCard(a,t)),$("last")&&($("last").innerHTML=formatLastStatusCard(a,t)),$("uptime")&&($("uptime").textContent=fmtUptime(e.uptime_seconds)),$("powerbox")&&($("powerbox").textContent=`profile=${n.profile||"-"}, GPU=${n.gpu||"-"}, CPU=${n.cpu||"-"}, fans=${n.fans||"-"}, container=${n.container||"-"}, idle=${n.idle_for_seconds??0}s`),renderOverviewTracker()}function setEditorState(e,t,n){const a=$(e),s=$(t);a&&a.classList.toggle("open",!!n),s&&s.classList.toggle("hidden",!!n)}function openUserEditor(){ensureUsersUi(),setEditorState("userEditor","userIntro",!0)}function openGroupEditor(){ensureGroupUi(),setEditorState("groupEditor","groupIntro",!0)}async function createPairGroup(e=null,t=null){if(gpuCount()<2)return void alert("At least two GPUs are required to create a dual pair.");let n=e,a=t;if(null===n||null===a){if(n=prompt(`First GPU index (0-${Math.max(gpuCount()-1,0)}):`,"0"),null===n)return;if(a=prompt(`Second GPU index (0-${Math.max(gpuCount()-1,0)}):`,"1"),null===a)return}const s=canonicalPairId(n,a);if(s)try{const e=await fetch("/admin/instances",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"save_pair",gpu_indices:[Number(n),Number(a)],mode:"vllm/dual",enabled:!1})}),t=await e.json();if(!e.ok||!t.ok)throw new Error(t.error||"pair save failed");setInstanceMsg(`Saved pair group ${s}`),await refreshStatus(),setScope(s,!1)}catch(e){alert("Pair group failed: "+e)}else alert("Select two distinct GPU indices.")}async function deleteCurrentPairGroup(){const e=currentScopeInstance(!0);if(e&&"dual"===e.kind){if(confirm(`Delete pair group ${e.id}?`))try{const t=await fetch("/admin/instances",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"delete_pair",instance_id:e.id})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"pair delete failed");setInstanceMsg(`Deleted pair group ${e.id}`),await refreshStatus(),setScope("GLOBAL",!1)}catch(e){alert("Pair delete failed: "+e)}}else alert("Select a dual pair scope first.")}async function switchDualMode(e){const t=currentScopeInstance(!1);if(t&&"dual"===t.kind){if(confirm(`Apply dual preset ${e} to ${t.id} on GPUs ${(t.gpu_indices||[]).join(", ")}? This will stop overlapping runtimes that already use those GPUs.`))try{await post("/admin/switch",{instance_id:t.id,mode:e})}catch(e){alert(e)}}else alert("Choose a dual pair tab, or use Global on an exactly-two-GPU server, before applying a dual preset.")}function profileDescription(e){return{eco:"Eco profile: lower GPU power limits, lower idle clocks, powersave CPU governor, faster idle/container stop timers.",balanced:"Balanced profile: normal server profile with 280W active GPU cap, idle downclocking after 10 minutes, and container stop after 1 hour.",default:"Default profile: keeps the 280W safety GPU cap but removes idle clock locking, uses schedutil CPU while active, and keeps standard idle timers.",turbo:"Turbo profile: higher GPU power allowance, performance CPU governor, relaxed idle timers, and minimal downclocking. Use when performance matters more than power."}[e]||"Apply profile?"}function applyDirectoryPayload(e){lastStatus||(lastStatus={}),Array.isArray(e.users)&&(lastStatus.users=e.users,renderUsers(e.users)),Array.isArray(e.groups)&&(lastStatus.groups=e.groups,renderGroups(e.groups)),e.server_config&&(lastStatus.server_config=e.server_config,renderAudit(e.server_config))}ensureUsersUi=function(){const e=document.querySelector(".tabs");if(e&&!document.getElementById("usersTabBtn")){const t=document.createElement("button");t.className="tab",t.id="usersTabBtn",t.textContent="Users",t.onclick=e=>tab(e,"users"),e.insertBefore(t,e.querySelector('.tab[onclick*="metrics"]')||null)}const t=document.querySelector("main.container");if(!t)return;let n=$("users");n||(n=document.createElement("section"),n.id="users",n.className="tabpane content-tab",t.insertBefore(n,document.getElementById("metrics"))),"1"!==n.dataset.v414Users&&(n.dataset.v414Users="1",n.innerHTML='<div class="panel"><div class="panel-head"><h2>User Accounts</h2><button class="add-preset-btn" title="New user" aria-label="New user" onclick="resetUserForm(false)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div class="preset-intro" id="userIntro">Manage per-user API keys, access scopes, and Codex-style scored budgets. The configured list stays visible while the editor is collapsed.</div><div class="preset-editor" id="userEditor"><div class="formgrid"><label>User name<input id="userName" placeholder="client_a" /></label><label>Allowed targets<input id="userTargets" placeholder="*, legacy, GPU0, GPU1" /></label><label>Groups<input id="userGroups" placeholder="starter, premium" /></label><label>5h score budget<input id="userScore5h" type="number" step="0.1" placeholder="unlimited" /></label><label>Weekly score budget<input id="userScoreWeek" type="number" step="0.1" placeholder="unlimited" /></label><label>Max tokens / message<input id="userMaxTokensMsg" type="number" step="1" placeholder="unlimited" /></label><label>Max tool calls / message<input id="userMaxToolsMsg" type="number" step="1" placeholder="unlimited" /></label><label>Input token weight<input id="userInputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Output token weight<input id="userOutputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Tool-call weight<input id="userToolCallWeight" type="number" step="0.001" placeholder="default" /></label><label>Thinking-second weight<input id="userThinkingSecondWeight" type="number" step="0.001" placeholder="default" /></label><label>Enabled<select id="userEnabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveUserForm()">Save User</button><button class="btn red" onclick="resetUserForm(true)">Cancel</button></div></div><div class="msg" id="usersMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured Users</h2><div id="usersGrid" class="api-grid"></div></div></div>')},resetUserForm=function(e=!0){ensureUsersUi(),selectedUserName="",$("userName").disabled=!1,$("userName").value="",$("userTargets").value="*",$("userGroups").value="",$("userScore5h").value="",$("userScoreWeek").value="",$("userMaxTokensMsg").value="",$("userMaxToolsMsg").value="",$("userInputTokenWeight").value="",$("userOutputTokenWeight").value="",$("userToolCallWeight").value="",$("userThinkingSecondWeight").value="",$("userEnabled").value="true",setEditorState("userEditor","userIntro",!e),setUsersMsg("")},collectUserForm=function(){function e(e){return($(e)&&$(e).value||"").trim()}return{name:e("userName"),allowed_targets:e("userTargets").split(",").map(e=>e.trim()).filter(Boolean),groups:e("userGroups").split(",").map(e=>e.trim()).filter(Boolean),enabled:"true"===$("userEnabled").value,generate_api_key:!selectedUserName,limits:{score_per_5h:parseQuotaNumber("userScore5h"),score_per_week:parseQuotaNumber("userScoreWeek"),max_tokens_per_message:parseQuotaNumber("userMaxTokensMsg"),max_tool_calls_per_message:parseQuotaNumber("userMaxToolsMsg"),input_token_weight:parseQuotaNumber("userInputTokenWeight"),output_token_weight:parseQuotaNumber("userOutputTokenWeight"),tool_call_weight:parseQuotaNumber("userToolCallWeight"),thinking_second_weight:parseQuotaNumber("userThinkingSecondWeight")}}},editUser=function(e){const t=(lastStatus&&lastStatus.users||[]).find(t=>t.name===e);t&&(ensureUsersUi(),selectedUserName=e,$("userName").disabled=!0,$("userName").value=t.name,$("userTargets").value=(t.allowed_targets||[]).join(", "),$("userGroups").value=(t.groups||[]).join(", "),$("userScore5h").value=t.limits.score_per_5h??"",$("userScoreWeek").value=t.limits.score_per_week??"",$("userMaxTokensMsg").value=t.limits.max_tokens_per_message??"",$("userMaxToolsMsg").value=t.limits.max_tool_calls_per_message??"",$("userInputTokenWeight").value=t.limits.input_token_weight??"",$("userOutputTokenWeight").value=t.limits.output_token_weight??"",$("userToolCallWeight").value=t.limits.tool_call_weight??"",$("userThinkingSecondWeight").value=t.limits.thinking_second_weight??"",$("userEnabled").value=String(!!t.enabled),openUserEditor())},renderUsers=function(e){ensureUsersUi();const t=$("usersGrid");t&&(e=e||[],selectedUserName&&!e.some(e=>e.name===selectedUserName)&&(selectedUserName=""),t.innerHTML=e.map(e=>{const t=[renderIconButton({title:"Edit",action:`editUser('${e.name}')`,icon:"edit"}),renderIconButton({title:e.api_key_available?"Show API key":"Show API key unavailable",action:`showUserApiKey('${e.name}')`,icon:"key"}),renderIconButton({title:"Reset API key",action:`resetUserKey('${e.name}')`,icon:"reset"}),renderIconButton({title:"Delete",action:`deleteUserByName('${e.name}')`,icon:"delete"})].join("");return`<div class="api-card"><div class="api-card-head"><h3>${e.name}<br><span class="label">${e.enabled?"enabled":"disabled"} &middot; access ${(e.effective_allowed_targets||e.allowed_targets||[]).join(", ")||"*"}</span></h3><span class="preset-actions">${t}</span></div><p>Groups: ${(e.groups||[]).join(", ")||"none"}</p><p>API key: ${e.has_api_key?e.api_key_available?"stored and viewable":"legacy key, reset once to store it":"not issued yet"}</p><p>Last 5h: ${quotaWindowText((e.usage||{}).window_5h)}</p><p>Last week: ${quotaWindowText((e.usage||{}).window_week)}</p><p class="label">Direct budgets &middot; ${quotaBudgetLine(e.limits||{})}</p><p class="label">Direct weights &middot; ${quotaWeightLine(e.limits||{})}</p><p class="label">Effective budgets &middot; ${quotaBudgetLine(e.effective_limits||{})}</p><p class="label">Effective weights &middot; ${quotaWeightLine(e.effective_limits||{})}</p></div>`}).join("")||'<div class="value">No API users configured yet.</div>')},ensureGroupUi=function(){ensureUsersUi();const e=$("users");if(!e)return;let t=$("groupsPanel");t||(t=document.createElement("div"),t.className="panel",t.id="groupsPanel",e.appendChild(t)),"1"!==t.dataset.v414Groups&&(t.dataset.v414Groups="1",t.innerHTML='<div class="panel-head"><h2>User Groups / Plans</h2><button class="add-preset-btn" title="New group" aria-label="New group" onclick="resetGroupForm(false)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none"/></svg></button></div><div class="preset-intro" id="groupIntro">Define reusable plans that carry scored budgets, per-message caps, and access scopes. The configured list stays visible while the editor is collapsed.</div><div class="preset-editor" id="groupEditor"><div class="formgrid"><label>Group name<input id="groupName" placeholder="starter" /></label><label>Description<input id="groupDescription" placeholder="Shared plan description" /></label><label>Allowed targets<input id="groupTargets" placeholder="*, legacy, GPU0, GPU1" /></label><label>5h score budget<input id="groupScore5h" type="number" step="0.1" placeholder="unlimited" /></label><label>Weekly score budget<input id="groupScoreWeek" type="number" step="0.1" placeholder="unlimited" /></label><label>Max tokens / message<input id="groupMaxTokensMsg" type="number" step="1" placeholder="unlimited" /></label><label>Max tool calls / message<input id="groupMaxToolsMsg" type="number" step="1" placeholder="unlimited" /></label><label>Input token weight<input id="groupInputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Output token weight<input id="groupOutputTokenWeight" type="number" step="0.001" placeholder="default" /></label><label>Tool-call weight<input id="groupToolCallWeight" type="number" step="0.001" placeholder="default" /></label><label>Thinking-second weight<input id="groupThinkingSecondWeight" type="number" step="0.001" placeholder="default" /></label><label>Enabled<select id="groupEnabled"><option value="true">Enabled</option><option value="false">Disabled</option></select></label></div><div class="preset-form-actions"><button class="btn green" onclick="saveGroupForm()">Save Group</button><button class="btn red" onclick="resetGroupForm(true)">Cancel</button></div></div><div class="msg" id="groupsMsg"></div><div class="panel" style="margin-top:12px"><h2>Configured Groups</h2><div id="groupsGrid" class="api-grid"></div></div>')},resetGroupForm=function(e=!0){ensureGroupUi(),selectedGroupName="",$("groupName").disabled=!1,$("groupName").value="",$("groupDescription").value="",$("groupTargets").value="*",$("groupScore5h").value="",$("groupScoreWeek").value="",$("groupMaxTokensMsg").value="",$("groupMaxToolsMsg").value="",$("groupInputTokenWeight").value="",$("groupOutputTokenWeight").value="",$("groupToolCallWeight").value="",$("groupThinkingSecondWeight").value="",$("groupEnabled").value="true",setEditorState("groupEditor","groupIntro",!e),setGroupsMsg("")},collectGroupForm=function(){function e(e){return($(e)&&$(e).value||"").trim()}return{name:e("groupName"),description:e("groupDescription"),allowed_targets:e("groupTargets").split(",").map(e=>e.trim()).filter(Boolean),enabled:"true"===$("groupEnabled").value,limits:{score_per_5h:parseQuotaNumber("groupScore5h"),score_per_week:parseQuotaNumber("groupScoreWeek"),max_tokens_per_message:parseQuotaNumber("groupMaxTokensMsg"),max_tool_calls_per_message:parseQuotaNumber("groupMaxToolsMsg"),input_token_weight:parseQuotaNumber("groupInputTokenWeight"),output_token_weight:parseQuotaNumber("groupOutputTokenWeight"),tool_call_weight:parseQuotaNumber("groupToolCallWeight"),thinking_second_weight:parseQuotaNumber("groupThinkingSecondWeight")}}},editGroup=function(e){const t=(lastStatus&&lastStatus.groups||[]).find(t=>t.name===e);t&&(ensureGroupUi(),selectedGroupName=e,$("groupName").disabled=!0,$("groupName").value=t.name,$("groupDescription").value=t.description||"",$("groupTargets").value=(t.allowed_targets||[]).join(", "),$("groupScore5h").value=t.limits.score_per_5h??"",$("groupScoreWeek").value=t.limits.score_per_week??"",$("groupMaxTokensMsg").value=t.limits.max_tokens_per_message??"",$("groupMaxToolsMsg").value=t.limits.max_tool_calls_per_message??"",$("groupInputTokenWeight").value=t.limits.input_token_weight??"",$("groupOutputTokenWeight").value=t.limits.output_token_weight??"",$("groupToolCallWeight").value=t.limits.tool_call_weight??"",$("groupThinkingSecondWeight").value=t.limits.thinking_second_weight??"",$("groupEnabled").value=String(!!t.enabled),openGroupEditor())},renderGroups=function(e){ensureGroupUi();const t=$("groupsGrid");t&&(e=e||[],selectedGroupName&&!e.some(e=>e.name===selectedGroupName)&&(selectedGroupName=""),t.innerHTML=e.map(e=>`<div class="api-card"><div class="api-card-head"><h3>${e.name}<br><span class="label">${e.enabled?"enabled":"disabled"} · access ${(e.allowed_targets||[]).join(", ")||"*"}</span></h3><span class="preset-actions"><button class="iconbtn" title="Edit" onclick="editGroup('${e.name}')">✏️</button><button class="iconbtn" title="Delete" onclick="deleteGroupByName('${e.name}')">❌</button></span></div><p>${e.description||"No description"}</p><p class="label">Configured budgets · ${quotaBudgetLine(e.limits||{})}</p><p class="label">Configured weights · ${quotaWeightLine(e.limits||{})}</p><p class="label">Resolved budgets · ${quotaBudgetLine(e.resolved_limits||e.limits||{})}</p><p class="label">Resolved weights · ${quotaWeightLine(e.resolved_limits||e.limits||{})}</p></div>`).join("")||'<div class="value">No groups configured yet.</div>')},renderAudit=function(e){e=e||{},ensureV414Layout();const t=lastStatus&&lastStatus.admin_port||8008,n=lastStatus&&lastStatus.proxy_port||8009,a=e.admin_path||"/admin",s=!!e.online_enabled,o=!!e.allow_proxy_without_api_key,r=!!e.local_api_enabled,i=e.local_api_port||10881;$("auditAdminEndpoint")&&($("auditAdminEndpoint").innerHTML=`:${t}${a}`),$("auditProxyEndpoint")&&($("auditProxyEndpoint").innerHTML=`:${n}`),$("auditExposure")&&($("auditExposure").textContent=s?"online through proxy/admin only":"local/private only"),$("auditLocalApi")&&($("auditLocalApi").textContent=r?`127.0.0.1:${i}`:"disabled"),$("auditSummary")&&($("auditSummary").innerHTML="Audit entries capture admin actions, proxy authentication outcomes, quota denials, API usage, group changes, and user-management events. Use the shared log viewer below to inspect either Docker runtime logs or the audit log stream."),$("auditPolicyText")&&($("auditPolicyText").innerHTML=`Proxy API keys are currently <b>${o?"optional":"required"}</b>. Admin UI remains under <code>:${t}${a}</code>.`),mirrorAuthToggles(o)},saveAuthSettings=async function(){const e=!(!$("auditAllowAnonymousProxy")||!$("auditAllowAnonymousProxy").checked);mirrorAuthToggles(e);try{const t=await fetch("/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"save_server_config",allow_proxy_without_api_key:e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"config failed");n.server_config&&renderAudit(n.server_config),setAuditMsg("Saved access policy"),await refreshStatus()}catch(e){alert("Access policy failed: "+e)}},renderInstances=function(e){ensureV414Layout();const t=$("instanceTabs"),n=$("instanceSummary"),a=$("instanceEnableBtn"),s=findPanelByHeading("system","Instances");if(!t||!n||!s)return;e=scopeItems(),selectedScope&&("GLOBAL"===selectedScope||e.some(e=>e.id===selectedScope))||(selectedScope=singleScopeItems()[0]?.id||pairScopeItems()[0]?.id||"GLOBAL");const o=singleScopeItems().map(e=>`<button class="subtab ${e.id===currentScope()?"active":""}" onclick="setScope('${e.id}')">${e.id}${e.running?" • on":" • off"}</button>`).join("")+pairScopeItems().map(e=>`<button class="subtab ${e.id===currentScope()?"active":""}" onclick="setScope('${e.id}')">Pair ${(e.gpu_indices||[]).join("+")}${e.running?" • on":" • off"}</button>`).join("")+`<button class="subtab ${scopeIsGlobal()?"active":""}" onclick="setScope('GLOBAL')">Global</button>`;t.innerHTML=o,ensurePairManager();const r=currentScopeInstance(!1),i=[...s.querySelectorAll(".actions .btn")].filter(e=>"instanceEnableBtn"!==e.id&&!e.closest("#pairManagerBar"));scopeIsGlobal()&&r&&2===gpuCount()?(n.innerHTML=`Global scope controls the only dual pair <code>${r.id}</code> on GPUs ${(r.gpu_indices||[]).join(", ")} · mode ${r.mode} · port ${r.port} · proxy <code>${r.proxy_prefix}/</code>`,a&&(a.disabled=!1,a.textContent=r.enabled?"Disable Boot Autostart":"Enable Boot Autostart"),i.forEach(e=>e.disabled=!1)):scopeIsGlobal()?(n.innerHTML="Global scope selected. Host-wide controls still apply below. Create or choose a dual pair tab to manage arbitrary two-GPU dual presets.",a&&(a.disabled=!0,a.textContent="Select a GPU or Pair Scope"),i.forEach(e=>e.disabled=!0)):r?(n.innerHTML=`${scopeLabel(r)} · ${r.assignment_text} · port ${r.port} · ${r.running?"running":"stopped"} · proxy <code>${r.proxy_prefix}/</code> · ${r.enabled?"autostart enabled":"autostart disabled"}`,a&&(a.disabled=!1,a.textContent=r.enabled?"Disable Boot Autostart":"Enable Boot Autostart"),i.forEach(e=>e.disabled=!1)):(n.textContent="No GPU instances configured",a&&(a.disabled=!0,a.textContent="Boot autostart unavailable"),i.forEach(e=>e.disabled=!0)),$("logInstanceLabel")&&($("logInstanceLabel").textContent=currentLogLabel())},renderPresetScopeTabs=function(){const e=$("presetScopeTabs"),t=$("presetScopeSummary");if(!e||!t)return;e.innerHTML=singleScopeItems().map(e=>`<button class="subtab ${e.id===currentScope()?"active":""}" onclick="setScope('${e.id}')">${e.id}</button>`).join("")+pairScopeItems().map(e=>`<button class="subtab ${e.id===currentScope()?"active":""}" onclick="setScope('${e.id}')">Pair ${(e.gpu_indices||[]).join("+")}</button>`).join("")+`<button class="subtab ${scopeIsGlobal()?"active":""}" onclick="setScope('GLOBAL')">Global</button>`;const n=currentScopeInstance(!1);scopeIsGlobal()&&n&&2===gpuCount()?t.innerHTML=`Global scope targets the only dual pair <code>${n.id}</code>. Dual preset buttons below will apply to GPUs ${(n.gpu_indices||[]).join(", ")}.`:scopeIsGlobal()?t.innerHTML="Global scope selected. Single-GPU presets are disabled here. Choose or create a dual pair tab to apply dual presets.":currentScopeInstance(!0)?t.innerHTML=`Targeting ${scopeLabel(currentScopeInstance(!0))} · ${currentScopeInstance(!0).assignment_text} · proxy <code>${currentScopeInstance(!0).proxy_prefix}/</code>`:t.textContent="No preset scope available",document.querySelectorAll("#singlePresetCard .actions .btn").forEach(e=>e.disabled=!scopeAllowsSinglePresets()),document.querySelectorAll("#dualPresetCard .actions .btn").forEach(e=>e.disabled=!scopeAllowsDualPresets())},updateScopedCards=function(){const e=currentScopeInstance(!1);$("profileScopeNote")&&($("profileScopeNote").innerHTML=scopeIsGlobal()?"Global scope: these profile buttons apply host-wide defaults for the full server.":`${scopeLabel(e)} scope: ${e?e.assignment_text:"select a scope to continue"}`),$("powerScopeNote")&&($("powerScopeNote").innerHTML=scopeIsGlobal()?"Global scope: power and cooling controls below affect the whole host.":`${scopeLabel(e)} scope: using the selected runtime context while keeping host-level power controls in sync.`),renderLogSourcePanel()},powerAction=async function(e){const t=currentScopeInstance(!1);if(!["stop_container","start_instance","restart_instance","toggle_enabled"].includes(e)||t){if("stop_container"!==e||confirm(`Stop ${scopeLabel(t)} now?`))try{await post("/admin/power",{action:e,instance_id:t?t.id:null,enabled:t?!t.enabled:void 0})}catch(e){alert(e)}}else alert("Select a GPU or Pair scope first.")},instanceAction=async function(e){await powerAction(e)},toggleInstanceEnabled=async function(){const e=currentScopeInstance(!1);if(e)try{await post("/admin/power",{action:"toggle_enabled",instance_id:e.id,enabled:!e.enabled})}catch(e){alert(e)}else alert("Select a GPU or Pair scope first.")},switchMode=async function(e){const t=currentScopeInstance(!0);if(!t||"dual"===t.kind)return void alert("Select a single GPU tab to apply a single-GPU preset.");const n=pairScopeItems().find(e=>e.running&&(e.gpu_indices||[]).includes(Number(t.gpu_index))),a=n?`\n\nWarning: GPU ${t.gpu_index} is currently occupied by ${n.id} running ${n.mode}. Continuing will stop that pair and replace it with ${e} on ${t.id}.`:"";if(confirm(`Assign ${e} to ${t.id} and start it?${a}`))try{await post("/admin/switch",{instance_id:t.id,mode:e})}catch(e){alert(e)}},profile=async function(e){if(confirm(profileDescription(e)+"\n\nApply this profile now?"))try{await post("/admin/profile",{profile:e},`/admin/profile ${e}`)}catch(e){alert(e)}},saveGroupForm=async function(){try{const e=await fetch("/admin/groups",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"save",group:collectGroupForm()})}),t=await e.json();if(!e.ok||!t.ok)throw new Error(t.error||"group save failed");applyDirectoryPayload(t),resetGroupForm(!0),setGroupsMsg("Saved group "+t.group.name),refreshStatus().catch(()=>{})}catch(e){alert("Group save failed: "+e)}},deleteGroupByName=async function(e){if(confirm("Delete group "+e+"?"))try{const t=await fetch("/admin/groups",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"delete",name:e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"group delete failed");applyDirectoryPayload(n),selectedGroupName===e&&resetGroupForm(!0),setGroupsMsg("Deleted group "+e),refreshStatus().catch(()=>{})}catch(e){alert("Group delete failed: "+e)}},pairingEnabled=function(){return!!(lastStatus&&lastStatus.server_config&&lastStatus.server_config.gpu_pairing_enabled)},legacyGlobalDualScope=function(){return 2===gpuCount()&&!pairingEnabled()},singleScopeItems=function(){return scopeItems().filter(e=>"dual"!==e.kind)},pairScopeItems=function(){return pairingEnabled()?scopeItems().filter(e=>"dual"===e.kind):[]},exactTwoPairTarget=function(){return 2===gpuCount()&&scopeItems().find(e=>"PAIR0_1"===e.id)||null},currentScopeInstance=function(e=!1){return"GLOBAL"===currentScope()?legacyGlobalDualScope()?e?null:legacyGlobalPair():pairingEnabled()&&2===gpuCount()?e?null:exactTwoPairTarget():null:scopeItems().find(e=>e.id===currentScope())||singleScopeItems()[0]||pairScopeItems()[0]||null},dockerLogTarget=function(){if("audit"===currentLogSource)return null;const e=legacyGlobalPair(),t=currentScopeInstance(!1)||scopeItems()[0]||null;return scopeIsGlobal()&&legacyGlobalDualScope()||legacyGlobalDualScope()&&e&&e.running&&t&&"dual"!==t.kind&&("pair"===t.assignment_scope||t.overrides_dual_mode||!t.running)?null:t},scopeLabel=function(e){return e?"GLOBAL"===e.id?"Global Dual":"dual"===e.kind?`Pair ${(e.gpu_indices||[]).join(" + ")}`:e.id:legacyGlobalDualScope()?"Global Dual":"Global"},scopeAllowsSinglePresets=function(){const e=currentScopeInstance(!0);return!!e&&"dual"!==e.kind},scopeAllowsDualPresets=function(){if(scopeIsGlobal()&&2===gpuCount())return!0;const e=currentScopeInstance(!1);return!!e&&"dual"===e.kind};const UI_STATE_KEY="club3090-ui-state";let uiStateHydrated=!1,uiStateSaveTimer=null,instanceBusyState={active:!1,message:""},currentLogSignature="",statusPollTimer=null;function readCachedUiState(){try{return JSON.parse(localStorage.getItem(UI_STATE_KEY)||"{}")||{}}catch(e){return{}}}function writeCachedUiState(e){try{localStorage.setItem(UI_STATE_KEY,JSON.stringify(e||{}))}catch(e){}}function normalizeTabName(e){return"audit"===e?"logs":["overview","system","presets","metrics","users","logs"].includes(e)?e:"overview"}function currentUiState(){return{active_tab:normalizeTabName(activeTabName),selected_scope:selectedScope||"GLOBAL",current_log_source:"audit"===currentLogSource?"audit":"docker",show_global_logs:!!showGlobalLogs}}function queueUiStateSave(e={}){const t={...currentUiState(),...e};writeCachedUiState(t),uiStateSaveTimer&&clearTimeout(uiStateSaveTimer),uiStateSaveTimer=setTimeout(async()=>{try{await fetch("/admin/ui-config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(t)})}catch(e){}},120)}function activeTabButton(e){return[...document.querySelectorAll(".tab")].find(t=>(t.getAttribute("onclick")||"").includes(`'${e}'`)||t.id===`${e}TabBtn`)||null}function hydrateUiState(e){if(uiStateHydrated)return;const t={...readCachedUiState(),...e||{}};activeTabName=normalizeTabName(t.active_tab||activeTabName),currentLogSource="audit"===t.current_log_source?"audit":"docker",showGlobalLogs="boolean"==typeof t.show_global_logs?t.show_global_logs:showGlobalLogs;const n=new Set(scopeItems().map(e=>e.id)),a=t.selected_scope||selectedScope||"GLOBAL";selectedScope="GLOBAL"===a?"GLOBAL":n.has(a)?a:singleScopeItems()[0]?.id||pairScopeItems()[0]?.id||"GLOBAL","GLOBAL"!==selectedScope&&(selectedInstance=selectedScope),uiStateHydrated=!0}setShowGlobalLogs=async function(e){showGlobalLogs=!!e,applyLogVisibility(),queueUiStateSave({show_global_logs:showGlobalLogs});try{await fetch("/admin/ui-config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({show_global_logs:showGlobalLogs})})}catch(e){setMsg("Could not save UI config: "+e)}},legacyGlobalPair=function(){return lastStatus&&lastStatus.legacy_global_instance||null};let powerCoolingBusyState={active:!1,message:""};const STATUS_POLL_MS=1e3;function syncPowerCoolingBusyState(){const e=findPanelByHeading("system","Power + Cooling");e&&(e.classList.toggle("instance-panel-busy",!!powerCoolingBusyState.active),[...e.querySelectorAll("button,input,select,textarea")].forEach(e=>{powerCoolingBusyState.active?e.setAttribute("disabled","disabled"):e.removeAttribute("disabled")}))}function setPowerCoolingBusy(e,t=""){powerCoolingBusyState={active:!!e,message:t||""},syncPowerCoolingBusyState()}async function withPowerCoolingBusy(e,t){setPowerCoolingBusy(!0,e);try{return await t()}finally{setPowerCoolingBusy(!1)}}function redrawMetricsSoon(){lastStatus&&(renderMetrics(lastStatus),requestAnimationFrame(()=>{lastStatus&&renderMetrics(lastStatus)}))}function syncInstancesBusyState(){const e=findPanelByHeading("system","Instances");if(!e)return;e.classList.toggle("instance-panel-busy",!!instanceBusyState.active),[...e.querySelectorAll("button,input,select,textarea")].forEach(e=>{instanceBusyState.active?e.setAttribute("disabled","disabled"):("gpuPairingEnabled"!==e.id||gpuCount()>=2)&&e.removeAttribute("disabled")});const t=$("pairingBusyNote");if(t){const e=instanceBusyState.message||(2===gpuCount()?"Keep disabled if you want Global to keep behaving like the shared two-GPU runtime.":"Enable this to manage arbitrary dual-GPU pair groups.");t.innerHTML=instanceBusyState.active?`<span class="spinner" aria-hidden="true"></span>${e}`:e}}function setInstancesBusy(e,t=""){instanceBusyState={active:!!e,message:t||""},syncInstancesBusyState()}async function saveGpuPairingSetting(e){setInstancesBusy(!0,"Applying GPU pairing setting...");try{const t=await fetch("/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"save_server_config",gpu_pairing_enabled:!!e})}),n=await t.json();if(!t.ok||!n.ok)throw new Error(n.error||"GPU pairing update failed");n.server_config&&(lastStatus||(lastStatus={}),lastStatus.server_config=n.server_config),await refreshStatus(),e||setScope("GLOBAL",!1)}catch(e){alert("GPU pairing update failed: "+e)}finally{setInstancesBusy(!1)}}function ensureAuditOverviewCard(){const e=$("system"),t=findPanelByHeading("logs","Audit Overview")||findPanelByHeading("audit","Audit Overview")||findPanelByHeading("system","Audit Overview");if(e&&t){const n=findPanelByHeading("system","Services");e.insertBefore(t,n&&n.nextSibling||e.children[1]||null)}}function ensurePairingToggle(){const e=findPanelByHeading("system","Instances");if(!e)return;let t=$("pairingToggleRow");if(!t){t=document.createElement("div"),t.id="pairingToggleRow",t.className="actions";const n=$("instanceTabs");n&&n.parentNode===e&&n.insertAdjacentElement("beforebegin",t)}const n=gpuCount(),a=pairingEnabled(),s=!!instanceBusyState.active,o=s?instanceBusyState.message||"Applying GPU pairing setting...":2===n?"Keep disabled if you want Global to keep behaving like the shared two-GPU runtime.":"Enable this to manage arbitrary dual-GPU pair groups.";t.innerHTML=`<label class="label"><input type="checkbox" id="gpuPairingEnabled" ${a?"checked":""} ${n<2||s?"disabled":""} onchange="saveGpuPairingSetting(this.checked)"> Enable GPU Pairing</label><span class="label busy-note" id="pairingBusyNote">${s?`<span class="spinner" aria-hidden="true"></span>${o}`:o}</span>`}ensureAccessPolicyCard=function(){const e=findPanelByHeading("system","Access Policy");e&&"1"!==e.dataset.v414Policy&&(e.dataset.v414Policy="1",e.innerHTML='<h2>Access Policy</h2><div class="actions" id="accessPolicyRow"><label class="label"><input type="checkbox" id="auditAllowAnonymousProxy" onchange="mirrorAuthToggles(this.checked)"> allow requests without per-user API keys</label><button class="btn blue" onclick="saveAuthSettings()">Save Policy</button></div><div class="value smallgap" style="margin-top:10px" id="auditPolicyText">-</div>')},ensureMachineButtons=function(){const e=findPanelByHeading("system","System");if(!e)return;const t=[...e.querySelectorAll(".actions")],n=[...e.querySelectorAll("button")].find(e=>(e.textContent||"").includes("Wake-on-LAN")),a=e.querySelector(".machine-row");n&&a&&!a.contains(n)&&a.prepend(n),t.forEach(e=>{e===a||e.querySelector("button")||e.remove()})},allPairChoices=function(){const e=gpuCount(),t=[];for(let n=0;n<e;n+=1)for(let a=n+1;a<e;a+=1)t.push([n,a]);return t},ensurePairManager=function(){const e=findPanelByHeading("system","Instances");if(!e)return;let t=$("pairManagerBar");if(!t){t=document.createElement("div"),t.id="pairManagerBar",t.className="actions";const n=$("instanceSummary");n&&n.parentNode===e&&n.insertAdjacentElement("afterend",t)}if(!pairingEnabled()||gpuCount()<2)return void(t.innerHTML="");const n=currentScopeInstance(!0),a=!!n&&"dual"===n.kind,s=new Set(pairScopeItems().map(e=>e.id)),o=allPairChoices().filter(([e,t])=>!s.has(canonicalPairId(e,t))).map(([e,t])=>`<button class="btn blue" onclick="createPairGroup(${e},${t})">Add Pair ${e}+${t}</button>`).join("");t.style.margin="8px 0 10px",t.innerHTML=`${o||""}<button class="btn purple" onclick="createPairGroup()">Custom Pair Group</button>${a?`<button class="btn red" onclick="deleteCurrentPairGroup()">Delete ${scopeLabel(n)}</button>`:""}`},ensureV414Layout=function(){ensureV413Layout(),ensureUsersUi(),ensureGroupUi(),ensureAccessPolicyCard(),ensureAuditOverviewCard(),ensureMachineButtons(),ensurePairingToggle(),ensurePairManager(),syncInstancesBusyState(),syncPowerCoolingBusyState()};const logCache=Object.create(null);let statusRefreshPromise=null,logConnectToken=0;function renderLogSourcePanel(){$("logSourceDocker")&&$("logSourceDocker").classList.toggle("active","docker"===currentLogSource),$("logSourceAudit")&&$("logSourceAudit").classList.toggle("active","audit"===currentLogSource),$("logsSourceSummary")&&($("logsSourceSummary").innerHTML="audit"!==currentLogSource?scopeIsGlobal()&&legacyGlobalDualScope()?"Docker logs selected. The shared live log viewer follows the active global dual runtime.":"Docker logs selected. The shared live log viewer follows the currently selected tracked instance.":"Audit logs selected. The shared live log viewer follows <code>/opt/club3090-control/audit.log</code>.")}function trimLogText(e){const t=String(e||"");return t.length>9e5?t.slice(-75e4):t}function logCacheEntry(e){return logCache[e]||(logCache[e]={text:"",loaded:!1}),logCache[e]}function renderCurrentLog(e){const t=$("log");if(!t)return;const n=logCacheEntry(e);t.value=n.loaded?n.text:"Connecting...\n",searchState.active?recalculateMatches(!0):$("autoscroll")&&$("autoscroll").checked&&(t.scrollTop=t.scrollHeight)}function replaceLogBuffer(e,t){const n=logCacheEntry(e);n.text=trimLogText(t||""),n.loaded=!0,e===currentLogSignature&&renderCurrentLog(e)}function appendLogChunk(e,t){if(!t)return;const n=logCacheEntry(e);n.text=trimLogText((n.text||"")+t),n.loaded=!0,e===currentLogSignature&&renderCurrentLog(e)}function syntheticLog(e){appendLog(`[admin-ui ${(new Date).toLocaleTimeString()}] ${e}`)}function adminResultText(e,t){let n="";if(e&&"object"==typeof e)try{n=JSON.stringify(e,null,2)}catch(e){n=""}return n||(n=String(t||"").trim()),n.length>5e3&&(n=n.slice(0,5e3)+"\n...<truncated>..."),n}function logStreamConfig(){if("audit"===currentLogSource)return{signature:"audit",url:"/admin/audit-stream?tail=4000"};const e=trackedLogRuntime(),t=e||dockerLogTarget(),n=e&&(e.id||e.instance_id)?e.id||e.instance_id:scopeIsGlobal()&&legacyGlobalDualScope()?"GLOBAL":t&&t.id;return{signature:`docker:${n||"primary"}`,url:"/admin/logs"+(n?`?instance=${encodeURIComponent(n)}`:"")}}currentLogHeading=function(){return"audit"===currentLogSource?"Audit Logs":"Docker Logs"},currentLogLabel=function(){if("audit"===currentLogSource)return"source: audit";const e=trackedLogRuntime();if(e)return"instance: "+(e.id||e.instance_id||"primary");if(scopeIsGlobal()&&legacyGlobalDualScope())return"instance: Global dual";const t=dockerLogTarget();return"instance: "+(t&&t.id||"primary")},clearLog=function(){const e=currentLogSignature||logStreamConfig().signature,t=logCacheEntry(e);t.text="",t.loaded=!0,renderCurrentLog(e)},appendLog=function(e){appendLogChunk(currentLogSignature||logStreamConfig().signature,`${e}\n`)},applyLogVisibility=function(){const e="logs"===activeTabName;document.body.classList.toggle("logs-tab",e),document.body.classList.remove("audit-tab");const t=document.querySelector(".logs.panel");t&&t.classList.toggle("log-card-hidden",!e&&!showGlobalLogs),$("logTitle")&&($("logTitle").textContent=currentLogHeading()),$("logInstanceLabel")&&($("logInstanceLabel").textContent=currentLogLabel()),renderLogSourcePanel(),renderLogTracker(),currentLogSignature&&renderCurrentLog(currentLogSignature)},connectLogs=function(e=!1){if(!("logs"===activeTabName||showGlobalLogs)&&!e)return;const t=logStreamConfig();if(!e&&logEs&&t.signature===currentLogSignature)return void renderCurrentLog(t.signature);currentLogSignature=t.signature,renderCurrentLog(t.signature);const n=++logConnectToken;if(logEs){try{logEs.close()}catch(e){}logEs=null}const a=new EventSource(t.url);logEs=a;const s=(e,n)=>{let a=null;try{a=JSON.parse(n||"{}")}catch(e){}const s=a&&"string"==typeof a.text?a.text:String(n||"").replaceAll("\\u0000","\n");"reset"===e?replaceLogBuffer(t.signature,s):appendLogChunk(t.signature,s)};a.addEventListener("reset",e=>{n===logConnectToken&&s("reset",e.data)}),a.addEventListener("append",e=>{n===logConnectToken&&s("append",e.data)}),a.onmessage=e=>{n===logConnectToken&&s("append",e.data)},a.onerror=()=>{}},setCurrentLogSource=function(e){currentLogSource="audit"===e?"audit":"docker",applyLogVisibility(),queueUiStateSave({current_log_source:currentLogSource}),connectLogs(!0)},setShowGlobalLogs=async function(e){showGlobalLogs=!!e,applyLogVisibility(),queueUiStateSave({show_global_logs:showGlobalLogs}),connectLogs(!1)},setScope=function(e,t=!0){const n=new Set(scopeItems().map(e=>e.id));selectedScope="GLOBAL"===e?"GLOBAL":n.has(e)?e:singleScopeItems()[0]?.id||pairScopeItems()[0]?.id||"GLOBAL","GLOBAL"!==selectedScope&&(selectedInstance=selectedScope),renderInstances(getInstanceList()),renderPresetScopeTabs(),updateScopedCards(),applyLogVisibility(),queueUiStateSave(),t&&connectLogs(!0)},post=async function(e,t,n=""){const a=n||`${e} ${JSON.stringify(t||{})}`;syntheticLog(`request sent: ${a}`);try{const n=await fetch(e,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(t||{})}),s=await n.text();let o=null;try{o=JSON.parse(s)}catch(e){}if(!n.ok||o&&!1===o.ok)throw new Error(o&&o.error||s||`${e} failed`);return syntheticLog(`request finished: ${a}`),appendLog(`----- admin result -----\n${adminResultText(o,s)}\n------------------------`),refreshStatus().catch(()=>{}),o||s}catch(e){throw syntheticLog(`request failed: ${a} | ${e.message||e}`),appendLog(`----- admin error -----\n${e.message||e}\n-----------------------`),refreshStatus().catch(()=>{}),e}};const baseRenderMetrics=renderMetrics;function renderEnhancedGpuMetricCharts(e){const t=$("gpuMetricCharts");if(!t||!e.gpus)return;const n=e.series||[],a=[{key:"util",suffix:"Util",label:"util %",color:"#72c7ff"},{key:"mem_pct",suffix:"Mem",label:"VRAM %",color:"#2fc46b"},{key:"temp",suffix:"Temp",label:"core temp °C",color:"#ffde59"},{key:"fan",suffix:"Fan",label:"fan %",color:"#a855f7"},{key:"power",suffix:"Power",label:"power W",color:"#ff5b6c"}];t.innerHTML=a.map(t=>e.gpus.map(e=>`<div class="chart"><canvas id="cGpu${e.index}${t.suffix}"></canvas></div>`).join("")).join(""),a.forEach(t=>e.gpus.forEach(e=>drawGpuSeries(`cGpu${e.index}${t.suffix}`,n,e.index,t.key,`GPU${e.index} ${t.label}`,t.color)))}async function wol(){const e=prompt("MAC address to wake (blank = configured default):","");if(null!==e)try{await post("/admin/wol",{mac:e})}catch(e){alert(e)}}async function machineAction(e){const t="reboot"===e?"RESTART":"SHUT DOWN";if(confirm(t+" machine now?")&&confirm("Final confirmation: "+t+" now."))try{await post("/admin/machine",{action:e})}catch(e){alert(e)}}function syncActiveTabDisplay(){document.querySelectorAll(".tabpane").forEach(e=>e.classList.remove("active")),document.querySelectorAll(".tab").forEach(e=>e.classList.remove("active"));const e=$(activeTabName);e&&e.classList.add("active");const t=activeTabButton(activeTabName);t&&t.classList.add("active"),applyLogVisibility()}function activateTab(e,t=!1){activeTabName=normalizeTabName(e),syncActiveTabDisplay(),("logs"===activeTabName||showGlobalLogs||t)&&connectLogs(!1),"metrics"===activeTabName&&(redrawMetricsSoon(),refreshStatus().catch(()=>{})),queueUiStateSave(),setTimeout(()=>{!searchState.active&&$("autoscroll").checked&&$("log")&&($("log").scrollTop=$("log").scrollHeight)},0)}function clearLegacyPollers(){const e=window.setInterval(()=>{},6e4);window.clearInterval(e);for(let t=1;t<e;t+=1)window.clearInterval(t)}function bootAdminUi(){clearLegacyPollers(),ensureV414Layout(),resetUserForm(!0),resetGroupForm(!0),selectedScope||(selectedScope=singleScopeItems()[0]?.id||pairScopeItems()[0]?.id||"GLOBAL"),setScope(selectedScope,!1),refreshStatus().catch(()=>{}),statusPollTimer&&clearInterval(statusPollTimer),statusPollTimer=setInterval(()=>{refreshStatus()},1e3),window.addEventListener("beforeunload",()=>{if(logEs)try{logEs.close()}catch(e){}})}renderMetrics=function(e){baseRenderMetrics(e),renderEnhancedGpuMetricCharts(e)},metricTab=function(e,t){document.querySelectorAll(".metricpane").forEach(e=>e.classList.remove("active")),document.querySelectorAll(".subtab").forEach(e=>e.classList.remove("active"));const n=$(t);n&&n.classList.add("active"),e&&e.target&&e.target.classList.add("active"),redrawMetricsSoon(),refreshStatus().catch(()=>{})},togglePowerOptimizations=async function(){const e=$("optToggle")&&$("optToggle").textContent.includes("Enable"),t=scopeIsGlobal()?"GLOBAL":currentScopeInstance(!1)&&currentScopeInstance(!1).id||null;try{await withPowerCoolingBusy(e?"Applying power optimizations...":"Disabling power optimizations...",()=>post("/admin/power",{action:e?"enable_optimizations":"disable_optimizations",instance_id:t},"/admin/power "+(e?"enable_optimizations":"disable_optimizations")))}catch(e){alert(e)}},toggleFansMax=async function(){const e=$("fanToggle")&&$("fanToggle").textContent.includes("Reset"),t=currentScopeInstance(!1),n=scopeIsGlobal()?"GLOBAL":t&&t.id||null;try{await withPowerCoolingBusy(e?"Resetting fans to default...":"Setting fans to max...",()=>post("/admin/power",{action:e?"fans_auto":"fans_max",instance_id:n},`/admin/power ${e?"fans_auto":"fans_max"} ${n||"host"}`))}catch(e){alert(e)}},tab=function(e,t){activateTab(t,!1)},refreshStatus=async function(){return statusRefreshPromise||(statusRefreshPromise=(async()=>{try{ensureV414Layout();const e=await fetch("/admin/status",{cache:"no-store"});if(!e.ok)throw new Error(`status fetch failed (${e.status})`);const t=await e.json(),n=(t.metrics,t.power||{});lastStatus=t,hydrateUiState(t.ui_config||{}),$("showGlobalLogs")&&($("showGlobalLogs").checked=!!showGlobalLogs),$("services").textContent=`vLLM=${t.vllm_service}, control=${t.control_service}, console=${t.console_service}`,renderOverviewStatus(t),renderGpuCards(t.gpus),$("optToggle").textContent=n.optimizations_enabled?"Disable Power Optimizations":"Enable Power Optimizations",$("fanToggle").textContent=n.fan_manual_override?"Reset Fans to Default":"Set Fans to Max",renderMetrics(t),renderPresetCatalog(t.presets),renderUsers(t.users||[]),renderGroups(t.groups||[]),renderAudit(t.server_config||{}),renderInstances(t.instances||[]),renderPresetScopeTabs(),updateScopedCards(),syncActiveTabDisplay(),("logs"===activeTabName||showGlobalLogs)&&connectLogs(!1),setMsg("")}catch(e){setMsg("Status error: "+e)}finally{statusRefreshPromise=null}})(),statusRefreshPromise)},bootAdminUi();</script></body></html>"""
class CommonMixin:
    def log_message(self, fmt, *args):
        return
    def read_json_body(self):
        n = int(self.headers.get("content-length","0") or "0")
        body = self.rfile.read(n) if n else b"{}"
        if not body:
            return {}
        return json.loads(body)
    def redirect(self, location, code=302):
        self.close_connection = True
        self.send_response(code)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
    def send_bytes(self, payload, content_type="application/octet-stream", code=200):
        self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj, indent=2).encode("utf-8"), "application/json", code)

class AdminHandler(CommonMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def require_auth(self):
        auth_header = self.headers.get("Authorization","")
        if check_basic_auth(auth_header):
            return True
        log_audit("admin_auth_denied", client=(self.client_address[0] if self.client_address else ""), path=self.path)
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="club-3090"')
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        return False
    def send_sse_event(self, event_name, payload):
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event_name}\ndata: {body}\n\n".encode("utf-8", errors="replace"))
        self.wfile.flush()
    def send_sse_comment(self, text="ping"):
        self.wfile.write(f": {text}\n\n".encode("utf-8", errors="replace"))
        self.wfile.flush()
    def do_GET(self):
        if not self.require_auth():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self.redirect("/admin")
            return
        if path == "/admin":
            html = HTML.replace("__SCRIPT_VERSION__", SCRIPT_VERSION).replace(":8008/admin", f":{ADMIN_PORT}/admin").replace(":8009", f":{PROXY_PORT}")
            self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/admin/status":
            self.send_json(get_status_snapshot())
            return
        if path == "/admin/logs":
            self.close_connection = False
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","keep-alive")
            self.end_headers()
            self.stream_logs(parsed)
            return
        if path == "/admin/audit-stream":
            params = parse_admin_query_params(parsed)
            self.close_connection = False
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","keep-alive")
            self.end_headers()
            self.stream_text_file(AUDIT_LOG_FILE, "no audit entries yet; waiting...", initial_tail_lines=parse_tail_lines_param(params, 250))
            return
        if path == "/admin/presets":
            self.send_json({"ok": True, "presets": preset_catalog()})
            return
        if path == "/admin/instances":
            self.send_json({"ok": True, "instances": instances_snapshot(), "single_gpu_modes": list(SINGLE_GPU_MODES), "dual_gpu_modes": list(DUAL_GPU_MODES), "running_dual_instances": running_dual_instance_snapshots()})
            return
        if path == "/admin/users":
            self.send_json({"ok": True, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
            return
        if path == "/admin/groups":
            self.send_json({"ok": True, "groups": list_groups_public(), "users": list_users_public(), "server_config": read_server_config()})
            return
        if path == "/admin/control-log":
            try:
                payload = subprocess.check_output(["tail","-n","300",CONTROL_LOG_FILE], text=True, stderr=subprocess.DEVNULL, timeout=3).encode("utf-8", errors="replace")
            except Exception:
                payload = b""
            self.send_bytes(payload, "text/plain; charset=utf-8")
            return
        if path == "/admin/audit-log":
            try:
                payload = subprocess.check_output(["tail","-n","300",AUDIT_LOG_FILE], text=True, stderr=subprocess.DEVNULL, timeout=3).encode("utf-8", errors="replace")
            except Exception:
                payload = b""
            self.send_bytes(payload, "text/plain; charset=utf-8")
            return
        self.send_error(404)
    def do_POST(self):
        if not self.require_auth():
            return
        path = urlsplit(self.path).path
        if path == "/admin/switch":
            try:
                data = self.read_json_body()
                instance_id = data.get("instance_id")
                mode = data.get("mode")
                if mode not in MODES:
                    raise ValueError("Invalid mode")
                if is_legacy_global_instance_id(instance_id):
                    if mode not in DUAL_GPU_MODES:
                        raise ValueError("Preset type does not match the selected instance scope")
                    rc, stop_msg = stop_legacy_global_instance()
                    result = run_switch(mode)
                    log_audit("admin_switch_mode_legacy_global", instance="GLOBAL", mode=mode, stop_rc=rc)
                    self.send_json({"ok": True, "instance": legacy_global_instance_snapshot(), "mode": mode, "output": (stop_msg + "\n" + result)[-12000:], "stopped_instances": ([{"id": "GLOBAL", "rc": rc, "output": stop_msg[-1200:]}] if stop_msg else []), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if instance_id:
                    target = get_instance(instance_id)
                    if not target:
                        raise ValueError(f"Unknown instance: {instance_id}")
                    valid_modes = DUAL_GPU_MODES if target.get("kind") == "dual" else SINGLE_GPU_MODES
                    if mode not in valid_modes:
                        raise ValueError("Preset type does not match the selected instance scope")
                    stopped = stop_overlapping_instances(target.get("gpu_indices") or [target.get("gpu_index")])
                    updated = update_instance(instance_id, mode=mode, enabled=True)
                    result = start_instance(updated["id"], wait=True)
                    log_audit("admin_switch_mode", instance=updated["id"], mode=mode, stopped_instances=[row["id"] for row in stopped])
                    self.send_json({"ok": True, "instance": instance_snapshot(updated), "mode": mode, "output": result.get("output", ""), "stopped_instances": stopped, "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                else:
                    if detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled():
                        rc, stop_msg = stop_vllm_container("legacy_dual_switch")
                        result = run_switch(mode)
                        log_audit("admin_switch_mode_legacy_global", instance="legacy", mode=mode, stop_rc=rc)
                        self.send_json({"ok": True, "instance": None, "mode": mode, "output": (stop_msg + "\n" + result)[-12000:], "stopped_instances": ([{"id": "legacy", "rc": rc, "output": stop_msg[-1200:]}] if stop_msg else []), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                        return
                    pairs = [inst for inst in read_instances_config() if inst.get("kind") == "dual"]
                    if len(pairs) != 1:
                        raise ValueError("Select a specific dual pair scope before applying a dual preset")
                    target = pairs[0]
                    stopped = stop_overlapping_instances(target.get("gpu_indices") or [target.get("gpu_index")])
                    updated = update_instance(target["id"], mode=mode, enabled=True)
                    result = start_instance(updated["id"], wait=True)
                    log_audit("admin_switch_mode_pair_default", instance=updated["id"], mode=mode, stopped_instances=[row["id"] for row in stopped])
                    self.send_json({"ok": True, "instance": instance_snapshot(updated), "mode": mode, "output": result.get("output", ""), "stopped_instances": stopped, "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/power":
            try:
                data = self.read_json_body()
                action = data.get("action")
                instance_id = data.get("instance_id")
                log_control(f"POWER action requested action={action} instance={instance_id}")
                if action == "active":
                    out = {"cpu": apply_cpu_active_power(), "gpu": apply_gpu_active_power()}
                elif action == "idle_clocks":
                    out = {"cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "stop_container":
                    if is_legacy_global_instance_id(instance_id):
                        rc, msg = stop_legacy_global_instance()
                    else:
                        rc, msg = stop_vllm_container("manual_admin", instance_id=instance_id)
                    out = {"container_stop_rc": rc, "container_stop_output": msg, "cpu": apply_cpu_idle_power(), "gpu": apply_gpu_idle_power()}
                elif action == "start_instance":
                    out = start_legacy_global_instance(wait=True) if is_legacy_global_instance_id(instance_id) else start_instance(instance_id, wait=True)
                elif action == "restart_instance":
                    if is_legacy_global_instance_id(instance_id):
                        stop_legacy_global_instance()
                        out = start_legacy_global_instance(wait=True)
                    else:
                        stop_vllm_container("manual_restart", instance_id=instance_id)
                        out = start_instance(instance_id, wait=True)
                elif action == "toggle_enabled":
                    enabled = bool(data.get("enabled"))
                    if is_legacy_global_instance_id(instance_id) or (not instance_id and detect_gpu_count_runtime() == 2 and not gpu_pairing_enabled(gpu_count=2)):
                        instance_id = "GLOBAL"
                        out = {"instance": set_legacy_global_enabled(enabled)}
                    else:
                        inst = update_instance(instance_id, enabled=enabled)
                        out = {"instance": instance_snapshot(inst)}
                elif action == "disable_optimizations":
                    out = set_power_optimizations(False, instance_id=instance_id)
                elif action == "enable_optimizations":
                    out = set_power_optimizations(True, instance_id=instance_id)
                elif action == "fans_max":
                    out = {"fans": set_fan_max_toggle(True, instance_id=instance_id)}
                elif action == "fans_auto":
                    out = {"fans": set_fan_max_toggle(False, instance_id=instance_id)}
                else:
                    raise ValueError("Invalid power action")
                log_audit("admin_power_action", action=action, instance=instance_id)
                self.send_json({"ok": True, "action": action, "result": out, "power": power_status()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/profile":
            try:
                data = self.read_json_body()
                profile_name = data.get("profile")
                log_control(f"PROFILE request received name={profile_name}")
                out = apply_performance_profile(profile_name)
                log_audit("admin_profile", profile=profile_name)
                self.send_json({"ok": True, "profile": profile_name, "result": out, "power": power_status()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/wol":
            try:
                data = self.read_json_body()
                out = wake_on_lan(data.get("mac") or None, data.get("broadcast") or None)
                log_audit("admin_wol", mac=data.get("mac") or "", broadcast=data.get("broadcast") or "")
                self.send_json({"ok": True, "result": out})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/presets":
            try:
                data = self.read_json_body()
                action = data.get("action")
                if action == "save":
                    catalog = save_custom_preset(data.get("name"), data.get("preset") or {})
                    log_audit("admin_preset_save", name=data.get("name"))
                elif action == "delete":
                    catalog = delete_custom_preset(data.get("name"))
                    log_audit("admin_preset_delete", name=data.get("name"))
                else:
                    raise ValueError("Invalid preset action")
                self.send_json({"ok": True, "presets": catalog})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/ui-config":
            try:
                data = self.read_json_body()
                cfg = write_ui_config(data)
                log_audit("admin_ui_config", keys=sorted(list((data or {}).keys())))
                self.send_json({"ok": True, "ui_config": cfg})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/instances":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip()
                if action == "save_pair":
                    instance = save_pair_instance(data.get("gpu_indices") or [], mode=data.get("mode"), enabled=data.get("enabled"))
                    log_audit("admin_pair_saved", instance=instance["id"], gpu_indices=instance.get("gpu_indices") or [], mode=instance.get("mode"))
                    self.send_json({"ok": True, "instance": instance_snapshot(instance), "instances": instances_snapshot(), "running_dual_instances": running_dual_instance_snapshots()})
                    return
                if action == "delete_pair":
                    instances = delete_pair_instance(data.get("instance_id"))
                    log_audit("admin_pair_deleted", instance=str(data.get("instance_id") or "").strip().upper())
                    self.send_json({"ok": True, "instances": instances, "running_dual_instances": running_dual_instance_snapshots()})
                    return
                raise ValueError("Invalid instances action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/users":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip()
                if action == "save":
                    user, api_key = save_user_record(data.get("user") or {})
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
                    return
                if action == "delete":
                    users = delete_user_record(data.get("name"))
                    self.send_json({"ok": True, "users": users, "groups": list_groups_public(), "server_config": read_server_config()})
                    return
                if action == "reset_key":
                    api_key, user = issue_api_key_for_user(safe_user_name(data.get("name")))
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
                    return
                if action == "show_key":
                    api_key, user = show_api_key_for_user(safe_user_name(data.get("name")))
                    self.send_json({"ok": True, "user": user, "api_key": api_key})
                    return
                if action == "save_server_config":
                    cfg_data = {}
                    if "allow_proxy_without_api_key" in data:
                        cfg_data["allow_proxy_without_api_key"] = bool(data.get("allow_proxy_without_api_key", True))
                    if "gpu_pairing_enabled" in data:
                        cfg_data["gpu_pairing_enabled"] = bool(data.get("gpu_pairing_enabled"))
                    cfg = write_server_config(cfg_data)
                    read_instances_config()
                    log_audit("admin_server_config", allow_proxy_without_api_key=cfg.get("allow_proxy_without_api_key", True), gpu_pairing_enabled=cfg.get("gpu_pairing_enabled"))
                    self.send_json({"ok": True, "server_config": cfg, "users": list_users_public(), "groups": list_groups_public()})
                    return
                raise ValueError("Invalid users action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/groups":
            try:
                data = self.read_json_body()
                action = str(data.get("action") or "").strip()
                if action == "save":
                    group = save_group_record(data.get("group") or {})
                    self.send_json({"ok": True, "group": group, "groups": list_groups_public(), "users": list_users_public(), "server_config": read_server_config()})
                    return
                if action == "delete":
                    groups = delete_group_record(data.get("name"))
                    self.send_json({"ok": True, "groups": groups, "users": list_users_public(), "server_config": read_server_config()})
                    return
                raise ValueError("Invalid groups action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/admin/machine":
            try:
                data = self.read_json_body()
                action = data.get("action")
                if action == "reboot":
                    log_audit("admin_machine", action="reboot")
                    self.send_json({"ok": True, "action": "reboot", "message": "Reboot command accepted"})
                    threading.Thread(target=lambda: (time.sleep(1), subprocess.run(["systemctl", "reboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)), daemon=True).start()
                    return
                if action == "shutdown":
                    log_audit("admin_machine", action="shutdown")
                    self.send_json({"ok": True, "action": "shutdown", "message": "Shutdown command accepted"})
                    threading.Thread(target=lambda: (time.sleep(1), subprocess.run(["systemctl", "poweroff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)), daemon=True).start()
                    return
                raise ValueError("Invalid machine action")
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return
        self.send_error(404)
    def stream_logs(self, parsed):
        params = parse_admin_query_params(parsed)
        requested = str(params.get("instance") or "").strip().upper()
        last_container = ""
        client_generation = -1
        client_seq = 0
        waiting_sent = False
        while True:
            instance, container = resolve_runtime_log_container(requested)
            if not container:
                try:
                    if not waiting_sent:
                        text = f"\n[log stream] {last_container} is no longer running; waiting for the next runtime container...\n" if last_container else "no running club-3090 runtime container found; waiting...\n"
                        self.send_sse_event("append", {"text": text})
                        waiting_sent = True
                        last_container = ""
                    else:
                        self.send_sse_comment()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return
                time.sleep(2)
                continue
            waiting_sent = False
            watcher = get_runtime_log_watcher(container)
            if watcher is None:
                time.sleep(1)
                continue
            if container != last_container:
                last_container = container
                client_generation = -1
                client_seq = 0
            try:
                watcher.wait_for_change(client_generation, client_seq, timeout=15)
                snapshot = watcher.snapshot()
                if snapshot["generation"] != client_generation:
                    self.send_sse_event("reset", {"text": snapshot["text"]})
                    client_generation = snapshot["generation"]
                    client_seq = snapshot["seq"]
                    continue
                update = watcher.collect_updates_since(client_generation, client_seq)
                if update["reset"]:
                    self.send_sse_event("reset", {"text": update["text"]})
                    client_generation = update["generation"]
                    client_seq = update["seq"]
                elif update["text"]:
                    self.send_sse_event("append", {"text": update["text"]})
                    client_seq = update["seq"]
                else:
                    self.send_sse_comment()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
    def stream_text_file(self, path, empty_message="waiting...", initial_tail_lines=250):
        sent_reset = False
        offset = 0
        idle_since = time.time()
        while True:
            try:
                if not os.path.exists(path):
                    if not sent_reset:
                        self.send_sse_event("reset", {"text": str(empty_message or "waiting...").rstrip("\n") + "\n"})
                        sent_reset = True
                    else:
                        self.send_sse_comment()
                    time.sleep(2)
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    if offset <= 0:
                        if int(initial_tail_lines) > 0:
                            lines = collections.deque(f, maxlen=int(initial_tail_lines))
                            text = "".join(lines)
                        else:
                            text = ""
                            f.seek(0, os.SEEK_END)
                        self.send_sse_event("reset", {"text": text or (str(empty_message or "waiting...").rstrip("\n") + "\n")})
                        offset = f.tell()
                        sent_reset = True
                        initial_tail_lines = 0
                        idle_since = time.time()
                    else:
                        try:
                            size_now = os.path.getsize(path)
                        except Exception:
                            size_now = offset
                        if size_now < offset:
                            offset = 0
                            sent_reset = False
                            continue
                        f.seek(offset)
                        chunk = f.read()
                        if chunk:
                            self.send_sse_event("append", {"text": chunk})
                            offset = f.tell()
                            idle_since = time.time()
                        elif time.time() - idle_since >= 15:
                            self.send_sse_comment()
                            idle_since = time.time()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            time.sleep(1)


class LocalApiHandler(CommonMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def require_local_access(self):
        client_ip = self.client_address[0] if self.client_address else ""
        if client_ip not in ("127.0.0.1", "::1"):
            log_audit("local_api_denied", reason="non_loopback", client=client_ip, path=self.path)
            self.send_json({"ok": False, "error": "Local API is loopback-only"}, 403)
            return False
        if not local_api_token_ok(self.headers.get("X-Club3090-Local-Token", "")):
            log_audit("local_api_denied", reason="invalid_token", client=client_ip, path=self.path)
            self.send_json({"ok": False, "error": "Missing or invalid local API token"}, 401)
            return False
        return True
    def do_GET(self):
        if not self.require_local_access():
            return
        path = urlsplit(self.path).path
        if path == "/users":
            self.send_json({"ok": True, "users": list_users_public(), "groups": list_groups_public(), "server_config": read_server_config()})
            return
        if path == "/groups":
            self.send_json({"ok": True, "groups": list_groups_public(), "users": list_users_public(), "server_config": read_server_config()})
            return
        if path == "/server-config":
            self.send_json({"ok": True, "server_config": read_server_config()})
            return
        self.send_error(404)
    def do_POST(self):
        if not self.require_local_access():
            return
        path = urlsplit(self.path).path
        try:
            data = self.read_json_body()
            if path == "/users":
                action = str(data.get("action") or "").strip()
                if action == "save":
                    user, api_key = save_user_record(data.get("user") or {})
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public()})
                    return
                if action == "delete":
                    users = delete_user_record(data.get("name"))
                    self.send_json({"ok": True, "users": users, "groups": list_groups_public()})
                    return
                if action == "reset_key":
                    api_key, user = issue_api_key_for_user(safe_user_name(data.get("name")))
                    self.send_json({"ok": True, "user": user, "api_key": api_key, "users": list_users_public(), "groups": list_groups_public()})
                    return
                raise ValueError("Invalid users action")
            if path == "/groups":
                action = str(data.get("action") or "").strip()
                if action == "save":
                    group = save_group_record(data.get("group") or {})
                    self.send_json({"ok": True, "group": group, "groups": list_groups_public(), "users": list_users_public()})
                    return
                if action == "delete":
                    groups = delete_group_record(data.get("name"))
                    self.send_json({"ok": True, "groups": groups, "users": list_users_public()})
                    return
                raise ValueError("Invalid groups action")
            if path == "/server-config":
                cfg = write_server_config(data or {})
                self.send_json({"ok": True, "server_config": cfg})
                return
            raise ValueError("Unknown local API path")
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

class ProxyHandler(CommonMixin, BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        instance_id, stripped = parse_instance_path(self.path)
        upstream_path, preset_name, cap = parse_preset_path(stripped)
        self.forward(None, upstream_path, preset_name, cap, instance_id=instance_id)
    def do_POST(self):
        n = int(self.headers.get("content-length","0") or "0")
        body = self.rfile.read(n) if n else b""
        instance_id, stripped = parse_instance_path(self.path)
        upstream_path, preset_name, cap = parse_preset_path(stripped)
        if preset_name and (upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")):
            body = apply_preset(body, preset_name, cap)
        self.forward(body, upstream_path, preset_name, cap, instance_id=instance_id)
    def forward(self, body, upstream_path, preset_name, cap, instance_id=None):
        start = time.time()
        status = None
        response_usage = {"tokens": 0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
        target = get_instance(instance_id) if instance_id else primary_instance()
        target_id = target["id"] if target else "legacy"
        target_metrics_key = str(target_id or "").strip().upper()
        request_usage = extract_request_usage(body) if body is not None and is_quota_counted_path(upstream_path) else {}
        auth_result = authorize_proxy_request(self.headers, instance_id, upstream_path, request_usage=request_usage)
        if auth_result[0] is False:
            _, code, payload = auth_result
            self.send_json(payload, code)
            return
        auth_context = auth_result[1]
        with metrics_lock:
            metrics["total_requests"] += 1
            metrics["active_requests"] += 1
            metrics["last_preset"] = preset_name or "raw"
            metrics["last_path"] = self.path
            target_request_metrics.setdefault(target_metrics_key, default_target_request_metrics())
        needs_model = upstream_path.startswith("/v1/models") or (body is not None and (upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions")))
        if needs_model:
            with metrics_lock:
                metrics["queued_requests"] += 1
                request_queue.append({"time": time.strftime("%H:%M:%S"), "path": self.path, "preset": preset_name or "raw", "instance": target_id})
            ensure_vllm_running_for_request(target["id"] if target else None)
            with metrics_lock:
                metrics["queued_requests"] = max(0, metrics["queued_requests"] - 1)
        url = f"http://127.0.0.1:{instance_runtime_port(target) if target else active_port()}" + upstream_path
        headers = {k:v for k,v in self.headers.items() if k.lower() not in HOP_HEADERS}
        for secret_header in ("Authorization", "authorization", "X-API-Key", "x-api-key", "api-key"):
            headers.pop(secret_header, None)
        if body is not None:
            headers["Content-Type"] = headers.get("Content-Type", "application/json")
        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=None) as r:
                status = r.status
                self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() not in HOP_HEADERS:
                        self.send_header(k,v)
                self.send_header("X-Club3090-Instance", target_id)
                self.send_header("Connection","close")
                self.end_headers()
                if "text/event-stream" in r.headers.get("Content-Type","").lower():
                    with metrics_lock:
                        metrics["streaming_requests"] += 1
                first_chunk_at = None
                total_bytes = bytearray()
                while True:
                    chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                    if not chunk:
                        break
                    if first_chunk_at is None:
                        first_chunk_at = time.time()
                    if len(total_bytes) < 2000000:
                        total_bytes.extend(chunk)
                    self.wfile.write(chunk)
                    self.wfile.flush()
                if first_chunk_at is not None:
                    toks = estimate_tokens_from_stream_bytes(bytes(total_bytes))
                    response_usage["output_tokens"] = max(int(response_usage.get("output_tokens") or 0), int(toks or 0))
                    response_usage["tokens"] = max(int(response_usage.get("tokens") or 0), int(toks or 0))
                    ttft = round(first_chunk_at - start, 3)
                    gen_time = max(0.001, time.time() - first_chunk_at)
                    with metrics_lock:
                        metrics["last_ttft_s"] = ttft
                        metrics["last_estimated_tokens"] = toks
                        metrics["last_tokens_per_second"] = round(toks / gen_time, 2) if toks else None
                        target_row = dict(target_request_metrics.get(target_metrics_key) or default_target_request_metrics())
                        target_row["last_ttft_s"] = ttft
                        target_row["last_estimated_tokens"] = toks
                        target_row["last_tokens_per_second"] = round(toks / gen_time, 2) if toks else None
                        target_request_metrics[target_metrics_key] = target_row
                parsed_usage = extract_response_usage(bytes(total_bytes))
                for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                    response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_usage.get(key) or 0))
        except urllib.error.HTTPError as e:
            status = e.code
            payload = e.read()
            parsed_usage = extract_response_usage(payload)
            for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_usage.get(key) or 0))
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type","text/plain"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection","close")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            status = 502
            # Best-effort self-healing failover for stopped/crashed containers.
            # Only attempt for model discovery/completion paths, and only once.
            if upstream_path.startswith("/v1/models") or upstream_path.startswith("/v1/chat/completions") or upstream_path.startswith("/v1/completions"):
                try:
                    with metrics_lock:
                        metrics["failovers"] += 1
                    log_control(f"PROXY failover attempt instance={target_id} mode={(target['mode'] if target else active_mode())} error={e}")
                    if target:
                        start_instance(target["id"], wait=True)
                    else:
                        run_switch(active_mode(), allow_fallback=False)
                    retry_url = f"http://127.0.0.1:{instance_runtime_port(target) if target else active_port()}" + upstream_path
                    retry_req = urllib.request.Request(retry_url, data=body, headers=headers, method=self.command)
                    with urllib.request.urlopen(retry_req, timeout=None) as r2:
                        status = r2.status
                        self.send_response(r2.status)
                        for k,v in r2.headers.items():
                            if k.lower() not in HOP_HEADERS:
                                self.send_header(k,v)
                        self.send_header("X-Club3090-Instance", target_id)
                        self.send_header("Connection","close")
                        self.end_headers()
                        retry_bytes = bytearray()
                        while True:
                            chunk = r2.read1(8192) if hasattr(r2, "read1") else r2.read(8192)
                            if not chunk:
                                break
                            if len(retry_bytes) < 2000000:
                                retry_bytes.extend(chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        parsed_retry_usage = extract_response_usage(bytes(retry_bytes))
                        for key in ("tokens", "input_tokens", "output_tokens", "tool_calls"):
                            response_usage[key] = max(int(response_usage.get(key) or 0), int(parsed_retry_usage.get(key) or 0))
                        if int(response_usage.get("output_tokens") or 0) == 0:
                            retry_toks = estimate_tokens_from_stream_bytes(bytes(retry_bytes))
                            response_usage["output_tokens"] = max(int(response_usage.get("output_tokens") or 0), int(retry_toks or 0))
                            response_usage["tokens"] = max(int(response_usage.get("tokens") or 0), int(retry_toks or 0))
                        return
                except Exception as failover_error:
                    log_control(f"PROXY failover failed: {failover_error}")
            self.send_json({"error": str(e), "active_mode": active_mode(), "active_port": active_port()}, 502)
        finally:
            latency = round(time.time() - start, 3)
            prompt_tokens = max(int(request_usage.get("input_tokens") or 0), int(response_usage.get("input_tokens") or 0))
            output_tokens = max(int(response_usage.get("output_tokens") or 0), max(0, int(response_usage.get("tokens") or 0) - int(prompt_tokens)))
            total_tokens = max(int(response_usage.get("tokens") or 0), int(prompt_tokens) + int(output_tokens))
            tool_calls = int(response_usage.get("tool_calls") or 0)
            with metrics_lock:
                metrics["active_requests"] = max(0, metrics["active_requests"] - 1)
                metrics["completed_requests"] += 1
                if status is None or int(status) >= 400:
                    metrics["failed_requests"] += 1
                metrics["last_latency_s"] = latency
                metrics["last_status"] = status
                recent_requests.appendleft({"time":time.strftime("%H:%M:%S"),"status":status,"latency_s":latency,"preset":preset_name or "raw","path":self.path,"upstream":upstream_path,"instance":target_id,"user":auth_context.get("user_name") or "anonymous"})
                target_row = dict(target_request_metrics.get(target_metrics_key) or default_target_request_metrics())
                target_row["last_status"] = status
                target_row["last_latency_s"] = latency
                target_row["last_input_tokens"] = prompt_tokens
                target_row["last_output_tokens"] = output_tokens
                target_row["last_total_tokens"] = total_tokens
                target_row["last_tool_calls"] = tool_calls
                target_row["last_preset"] = preset_name or "raw"
                target_row["last_path"] = self.path
                target_row["last_request_at"] = int(time.time())
                target_request_metrics[target_metrics_key] = target_row
            record_user_usage(auth_context.get("user_name"), auth_context.get("count_request", False), status, request_usage, response_usage, latency)
            log_control(f"REQ user={(auth_context.get('user_name') or 'anonymous')} instance={target_id} status={status} latency={latency}s preset={preset_name or 'raw'} path={self.path} upstream={upstream_path} input_tokens={prompt_tokens} output_tokens={output_tokens} total_tokens={total_tokens} tool_calls={tool_calls}")

def build_server(port, handler, bind="0.0.0.0"):
    server = ThreadingHTTPServer((bind, port), handler)
    server.daemon_threads = True
    return server

def serve(server, label="server"):
    sock = None
    try:
        sock = server.socket.getsockname()
    except Exception:
        sock = ("?", "?")
    log_control(f"{label} listening on {sock[0]}:{sock[1]}")
    server.serve_forever()

def startup_power_primer():
    try:
        apply_cpu_active_power()
    except Exception as e:
        log_control(f"STARTUP cpu power primer error: {e}")
    try:
        apply_gpu_active_power(skip_fans=True)
    except Exception as e:
        log_control(f"STARTUP gpu power primer error: {e}")

def main():
    os.makedirs(CONTROL_DIR, exist_ok=True)
    os.makedirs(INSTANCES_DIR, exist_ok=True)
    write_server_config(read_server_config())
    ensure_local_api_token()
    # Hard fail early if an update somehow produced an incomplete control script.
    # This specifically guards the proxy/autostart path that depends on port_open().
    if not callable(globals().get("port_open")):
        raise RuntimeError("internal install error: port_open() is not defined")
    if len(sys.argv) > 1 and sys.argv[1] == "--boot-enabled-instances":
        boot_enabled_instances()
        return
    if DEFAULT_MODE in MODES and read_active_mode_file() is None:
        write_active_mode(DEFAULT_MODE)
    read_instances_config()
    log_control("control service starting")
    try:
        build_series_point()
    except Exception as e:
        log_control(f"initial metrics snapshot error: {e}")
    try:
        refresh_status_snapshot()
    except Exception as e:
        log_control(f"initial status snapshot error: {e}")
    threading.Thread(target=idle_watchdog, daemon=True).start()
    threading.Thread(target=metrics_collector, daemon=True).start()
    threading.Thread(target=status_snapshot_collector, daemon=True).start()
    cfg = read_server_config()
    admin_server = build_server(ADMIN_BIND_PORT, AdminHandler, ADMIN_BIND_HOST)
    if cfg.get("local_api_enabled", False):
        local_api_port = int(cfg.get("local_api_port", LOCAL_API_PORT))
        local_api_server = build_server(local_api_port, LocalApiHandler, "127.0.0.1")
        threading.Thread(target=serve, args=(local_api_server, "local-api"), daemon=True).start()
    proxy_server = build_server(PROXY_BIND_PORT, ProxyHandler, PROXY_BIND_HOST)
    threading.Thread(target=serve, args=(proxy_server, "proxy"), daemon=True).start()
    threading.Thread(target=startup_power_primer, daemon=True).start()
    serve(admin_server, "admin")

if __name__ == "__main__":
    main()
PYCTRL

"${SUDO[@]}" chmod +x "${CONTROL_PY}"
log_done "Control backend written"

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
# Structural validation: catch missing helper functions before replacing a working service.
"${SUDO[@]}" "${PYTHON_BIN}" - "${CONTROL_PY}" <<'PYVERIFY'
import ast, sys
path = sys.argv[1]
tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
required = {"port_open","wait_for_port","cleanup_vllm_containers","run_switch","detected_mode","active_port","ensure_vllm_running_for_request","apply_preset","parse_preset_path","set_gpu_fans","set_power_optimizations","set_fan_max_toggle","apply_fan_curve_once","ensure_headless_x_running","run_nvidia_settings","metrics_collector","wake_on_lan","apply_performance_profile","system_stats","read_ui_config","write_ui_config","read_custom_presets","write_custom_presets","get_all_presets","preset_catalog","save_custom_preset","delete_custom_preset","serve","main"}
missing = sorted(required - funcs)
if missing:
    raise SystemExit("control.py missing required functions: " + ", ".join(missing))
PYVERIFY
# Guardrail: the control service must not make vLLM /health requests.
if grep -q 'urlopen.*health\|/health.*urlopen' "${CONTROL_PY}"; then
  echo "ERROR: control.py still contains HTTP /health polling" >&2
  exit 1
fi
log_done "Generated files validated"

write_control_units() {
  "${SUDO[@]}" tee /etc/systemd/system/club3090-control.service >/dev/null <<UNIT
[Unit]
Description=club-3090 proxy and admin control panel
ConditionKernelCommandLine=club3090.server=1
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

  "${SUDO[@]}" tee /etc/systemd/system/club3090-headless-x.service >/dev/null <<UNIT
[Unit]
Description=club-3090 private headless Xorg for NVIDIA fan control
ConditionKernelCommandLine=club3090.server=1
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
  "${SUDO[@]}" tee "${CADDYFILE_PATH}" >/dev/null <<CADDY
{
    auto_https disable_redirects
    admin off
}

https://:${ADMIN_PORT} {
    tls ${TLS_CERT_FILE} ${TLS_KEY_FILE}
    reverse_proxy 127.0.0.1:${CONTROL_ADMIN_BIND_PORT}
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
ConditionKernelCommandLine=club3090.server=1
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
  if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" != "true" ]]; then
    "${SUDO[@]}" systemctl disable --now club3090-caddy.service 2>/dev/null || true
    "${SUDO[@]}" rm -f /etc/systemd/system/club3090-caddy.service "${CADDYFILE_PATH}" >/dev/null 2>&1 || true
    return 0
  fi
  ensure_https_certificate
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

start_control_plane_services_if_booted() {
  if ! grep -q 'club3090.server=1' /proc/cmdline; then
    return 0
  fi
  start_unit_nonblocking club3090-control.service
  if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
    start_unit_nonblocking club3090-caddy.service
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

if [[ "${ACTION}" == "install" ]]; then
  log_step "Writing and enabling systemd units for a fresh install"
  write_vllm_unit
  write_control_units
  configure_https_frontend
  cleanup_legacy_fan_test_artifacts
  log_step "Reloading systemd manager configuration"
  "${SUDO[@]}" systemctl daemon-reload
  log_step "Enabling managed club-3090 services"
  enable_managed_units
  log_step "Configuring networking and frontend exposure"
  configure_networking_and_frontend
  log_step "Starting control-plane services when server boot mode is active"
  start_control_plane_services_if_booted
  log_done "Install actions completed"

  echo
  echo "Installed club-3090 server control services."
  echo "They start unattended before login, but only when booted with kernel arg: club3090.server=1"
else
  log_step "Refreshing systemd units and managed services for update"
  # Update the vLLM unit too so the next reboot uses the last selected mode.
  # Do not restart it here; that would interrupt a running model session.
  write_vllm_unit
  write_control_units
  configure_https_frontend
  cleanup_legacy_fan_test_artifacts
  log_step "Reloading systemd manager configuration"
  "${SUDO[@]}" systemctl daemon-reload
  log_step "Re-enabling managed club-3090 services"
  enable_managed_units
  log_step "Refreshing networking and frontend exposure"
  configure_networking_and_frontend
  log_step "Starting control-plane services if the server boot flag is active"
  start_control_plane_services_if_booted
  log_done "Update actions completed"
  echo
  echo "Updated club-3090 multi-instance control plane, proxy, metrics UI, console log follower, and boot unit."
  echo "Running Docker instances were left unchanged; next server boot will restore enabled entries from ${CONTROL_DIR}/instances.json."
fi

URL_SCHEME="http"
if [[ "${ONLINE_TLS_EFFECTIVE_ENABLED}" == "true" ]]; then
  URL_SCHEME="https"
fi
echo "Admin UI:  ${URL_SCHEME}://SERVER:${ADMIN_PORT}/admin"
echo "Proxy API: ${URL_SCHEME}://SERVER:${PROXY_PORT}/v1/chat/completions"
echo "OpenAI base URL: ${URL_SCHEME}://SERVER:${PROXY_PORT}/v1"
echo "Per-GPU proxy: ${URL_SCHEME}://SERVER:${PROXY_PORT}/GPU0/v1/chat/completions"
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
echo "Preset path styles supported: ${URL_SCHEME}://SERVER:${PROXY_PORT}/v1/<preset>/chat/completions, ${URL_SCHEME}://SERVER:${PROXY_PORT}/<preset>/v1/chat/completions, and per-GPU prefixes like ${URL_SCHEME}://SERVER:${PROXY_PORT}/GPU0/v1/<preset>/chat/completions"
