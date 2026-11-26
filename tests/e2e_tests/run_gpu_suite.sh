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

set -euo pipefail

# Do not let a runner's interactive shell or previously activated environment
# affect imports or uv's target environment.
unset PYTHONPATH VIRTUAL_ENV CONDA_PREFIX UV_NO_CACHE

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <suite|build:<component>> <output-dir> <venv-root>"
  echo "Each target installs the matching robot component into a clean environment."
  exit 2
fi

target=$1
output_dir=$2
venv_root=$3
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
all_suites=(libero libero-pro libero-plus robocasa robotwin robodojo robolab)

if [[ "$target" != build:* && ! "${CUDA_VISIBLE_DEVICES:-}" =~ ^[0-9]+$ ]]; then
  echo "CUDA_VISIBLE_DEVICES must expose exactly one selected GPU"
  exit 1
fi
if [[ -e "$output_dir" || -e "$venv_root" ]]; then
  echo "Output and venv paths must not already exist"
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to create a clean Python environment"
  exit 1
fi
for command in timeout setsid ps; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required to bound tests and verify process cleanup"
    exit 1
  fi
done

install_timeout=${RPENT_INSTALL_TIMEOUT:-45m}
test_timeout=${RPENT_TEST_TIMEOUT:-45m}
pytest_timeout=${RPENT_GPU_PYTEST_TIMEOUT_SECONDS:-1200}

if [[ ! "$pytest_timeout" =~ ^[1-9][0-9]*$ ]]; then
  echo "RPENT_GPU_PYTEST_TIMEOUT_SECONDS must be a positive integer"
  exit 1
fi

mkdir -p "$output_dir" "$venv_root"
output_dir=$(cd "$output_dir" && pwd)
venv_root=$(cd "$venv_root" && pwd)

cleanup() {
  if [[ -d "$venv_root" ]]; then
    find "$venv_root" -depth -delete
  fi
}
trap cleanup EXIT

require_dir() {
  local name=$1
  local value=${!name:-}
  if [[ -z "$value" || ! -d "$value" ]]; then
    echo "$name must point to a directory"
    exit 1
  fi
}

require_file() {
  local name=$1
  local value=${!name:-}
  if [[ -z "$value" || ! -f "$value" ]]; then
    echo "$name must point to a file"
    exit 1
  fi
}

session_processes() {
  local session_id=$1
  ps -o pid= --sid "$session_id" 2>/dev/null | awk '{$1=$1}; NF {print}' || true
}

