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

# Run the installer on a checkout that has no environment yet.
#
# The ``rpent-install`` console script exists only after an environment is
# installed,
# so this launcher runs ``rpent.cli.install`` in a throwaway uv environment
# that adds nothing but the manifest parser dependency. Documentation and CI
# call it, so the bootstrap interpreter and that dependency are declared once;
# installer arguments pass straight through.

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if ! command -v uv >/dev/null 2>&1; then
  printf 'uv is required to bootstrap rpent-install; install it from %s\n' \
    'https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi

cd -- "$repo_root"
exec uv run --no-project --python 3.11 --with packaging -- \
  python -m rpent.cli.install "$@"
