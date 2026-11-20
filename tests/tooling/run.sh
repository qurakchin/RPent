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

# Run one of the repository tools in ``tests/tooling`` from a bare checkout.
#
# The tools read manifests and reproduction locks and add nothing but
# ``packaging``, so they do not need an installed environment. Pass the module and
# its arguments;
# ``tests/tooling/run.sh rpent.cli.install check --all`` is the form the
# installation guide uses in place of the explicit ``uv run`` prefix.

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

if ! command -v uv >/dev/null 2>&1; then
  printf 'uv is required to run the repository tools; install it from %s\n' \
    'https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  echo "usage: tests/tooling/run.sh <module> [arguments...]" >&2
  exit 2
fi

cd -- "$repo_root"
exec uv run --no-project --python 3.11 --with packaging -- python -m "$@"
