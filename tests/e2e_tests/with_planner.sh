#!/usr/bin/env bash
# Copyright 2026 The RPent Authors.
# Start one CPU model for this GPU slot and stop it when pytest exits.
set -euo pipefail
log=${1:?expected server log path}
shift
root=${RPENT_E2E_PLANNER_DIR:-/mnt/public/rpent_shared/models/ci-qwen35-2b}
port=$((18396 + ${CUDA_VISIBLE_DEVICES:?select a single GPU}))
export RPENT_E2E_PLANNER_URL="http://127.0.0.1:$port/v1"

"$root/llama-b12774/llama-server" --host 127.0.0.1 --port "$port" \
  --model "$root/Qwen3.5-2B-Q4_K_M.gguf" --mmproj "$root/mmproj-F16.gguf" \
  --alias Qwen3.5-2B --jinja --reasoning off --temp 0 --seed 0 \
  --threads 6 --parallel 1 --ctx-size 32768 -ngl 0 --no-mmproj-offload \
  >"$log" 2>&1 &
planner_pid=$!
stop_planner() {
  kill "$planner_pid" 2>/dev/null || true
  wait "$planner_pid" 2>/dev/null || true
}
trap stop_planner EXIT
trap 'exit 143' TERM HUP
trap 'exit 130' INT
for ((i = 0; i < 180; i++)); do
  if ! kill -0 "$planner_pid" 2>/dev/null; then
    tail -30 "$log" >&2
    exit 1
  fi
  if curl --noproxy '*' -fsS --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    "$@"
    exit $?
  fi
  sleep 1
done
echo "Qwen3.5-2B failed to become ready; see $log" >&2
exit 1
