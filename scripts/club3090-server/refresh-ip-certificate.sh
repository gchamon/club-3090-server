#!/usr/bin/env bash
set -euo pipefail

CONTROL_DIR="${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}"
WEBROOT="${CLUB3090_ACME_WEBROOT:-${CONTROL_DIR}/acme}"
HOST_FILE="${CLUB3090_HTTPS_HOST_FILE:-${CONTROL_DIR}/https_host}"
LOG_FILE="${CONTROL_DIR}/control.log"

if [[ ! -r "${HOST_FILE}" ]]; then
  printf '[%s] certificate refresh skipped: no configured HTTPS host\n' "$(date '+%Y-%m-%d %H:%M:%S')" >>"${LOG_FILE}"
  exit 0
fi
host="$(<"${HOST_FILE}")"
if [[ -z "${host}" ]]; then
  printf '[%s] certificate refresh skipped: HTTPS host is empty\n' "$(date '+%Y-%m-%d %H:%M:%S')" >>"${LOG_FILE}"
  exit 0
fi
command -v certbot >/dev/null 2>&1 || { echo "certbot is required for certificate refresh" >&2; exit 1; }
install -d -m 0755 "${WEBROOT}"
certbot renew --non-interactive --webroot --webroot-path "${WEBROOT}" >>"${LOG_FILE}" 2>&1
systemctl reload club3090-caddy.service
