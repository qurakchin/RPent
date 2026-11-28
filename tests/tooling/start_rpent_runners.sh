#!/usr/bin/env bash
# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Idempotent, reboot-safe launcher for homogeneous rpent-gpu runners.
#
# First-time registration (when /opt/actions-runners/gpu-XX/.runner does not exist):
#   RUNNER_TOKEN=<github-registration-token> bash start_rpent_runners.sh
#
# Subsequent runs and after host reboot (no token required):
#   bash start_rpent_runners.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/RLinf/RPent}"
RUNNER_PREFIX="${RUNNER_PREFIX:-$(hostname -s)}"
RUNNER_COUNT="${RUNNER_COUNT:-16}"
RUNNER_LABELS="${RUNNER_LABELS:-rpent-gpu}"
GPU_POOL="${RPENT_GPU_POOL:-0,1,2,3,4,5,6,7}"
INSTALL_SLOTS="${RPENT_INSTALL_SLOTS:-4}"
SLOT_LOCK_DIR="${RPENT_SLOT_LOCK_DIR:-/tmp/rpent-ci-slots}"
SRC="${SRC:-/mnt/public/rpent_shared/actions-runner}"
BASE="${BASE:-/opt/actions-runners}"

mkdir -p "$BASE" "$SLOT_LOCK_DIR"

ensure_runner() {
  local idx=$1
  local tag
  tag=$(printf "gpu-%02d" "$idx")
  local dir="$BASE/$tag"
  local session="runner-$tag"
  local name="${RUNNER_PREFIX}-${tag}"

  if [[ ! -f "$dir/.runner" ]]; then
    if [[ -z "${RUNNER_TOKEN:-}" ]]; then
      echo "ERROR: $dir is not configured. Re-run with RUNNER_TOKEN=<token> to register." >&2
      exit 1
    fi
    rm -rf "$dir"
    mkdir -p "$dir"
    cp -a "$SRC/bin" "$SRC/externals" "$SRC/config.sh" "$SRC/env.sh" \
      "$SRC/run.sh" "$SRC/run-helper.sh.template" "$SRC/safe_sleep.sh" \
      "$dir/"
    if [[ -f "$SRC/.path" ]]; then
      cp -a "$SRC/.path" "$dir/"
    fi
    (
      cd "$dir"
      RUNNER_ALLOW_RUNASROOT=1 ./config.sh \
        --unattended --replace \
        --url "$REPO_URL" --token "$RUNNER_TOKEN" \
        --name "$name" --labels "$RUNNER_LABELS" --work _work
    )
  fi

  {
    echo 'LANG=en_US.utf8'
    echo 'LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64'
    echo 'CUDA_HOME=/usr/local/cuda-12.8'
    echo "RPENT_GPU_POOL=$GPU_POOL"
    echo "RPENT_INSTALL_SLOTS=$INSTALL_SLOTS"
    echo "RPENT_SLOT_LOCK_DIR=$SLOT_LOCK_DIR"
    echo 'RUNNER_ALLOW_RUNASROOT=1'
    echo 'UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/'
    echo 'UV_LINK_MODE=symlink'
    echo 'RPENT_GITHUB_MIRROR=https://gh-proxy.com'
    echo 'UV_LOCK_TIMEOUT=1200'
  } >"$dir/.env"

  if [[ -f "$dir/.path" ]]; then
    if ! grep -q "/usr/local/cuda-12.8/bin" "$dir/.path"; then
      printf '/usr/local/cuda-12.8/bin:%s\n' "$(cat "$dir/.path")" >"$dir/.path"
    fi
  else
    printf '/usr/local/cuda-12.8/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' >"$dir/.path"
  fi

  if [[ ! -x "$dir/keepalive.sh" ]]; then
    cat >"$dir/keepalive.sh" <<'KEOF'
#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export RUNNER_ALLOW_RUNASROOT=1
while true; do
  echo "[$(date -Is)] starting $(basename "$DIR")" >> "$DIR/keepalive.log"
  ./run.sh >> "$DIR/keepalive.log" 2>&1
  rc=$?
  echo "[$(date -Is)] exited rc=$rc, restarting in 10s" >> "$DIR/keepalive.log"
  sleep 10
done
KEOF
    chmod +x "$dir/keepalive.sh"
  fi

  if tmux has-session -t "$session" 2>/dev/null; then
    echo "$session already running"
  else
    tmux new-session -d -s "$session" "bash $dir/keepalive.sh"
    echo "$session started"
  fi
}

for ((i = 0; i < RUNNER_COUNT; i++)); do
  ensure_runner "$i"
done

tmux ls
