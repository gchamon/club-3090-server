#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="${CLUB3090_SERVER_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)}"
CONTROL_DIR="${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}"

printf '[club3090-vllm] stopping managed inference instances\n'
cd "${SERVER_DIR}/src"
export CLUB3090_SERVER_DIR="${SERVER_DIR}"
export CLUB3090_CONTROL_DIR="${CONTROL_DIR}"
exec /usr/bin/python3 -m control.http_server --stop-managed-instances
