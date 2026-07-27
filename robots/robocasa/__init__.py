"""RoboCasa environment extension."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from robots.robocasa.prompt_bundle import (
    system_prompt,
    user_prompt,
)
from rpent.envs.env_spec import EnvSpec, RunConfig
from rpent.envs.prompt_bundle import PromptBundle
from rpent.utils.config import get_repo_root

if TYPE_CHECKING:
    from rpent.dashboard.state import State
    from rpent.utils.daemon import ProcessDaemon
    from rpent.utils.rpc import RpcClient


def get_env_spec() -> EnvSpec:
    """Return the RoboCasa env identity, prompt bundle, and runner hooks.

    Tool schemas, handlers, server lifecycle, and the MCP allowlist live on
    the RoboCasa toolkit (see :func:`get_toolkit`).
    """
    return EnvSpec(
        name="robocasa",
        prompts=PromptBundle(
            system=system_prompt,
            user=user_prompt,
        ),
        add_cli_args=_add_cli_args,
        parse_config=_parse_config,
        init_runtime=_init_runtime,
    )


def get_toolkit(
    *,
    primitives_kwargs: dict[str, Any],
    video_path: str | None = None,
    dashboard: Any = None,
):
    """Return the RoboCasa toolkit (common tools + RoboCasa primitives)."""
    from robots.robocasa.toolkit import RoboCasaToolkit

    return RoboCasaToolkit(
        primitives_kwargs=primitives_kwargs,
        video_path=video_path,
        dashboard=dashboard,
    )


def _add_cli_args(parser: argparse.ArgumentParser, use_dashboard: bool) -> None:
    """Register RoboCasa CLI flags on the shared ``parser``."""
    required = not use_dashboard
    parser.add_argument("--robocasa-env", default=None, required=required,
                        help="RoboCasa task name, e.g. OpenDrawer")
    parser.add_argument("--robocasa-split", default="target",
                        choices=["target", "pretrain", "all"],
                        help="RoboCasa data split (default: target)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hi-res", type=int, default=0,
                        help="Hi-res agentview resolution (0=off)")
    parser.add_argument("--env-endpoint", default=None,
                        help="[protocol://]host:port of an existing env_server")
    parser.add_argument("--vla-endpoint", default=None,
                        help="[protocol://]host:port of an existing vla_server")
    parser.add_argument("--cuda-device", default=None,
                        help="GPU device(s) to expose via CUDA_VISIBLE_DEVICES.")


def _parse_config(args: argparse.Namespace) -> RunConfig:
    """Validate final ``args`` and derive per-run identifiers."""
    if not args.robocasa_env:
        raise ValueError("--robocasa-env is required")

    recipe_tag = f"{args.robocasa_env}_{args.robocasa_split}_s{args.seed}"
    prompt_vars = {
        "env_name": args.robocasa_env,
        "split": args.robocasa_split,
        "seed": args.seed,
        "recipe_tag": recipe_tag,
    }

    output_dir = args.output_dir
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S")
        output_dir = get_repo_root() / "logs" / f"{timestamp}_{args.robocasa_env}_{args.robocasa_split}_s{args.seed}"
    output_dir = Path(output_dir)

    dashboard_state = None
    if getattr(args, "dashboard", False):
        from rpent.dashboard.state import State
        dashboard_state = State(
            run_id=f"robocasa/{output_dir.name}",
            name=recipe_tag,
            suite=args.robocasa_env,
            task=0,
            seed=args.seed,
            output_dir=str(output_dir),
            video_path=str(output_dir / "episode.mp4"),
        )
    return RunConfig(
        recipe_tag=recipe_tag,
        output_dir=output_dir,
        prompt_vars=prompt_vars,
        dashboard_state=dashboard_state,
        task_desc={"env_name": args.robocasa_env, "split": args.robocasa_split, "seed": args.seed},
    )


def _parse_endpoint(endpoint: str) -> tuple[str, str, int]:
    """Parse ``[protocol://]host:port`` into ``(protocol, host, port)``.

    Protocol defaults to ``socket`` for robocasa (numpy-heavy payloads).
    """
    if "://" in endpoint:
        protocol, _, rest = endpoint.partition("://")
    else:
        protocol, rest = "http", endpoint
    host, _, port = rest.partition(":")
    if not host or not port:
        raise ValueError(f"endpoint must be [protocol://]host:port, got {endpoint!r}")
    return protocol, host, int(port)


def _subprocess_env(cuda_device: str | None, **extra: str) -> dict[str, str]:
    """Build the env dict for a subprocess: inherit from parent, apply
    ``--cuda-device`` uniformly, layer optional extras on top.

    If ``cuda_device`` is None, ``CUDA_VISIBLE_DEVICES`` is left as inherited
    (respecting whatever the parent shell set). If given, it wins.
    """
    env = os.environ.copy()
    if cuda_device is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(cuda_device)
    env.update(extra)
    return env


def _init_runtime(
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[list[ProcessDaemon], dict[str, Any]]:
    """Spawn env + vla daemons and build clients for RoboCasa.

    Each server can be spawned or attached-to independently: pass an
    endpoint to attach, or leave it unset to spawn a local subprocess.

    Heavy deps (rpc / vla / daemon / env_client) are imported lazily so
    that a bare ``import robots.robocasa`` (for ``get_env_spec`` /
    ``get_toolkit``) doesn't drag them in.
    """
    from robots.robocasa.env_client import RoboCasaEnvClient
    from robots.robocasa.vla_client import RoboCasaVLAClient
    from rpent.utils.daemon import ProcessDaemon, pick_free_port
    from rpent.utils.rpc import wait_for_ready
    from rpent.utils.socket_rpc import SocketRpcClient

    daemons: list[ProcessDaemon] = []

    # --- env_server --------------------------------------------------------
    if args.env_endpoint is None:
        host, port = "127.0.0.1", pick_free_port()
        env_daemon = ProcessDaemon(
            name="env_server",
            cmd=[
                sys.executable,
                str(get_repo_root() / "robots" / "robocasa" / "env_server.py"),
                "--env", args.robocasa_env,
                "--split", args.robocasa_split,
                "--seed", str(args.seed),
                "--transport_host", host,
                "--transport_port", str(port),
            ],
            env=_subprocess_env(
                args.cuda_device,
                MUJOCO_GL="egl",
            ),
            log_path=str(Path(output_dir) / "env_server.log"),
        )
        env_daemon.start()
        daemons.append(env_daemon)
        env_client: RpcClient = SocketRpcClient(host, port)
        wait_for_ready(env_client)
    else:
        protocol, host, port = _parse_endpoint(args.env_endpoint)
        if protocol == "socket":
            env_client = SocketRpcClient(host, port)
        else:
            raise ValueError(
                f"--env-endpoint protocol must be socket for robocasa, got {protocol!r}"
            )

    # --- vla_server --------------------------------------------------------
    if args.vla_endpoint is None:
        host, port = "127.0.0.1", pick_free_port()
        vla_daemon = ProcessDaemon(
            name="vla_server",
            cmd=[
                sys.executable,
                str(get_repo_root() / "robots" / "robocasa" / "vla_server.py"),
                "--transport_host", host,
                "--transport_port", str(port),
            ],
            env=_subprocess_env(args.cuda_device),
            log_path=str(Path(output_dir) / "vla_server.log"),
        )
        vla_daemon.start()
        daemons.append(vla_daemon)
        vla_rpc: RpcClient = SocketRpcClient(host, port)
        wait_for_ready(vla_rpc)
    else:
        protocol, host, port = _parse_endpoint(args.vla_endpoint)
        if protocol == "socket":
            vla_rpc = SocketRpcClient(host, port)
        else:
            raise ValueError(
                f"--vla-endpoint protocol must be socket for robocasa, got {protocol!r}"
            )

    primitives_kwargs = {
        "env": RoboCasaEnvClient(
            env_client,
            expected_meta={
                "camera_h": 256,
                "camera_w": 256,
            },
        ),
        "workdir": str(output_dir),
        "hi_res": args.hi_res or None,
        "vla_client": RoboCasaVLAClient(vla_rpc),
    }
    return daemons, primitives_kwargs
