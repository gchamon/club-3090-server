#!/usr/bin/env bash
set -euo pipefail

INTERVAL_SECONDS="${CLUB3090_CONSOLE_INTERVAL:-1}"
TAIL_LINES="${CLUB3090_CONSOLE_TAIL:-80}"
last_line=""
last_emit=0

emit() {
  local line="$1" now
  [[ -z "${line}" || "${line}" == *"GET /health HTTP/1.1"* || "${line}" == "${last_line}" ]] && return 0
  now="$(date +%s)"
  (( now - last_emit >= INTERVAL_SECONDS )) || return 0
  printf '[club3090-console] %s\n' "${line}"
  last_line="${line}"
  last_emit="${now}"
}

emit "Docker log follower starting. Waiting for club-3090 runtime container..."
while true; do
  mapfile -t containers < <(docker ps --format '{{.Names}}' | grep -Ei 'club3090-|vllm|qwen|llama-cpp' || true)
  if ((${#containers[@]} == 0)); then
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
  for pid in "${pids[@]}"; do kill "${pid}" 2>/dev/null || true; done
  emit "A log stream ended; rescanning..."
  sleep 2
done
