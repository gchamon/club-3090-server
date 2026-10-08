#!/usr/bin/env bash
set -euo pipefail

if (($# != 0)); then
  printf 'Usage: %s\n' "$0" >&2
  exit 2
fi

sudo systemctl start \
  club3090-control.service \
  club3090-updater.service \
  club3090-benchmarks.service \
  club3090-vllm.service
