#!/usr/bin/env bash
# Copyright 2026 The RPent Authors.
# Install the GPU planner in its own environment, separate from simulator pins.
set -euo pipefail
root=${1:?usage: provision_planner.sh INSTALL_DIRECTORY}
mkdir -p "$root"
root=$(cd "$root" && pwd)
exec 9>"$root/.provision.lock"
flock 9
if [[ -f "$root/.ready-vllm-0.18.0" ]]; then
  exit 0
fi
export HF_HUB_CACHE="$root/cache/huggingface"
uv venv --allow-existing --python 3.11 "$root/venv"
uv pip install --python "$root/venv/bin/python" 'vllm==0.18.0'
"$root/venv/bin/python" - "$root/model" <<'PYTHON'
import sys
from huggingface_hub import snapshot_download

snapshot_download(
    "Qwen/Qwen3.5-0.8B",
    revision="2fc06364715b967f1860aea9cf38778875588b17",
    local_dir=sys.argv[1],
)
PYTHON
touch "$root/.ready-vllm-0.18.0"
