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
venv=${RPENT_E2E_PLANNER_VENV:-/mnt/public/rpent_shared/venvs/vllm}
model=${RPENT_E2E_PLANNER_MODEL:-/mnt/public/rpent_shared/models/Qwen3.5-0.8B}
cache_root=${RPENT_E2E_PLANNER_CACHE:-/mnt/public/rpent_shared/cache/planner}
if [[ ! -x "$venv/bin/vllm" ]]; then
  echo "Pre-installed vLLM binary not found: $venv/bin/vllm (set RPENT_E2E_PLANNER_VENV)" >&2
  exit 1
fi
if [[ ! -d "$model" ]]; then
  echo "Pre-installed planner model not found: $model (set RPENT_E2E_PLANNER_MODEL)" >&2
  exit 1
fi
port=${RPENT_E2E_PLANNER_PORT:-$((18396 + ${CUDA_VISIBLE_DEVICES:?select a single GPU}))}
export RPENT_E2E_PLANNER_URL="http://127.0.0.1:$port/v1"
export VLLM_CACHE_ROOT="$cache_root/vllm"
export TRITON_CACHE_DIR="$cache_root/triton"
export TORCHINDUCTOR_CACHE_DIR="$cache_root/torchinductor"

# The simulator and action model share this GPU; avoid vLLM's 90% default.
setsid "$venv/bin/vllm" serve "$model" \
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
