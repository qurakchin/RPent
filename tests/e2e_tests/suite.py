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

"""Declarative E2E suite loader and shell-metadata CLI."""

from __future__ import annotations

import os
import re
import shlex
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SUITES_DIR = Path(__file__).resolve().parent / "suites"
DEFAULT_SHARED_ROOT = "/mnt/public/rpent_shared"
_SHARED_PREFIXES = ("assets/", "models/", "venvs/")
_ENV_PLACEHOLDER = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}")


def shared_root(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return env.get("RPENT_SHARED_ROOT", DEFAULT_SHARED_ROOT).rstrip("/")


def _load_suite_file(path: Path) -> dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    suite_name = path.stem
    data.setdefault("suite", suite_name)
    data.setdefault("robot", suite_name)
    data.setdefault("optional_models", [])
    data.setdefault("env", {})
    data.setdefault("base_args", [])
    data.setdefault("setup", {})
    data.setdefault("cases", [])
    return data


def discover_suites(suites_dir: Path = SUITES_DIR) -> dict[str, dict[str, Any]]:
    """Load all declarative suite TOMLs sorted by suite name."""
    if not suites_dir.is_dir():
        return {}
    return {
        path.stem: _load_suite_file(path)
        for path in sorted(suites_dir.glob("*.toml"), key=lambda p: p.stem)
    }


def load_suite(name: str, suites_dir: Path = SUITES_DIR) -> dict[str, Any]:
    path = suites_dir / f"{name}.toml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in suites_dir.glob("*.toml")))
        raise FileNotFoundError(
            f"Unknown E2E suite {name!r}; available: {available or 'none'}"
        )
    return _load_suite_file(path)


def resolve_value(
    value: str,
    *,
    shared: str,
    output_dir: str = "",
    gpu: str = "0",
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve placeholders ({output_dir}, {gpu}, {env:VAR}) and shared paths."""
    env = os.environ if environ is None else environ
    text = value.replace("{output_dir}", output_dir).replace("{gpu}", gpu)
    text = _ENV_PLACEHOLDER.sub(lambda m: env.get(m.group(1), ""), text)
    if text.startswith(_SHARED_PREFIXES):
        return f"{shared}/{text}"
    return text


def resolve_case(
    suite: dict[str, Any],
    case: dict[str, Any],
    *,
    output_dir: Path,
    gpu: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve env and CLI args for one case and collect missing prerequisites."""
    env_src = dict(os.environ if environ is None else environ)
    shared = shared_root(env_src)
    out_str = str(output_dir)

    # [env] entries act as defaults: an already-set external env var always wins.
    case_env: dict[str, str] = {}
    for mapping in (suite.get("env") or {}, case.get("env") or {}):
        for key, raw in mapping.items():
            if env_src.get(key):
                case_env[key] = env_src[key]
            else:
                case_env[key] = resolve_value(
                    str(raw),
                    shared=shared,
                    output_dir=out_str,
                    gpu=gpu,
                    environ={**env_src, **case_env},
                )

    combined_env = {**env_src, **case_env}
    raw_args = [*(suite.get("base_args") or []), *(case.get("args") or [])]
    args = [
        resolve_value(
            str(arg),
            shared=shared,
            output_dir=out_str,
            gpu=gpu,
            environ=combined_env,
        )
        for arg in raw_args
    ]

    missing: list[str] = []
    for var in case.get("require_env") or []:
        if not combined_env.get(var, "").strip():
            missing.append(f"env {var} is not set")

    opt_in = case.get("opt_in_env")
    if opt_in and combined_env.get(opt_in, "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        missing.append(f"opt-in {opt_in}=1 is not set")

    shared_prefix = shared + "/"
    seen_paths: set[str] = set()
    for val in (*case_env.values(), *args):
        if val.startswith(shared_prefix) and val not in seen_paths:
            seen_paths.add(val)
            if not Path(val).exists():
                missing.append(f"missing resource {val}")

    return {
        "name": case["name"],
        "robot": suite["robot"],
        "args": args,
        "env": case_env,
        "action_tool": case.get("action_tool"),
        "action_count_field": case.get("action_count_field"),
        "tool_args": {
            **(suite.get("tool_args") or {}),
            **(case.get("tool_args") or {}),
        },
        "require_post_action_image": bool(case.get("require_post_action_image", False)),
        "missing": missing,
    }


def _print_shell_meta(suite_name: str, output_dir: str) -> None:
    suite = load_suite(suite_name)
    shared = shared_root()
    setup = suite.get("setup") or {}

    print(f"SUITE_COMPONENT={shlex.quote(suite['component'])}")
    print(f"SUITE_REINSTALL_PKG={shlex.quote(setup.get('reinstall_copy_pkg', ''))}")

    post_cmd = [
        resolve_value(p, shared=shared, output_dir=output_dir)
        for p in (setup.get("post_install_cmd") or [])
    ]
    print("SUITE_POST_INSTALL_CMD=(" + " ".join(shlex.quote(p) for p in post_cmd) + ")")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(
            "Usage: suite.py <list|shell-meta <suite> <output_dir>>",
            file=sys.stderr,
        )
        return 2
    cmd = args[0]
    if cmd == "list":
        for name in discover_suites():
            print(name)
        return 0
    if cmd == "shell-meta" and len(args) == 3:
        _print_shell_meta(args[1], args[2])
        return 0
    print(f"Unknown command: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
