#!/usr/bin/env bash
set -euo pipefail

UNITS=(
  club3090-control.service
  club3090-benchmarks.service
  club3090-updater.service
  club3090-headless-x.service
  club3090-console-log.service
  club3090-vllm.service
  club3090-caddy.service
  club3090-cert-refresh.service
  club3090-cert-refresh.timer
)
UNIT_DIR="${CLUB3090_SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
ENV_FILE="${CLUB3090_SERVER_ENV_FILE:-/etc/club3090-server.env}"

progress() { printf '[uninstall] %s\n' "$*" >&2; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
progress "Checking systemctl and privilege requirements"
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required to remove registered services"
if [[ "${EUID}" -eq 0 ]]; then SUDO=(); else
  command -v sudo >/dev/null 2>&1 || fail "sudo is required; run sudo ./uninstall.sh"
  SUDO=(sudo)
fi

progress "Stopping and disabling Club-3090 Server services"
for unit in "${UNITS[@]}"; do
  "${SUDO[@]}" systemctl disable --now "${unit}" || true
  "${SUDO[@]}" rm -f "${UNIT_DIR}/${unit}"
done
progress "Removing service configuration ${ENV_FILE}"
"${SUDO[@]}" rm -f "${ENV_FILE}"
progress "Reloading systemd unit definitions"
"${SUDO[@]}" systemctl daemon-reload

progress "Uninstallation complete"
printf 'Removed Club-3090 Server service registrations and %s.\n' "${ENV_FILE}"
printf 'Kept the repository checkout, upstream checkout, runtime data, model files, and installed system packages unchanged.\n'