wait_for_session_exit() {
  local session_id=$1
  local attempts=$2
  local attempt

  for ((attempt = 0; attempt < attempts; attempt++)); do
    if [[ -z "$(session_processes "$session_id")" ]]; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

terminate_session_processes() {
  local session_id=$1
  local -a pids=()

  mapfile -t pids < <(session_processes "$session_id")
  if ((${#pids[@]} == 0)); then
    return
  fi

  kill -TERM "${pids[@]}" 2>/dev/null || true
  if wait_for_session_exit "$session_id" 50; then
    return
  fi

  mapfile -t pids < <(session_processes "$session_id")
  if ((${#pids[@]} > 0)); then
    kill -KILL "${pids[@]}" 2>/dev/null || true
    wait_for_session_exit "$session_id" 25 || true
  fi
}

verify_test_session_cleanup() {
  local name=$1
  local session_file=$2
  local report="$output_dir/$name-daemon-cleanup.txt"
  local session_id
  local residual_before
  local residual_after

  if [[ ! -s "$session_file" ]]; then
    echo "cleanup_status=failed" >"$report"
    echo "reason=pytest session id was not recorded" >>"$report"
    echo "$name cleanup verification failed: session id was not recorded"
    return 1
  fi
  session_id=$(<"$session_file")
  if [[ ! "$session_id" =~ ^[1-9][0-9]*$ ]]; then
    echo "cleanup_status=failed" >"$report"
    echo "reason=invalid pytest session id: $session_id" >>"$report"
    echo "$name cleanup verification failed: invalid session id"
    return 1
  fi

  # Parent-watch daemons may need a moment to observe EOF after pytest exits.
  wait_for_session_exit "$session_id" 25 || true
  residual_before=$(session_processes "$session_id")
  if [[ -n "$residual_before" ]]; then
    terminate_session_processes "$session_id"
  fi
  residual_after=$(session_processes "$session_id")

  {
    echo "session_id=$session_id"
    if [[ -n "$residual_before" ]]; then
      echo "residual_before_cleanup=${residual_before//$'\n'/,}"
    else
      echo "residual_before_cleanup=none"
    fi
    if [[ -n "$residual_after" ]]; then
      echo "residual_after_cleanup=${residual_after//$'\n'/,}"
      echo "cleanup_status=failed"
    else
      echo "residual_after_cleanup=none"
      echo "cleanup_status=passed"
    fi
  } >"$report"

  if [[ -n "$residual_after" ]]; then
    echo "$name cleanup verification failed; see $report"
    return 1
  fi
  if [[ -n "$residual_before" ]]; then
    echo "$name left processes running; they were terminated; see $report"
    return 1
  fi
  echo "$name daemon cleanup verified"
}

run_gpu_pytest() {
  local name=$1
  local python=$2
  local suite_output="$output_dir/$name"
  local junit_path="$output_dir/$name-junit.xml"
  shift 2
  local session_file="$output_dir/$name-pytest-session.txt"
  local test_status
  local cleanup_status=0

  set +e
  RPENT_E2E_OUTPUT_DIR="$suite_output" \
    timeout --foreground --kill-after=2m "$test_timeout" \
    bash -c '
      set -euo pipefail
      session_file=$1
      shift
      setsid "$@" &
      session_id=$!
      echo "$session_id" >"$session_file"
      cleanup() {
        kill -TERM -- "-$session_id" 2>/dev/null || true
      }
      trap cleanup EXIT HUP INT TERM
      wait "$session_id"
    ' bash "$session_file" \
      bash "$repo_root/tests/e2e_tests/with_planner.sh" "$output_dir/$name-planner-server.log" \
      "$python" -m pytest -v -rs \
      --timeout="$pytest_timeout" \
      --basetemp="$output_dir/$name-pytest-tmp" \
      --junitxml="$junit_path" "$@"
  test_status=$?
  set -e

  verify_test_session_cleanup "$name" "$session_file" || cleanup_status=$?
  if ((test_status != 0)); then
    return "$test_status"
  fi
  if [[ -z "$(find "$output_dir" -name tool-coverage.json -print -quit)" ]]; then
    echo "$name did not execute a planner/tool coverage test; check skipped prerequisites" >&2
    return 1
  fi
  return "$cleanup_status"
}

# rpent-install is the only supported install entry point. A fresh checkout has
# no installed CLI yet, so the launcher bootstraps it in a throwaway environment;
# the installer then selects the target Python from the component manifest.
run_rpent_install() {
  timeout --kill-after=2m "$install_timeout" \
    "$repo_root/rpent-install.sh" "$@"
}

install_test_runner() {
  local python=$1
  # The test runner is the suite's own tool, not part of the environment under
  # test: the venv is deleted after the run, so no fingerprint attests these
  # packages, and a pin here would only change how the suite is driven.
  timeout --kill-after=2m "$install_timeout" \
    uv pip install --python "$python" pytest pytest-timeout
}

run_in_clean_env() {
  local name=$1
  local component=$2
  shift 2
  local venv_dir="$venv_root/$name"

  run_rpent_install install "$component" --venv "$venv_dir"
  install_test_runner "$venv_dir/bin/python"
  run_gpu_pytest "$name" "$venv_dir/bin/python" "$@"
}

run_libero() {
  local name=$1
  local variant=$2
  local component=$3
  local asset_var=$4
  local package=$5
  local downloader=$6
  shift 6
  local venv_dir="$venv_root/$name"
  local requirement

  require_dir "$asset_var"
  export RPENT_LIBERO_VARIANT="$variant"
  export LIBERO_CONFIG_PATH="$output_dir/libero-config"
  mkdir "$LIBERO_CONFIG_PATH"
  run_rpent_install install "$component" --venv "$venv_dir"
  install_test_runner "$venv_dir/bin/python"

  # The download command writes beside the simulator module. Keep those writes
  # in this venv even when its dependencies are symlinked to the shared cache.
  requirement=$(uv pip freeze --python "$venv_dir/bin/python" \
    | awk -v pkg="$package" '$1 == pkg || index($1, pkg "==") == 1 {print}')
  if [[ -z "$requirement" ]]; then
    echo "Expected $package in $venv_dir" >&2
    return 1
  fi
  timeout --kill-after=2m "$install_timeout" uv pip install \
    --python "$venv_dir/bin/python" --link-mode copy \
    --reinstall-package "$package" --no-deps "$requirement"
  timeout --kill-after=2m "$install_timeout" \
    "$venv_dir/bin/$downloader" --link "${!asset_var}"
  run_gpu_pytest "$name" "$venv_dir/bin/python" "$@"
}

run_robodojo() {
  require_dir ROBODOJO_ASSETS_ROOT
  if [[ -n "${ROBODOJO_SIM_PYTHON:-}" ]]; then
    require_file ROBODOJO_SIM_PYTHON
  fi
  export OMNI_KIT_ACCEPT_EULA=YES
  export RPENT_RUN_ROBODOJO_INTEGRATION=1
  run_in_clean_env "$target" robot-robodojo "$@"
}

build_component_env() {
  local component=$1
  local venv_dir="$venv_root/$component"

  run_rpent_install install "$component" --venv "$venv_dir"
  cp "$venv_dir/rpent-install.json" "$output_dir/"
  run_rpent_install doctor --venv "$venv_dir"
  "$venv_dir/bin/rpent" --help >/dev/null
}

cd "$repo_root"
case "$target" in
  build:*)
    build_component_env "${target#build:}"
    ;;
  all)
    status=0
    for suite in "${all_suites[@]}"; do
      bash "$repo_root/tests/e2e_tests/run_gpu_suite.sh" \
        "$suite" "$output_dir/$suite" "$venv_root/$suite" || status=1
    done
    exit "$status"
    ;;
  libero)
    export PI05_CHECKPOINT_PATH="${LIBERO_STANDARD_CHECKPOINT_PATH:-${PI05_CHECKPOINT_PATH:-}}"
    run_libero libero standard robot-libero LIBERO_ASSET_PATH rpent-libero \
      libero-download-assets tests/e2e_tests/libero/test_components.py \
      tests/e2e_tests/libero/test_policy_chain.py
    ;;
  libero-pro)
    run_libero libero-pro pro robot-libero LIBERO_PRO_ASSET_PATH rpent-liberopro \
      liberopro-download-assets tests/e2e_tests/libero -k 'not wam'
    ;;
  libero-plus)
    export PI05_CHECKPOINT_PATH="${LIBERO_STANDARD_CHECKPOINT_PATH:-${PI05_CHECKPOINT_PATH:-}}"
    run_libero libero-plus plus robot-libero_plus LIBERO_PLUS_ASSET_PATH \
      rlinf-liberoplus liberoplus-download-assets \
      tests/e2e_tests/libero/test_components.py \
      tests/e2e_tests/libero/test_policy_chain.py -k 'not wam'
    ;;
  robocasa)
    require_dir ROBOCASA_ASSETS_PATH
    export RPENT_RUN_ROBOCASA_INTEGRATION=1
    run_in_clean_env robocasa robot-robocasa tests/e2e_tests/robocasa
    ;;
  robotwin)
    require_dir ROBOTWIN_ASSETS_PATH
    run_in_clean_env robotwin robot-robotwin tests/e2e_tests/robotwin
    ;;
  robodojo)
    run_robodojo tests/e2e_tests/robodojo
    ;;
  robolab)
    export PI05_CHECKPOINT_PATH="${ROBOLAB_CHECKPOINT_PATH:-${PI05_CHECKPOINT_PATH:-}}"
    require_dir ROBOLAB_ASSETS_PATH
    require_file ROBOLAB_SIM_PYTHON
    run_in_clean_env robolab robot-robolab tests/e2e_tests/robolab
    ;;
  *)
    echo "Unknown target: $target" >&2
    exit 2
    ;;
esac
