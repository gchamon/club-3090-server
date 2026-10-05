#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="${CLUB3090_SERVER_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
CONTROL_DIR="${CLUB3090_CONTROL_DIR:-/var/lib/club3090-control}"

printf '[club3090-vllm] applying active power profile before model startup\n'
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -pm 1 || true
  nvidia-smi -rgc || true
  nvidia-smi -pl "${CLUB3090_GPU_ACTIVE_POWER_LIMIT_W:-280}" || true
fi
if command -v cpupower >/dev/null 2>&1; then
  cpupower frequency-set -g "${CLUB3090_CPU_ACTIVE_GOVERNOR:-performance}" || true
fi

printf '[club3090-vllm] starting enabled club-3090 instances\n'
cd "${SERVER_DIR}/src"
export CLUB3090_SERVER_DIR="${SERVER_DIR}"
export CLUB3090_CONTROL_DIR="${CONTROL_DIR}"
exec /usr/bin/python3 -m control.http_server --boot-enabled-instances
