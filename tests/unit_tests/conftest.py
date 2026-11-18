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

"""Shared logging isolation, RPC, and synthetic manifest fixtures."""

import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from rpent.install.discovery import Catalog
from rpent.install.manifest import Component, Profile
from rpent.utils import logging as run_logging
from rpent.utils.rpc.http_rpc import HttpRpcClient, HttpRpcServer
from rpent.utils.rpc.socket_rpc import SocketRpcClient, SocketRpcServer

TRANSPORTS = ["socket", "http"]


@pytest.fixture(autouse=True)
def isolate_run_logging(monkeypatch):
    """Restore process-wide logging after planner, CLI, or robot tests."""
    logger = run_logging.get_logger()
    handlers = list(logger.handlers)
    level, propagate = logger.level, logger.propagate
    monkeypatch.setattr(run_logging, "_log_initialized", run_logging._log_initialized)
    monkeypatch.setattr(run_logging, "_output_dir", run_logging._output_dir)
    try:
        yield
    finally:
        for handler in logger.handlers:
            if handler not in handlers:
                handler.close()
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate


@pytest.fixture(params=TRANSPORTS)
def transport(request):
    return request.param


@pytest.fixture
def make_server_and_client():
    """Serve a facade on a loopback transport and yield its client."""

    @contextmanager
    def _ctx(facade, transport, *, enable_sessions=False):
        if transport == "socket":
            server = SocketRpcServer(("127.0.0.1", 0), facade._dispatch)
        else:
            server = HttpRpcServer(("127.0.0.1", 0), facade._dispatch)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            if transport == "socket":
                client = SocketRpcClient(
                    "127.0.0.1", port, enable_sessions=enable_sessions
                )
            else:
                client = HttpRpcClient(
                    f"http://127.0.0.1:{port}", enable_sessions=enable_sessions
                )
            yield client
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    return _ctx


@pytest.fixture
def write_toml(tmp_path):
    """Write a TOML file and return its path."""

    def _write(relative, text):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.strip() + "\n", encoding="utf-8")
        return path

    return _write


@pytest.fixture
def make_component(tmp_path):
    """Build a component without touching the filesystem."""

    def _make(name, **values):
        placements = tuple(values.pop("placements", ("in-env",)))
        kind = values.pop("kind", "robot")
        directory = {
            "model": Path("components") / "models",
            "toolkit": Path("components") / "toolkits",
        }.get(kind, Path("robots"))
        return Component(
            name=name,
            kind=kind,
            path=tmp_path / directory / name,
            manifest=tmp_path / directory / name / "component.toml",
            probe=values.pop("probe", f"robots.{name}"),
            python=values.pop("python", None),
            platforms=tuple(values.pop("platforms", ())),
            requires=tuple(values.pop("requires", ())),
            imports=tuple(values.pop("imports", ())),
            env_conflicts=tuple(values.pop("env_conflicts", ())),
            placements=placements,
            default_variant=values.pop("default_variant", None),
            variant_required=values.pop("variant_required", False),
            dependencies=tuple(values.pop("dependencies", ())),
            optional=values.pop("optional", {}),
            overrides=tuple(values.pop("overrides", ())),
            docs=None,
            manifest_sha256=values.pop("manifest_sha256", name),
        )

    return _make


@pytest.fixture
def make_profile(tmp_path):
    """Build a profile without touching the filesystem."""

    def _make(name, components=None, **values):
        return Profile(
            name=name,
            path=tmp_path / "installs" / "profiles" / f"{name}.toml",
            python=values.pop("python", "3.11"),
            platform=values.pop("platform", "linux-x86_64"),
            components=components or {},
            dependencies=tuple(values.pop("dependencies", ())),
            index_url=values.pop("index_url", None),
            extra_index_urls=tuple(values.pop("extra_index_urls", ())),
            index_strategy=values.pop("index_strategy", None),
            lock=values.pop("lock", None),
            core=values.pop("core", True),
            generate_extra=values.pop("generate_extra", False),
            extra=values.pop("extra", None),
            description=None,
            manylinux=values.pop("manylinux", "2_31"),
        )

    return _make


@pytest.fixture
def make_catalog(tmp_path, make_component, make_profile):
    """Build a catalog from component and profile mappings."""

    def _make(components=(), profiles=None):
        component_map = {component.name: component for component in components}
        return Catalog(
            root=Path(tmp_path),
            components=component_map,
            profiles=profiles or {},
        )

    return _make
