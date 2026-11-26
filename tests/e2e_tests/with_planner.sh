#!/usr/bin/env bash
# Copyright 2026 The RPent Authors.
# Start one GPU planner for this suite and stop its workers when pytest exits.
set -euo pipefail
log=${1:?expected server log path}
shift
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}${no_proxy:+$no_proxy,}127.0.0.1,localhost"
export no_proxy="$NO_PROXY"
if [[ -n "${RPENT_E2E_PLANNER_URL:-}" ]]; then
  curl --noproxy '*' -fsS --max-time 5 "${RPENT_E2E_PLANNER_URL%/}/models" >/dev/null
  exec "$@"
fi
root=${RPENT_E2E_PLANNER_DIR:-/mnt/public/ljy/ci-planner/qwen35-08b}
bash "$(dirname "${BASH_SOURCE[0]}")/provision_planner.sh" "$root"
port=${RPENT_E2E_PLANNER_PORT:-$((18396 + ${CUDA_VISIBLE_DEVICES:?select a single GPU}))}
export RPENT_E2E_PLANNER_URL="http://127.0.0.1:$port/v1"
export VLLM_CACHE_ROOT="$root/cache/vllm"
export TRITON_CACHE_DIR="$root/cache/triton"
export TORCHINDUCTOR_CACHE_DIR="$root/cache/torchinductor"

# The simulator and action model share this GPU; avoid vLLM's 90% default.
setsid "$root/venv/bin/vllm" serve "$root/model" \
  --host 127.0.0.1 --port "$port" --served-model-name Qwen3.5-0.8B \
  --dtype bfloat16 --seed 0 --enforce-eager \
  --gpu-memory-utilization "${RPENT_E2E_PLANNER_GPU_MEMORY_UTILIZATION:-0.20}" \
  --max-model-len 16384 --max-num-seqs 1 --max-num-batched-tokens 2048 \
  --limit-mm-per-prompt '{"image": 8, "video": 0}' \
  --mm-processor-kwargs '{"size": {"shortest_edge": 65536, "longest_edge": 262144}}' \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --override-generation-config '{"temperature": 0}' \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking": false}' \
  >"$log" 2>&1 &
planner_pid=$!
stop_planner() {
  kill -TERM -- "-$planner_pid" 2>/dev/null || true
  wait "$planner_pid" 2>/dev/null || true
}
trap stop_planner EXIT
trap 'exit 143' TERM HUP
trap 'exit 130' INT
for ((i = 0; i < 600; i++)); do
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
echo "Qwen3.5-0.8B failed to become ready; see $log" >&2
exit 1
