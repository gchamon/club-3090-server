#!/usr/bin/env bash
set -euo pipefail

if (($# == 0)); then
  services=(
    club3090-vllm.service
    club3090-benchmarks.service
    club3090-updater.service
    club3090-control.service
  )
elif (($# == 1)) && [[ "$1" == "--gpu" ]]; then
  services=(club3090-vllm.service)
else
  printf 'Usage: %s [--gpu]\n' "$0" >&2
  exit 2
fi

sudo systemctl stop "${services[@]}"
