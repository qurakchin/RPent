# Architecture ↔ Code Map

A quick-lookup table mapping "architecture diagram (`docs/arch.jpeg`) → code path", so you can locate the module behind each layer while reading the code. The full alignment audit (including unimplemented items, docstring drift, etc.) lives in [`../ALIGN.md`](../ALIGN.md).

## Legend

- ✅ Implemented
- ⚠️ Partially implemented / naming or location not fully aligned
- 🚧 Appears in the diagram but not implemented in code (planned)

## 1. User Layer

| Diagram element | Status | Code path | Notes |
|---|---|---|---|
| Web Dashboard | ✅ | `rpent/dashboard/server.py` — FastAPI main service<br>`rpent/dashboard/launcher.py` — launcher-screen form adapter (`FIELDS`, `apply_to_args`)<br>`rpent/dashboard/state.py` — `State` thread-safe runtime state<br>`rpent/dashboard/index.html`, `index.zh-cn.html` — frontend (`--dashboard_language`) | Enabled via `python rpent/cli/main.py --dashboard`; interrupt / message injection lives in the `state.py::_interact` section |
| Interactive CLI | ⚠️ | `rpent/cli/main.py` (`_build_argparser`, `main`) | Itself a **batch** entrypoint; true conversational interaction relies on the dashboard input box under the `--dashboard-interact` combination |

## 2. Intelligence Layer — Agentic Planner

The diagram shows 4 boxes + 3 external arrows inside Agentic Planner; in code these are consolidated inside the `rpent/cerebrum/` package.

| Diagram element | Status | Code path | Notes |
|---|---|---|---|
| Agentic Planner (overall) | ⚠️ naming | `rpent/cerebrum/` | The code term is "cerebrum" rather than "planner"; see `rpent/cerebrum/base.py::Cerebrum` Protocol |
| Foundation Models | ⚠️ | No standalone module; scattered across 3 backends:<br>`rpent/cerebrum/api_loop.py::ApiAgentLoop` (pydantic-ai)<br>`rpent/cerebrum/claude_code.py::ClaudeCodeCerebrum`<br>`rpent/cerebrum/codex.py::CodexCerebrum` | Selected via the `build_cerebrum(cerebrum_type, ...)` factory (`base.py:121`) |
| Memory Management | ⚠️ | No standalone module; directory convention + helper:<br>`rpent/utils/config.py::get_memory_dir(env_name)` → `resources/<env>/memory/`<br>`rpent/cerebrum/base.py:189,208` mounted into SDK context via `extra_dirs` | LIBERO-side memory files live in `resources/libero/memory/*.md` |
| Agent Loop | ⚠️ | No standalone module; loop is embedded in each backend:<br>`rpent/cerebrum/api_loop.py::ApiAgentLoop._solve` (`while True` at :116)<br>`rpent/cerebrum/claude_code.py::consume_stream` | Dashboard injection / interrupt: `_take_injection` / `dashboard.take_pending_messages` |
| Tool Library | ✅ | `rpent/tools/toolkit.py::Toolkit` (base class, common tools)<br>`rpent/tools/common.py::TOOLS_SPEC` (read/write/list/finish)<br>Env-side extensions: `robots/libero/toolkit.py::LiberoToolkit` + `robots/libero/tools.py::LiberoPrimitives` | Toolkits register via `add_tool`; `get_tools_spec` + `execute_tool` are consumed by the cerebrum |
| Self-Evolve (arrow) | 🚧 | — | No corresponding module |
| External API (dashed) | ✅ | Consumed via the `api` cerebrum against Anthropic / OpenAI / OpenAI-compatible; see `rpent/cerebrum/base.py:138-173` (`_provider_factory` + `infer_model`) | |
| External Codex/CC (dashed) | ✅ | `rpent/cerebrum/claude_code.py` (Claude Agent SDK) + `rpent/cerebrum/codex.py` (openai-codex + `rpent/cerebrum/utils/http_mcp_server.py::HttpMcpServer` bridge) | |

## 3. Intelligence Layer — Action Primitive

| Diagram element | Status | Code path | Notes |
|---|---|---|---|
| VLA (Vision-Language-Action) | ✅ | Server side: `robots/libero/vla_server.py` (FastAPI, `/predict` + `/healthz`)<br>Client side: `rpent/utils/vla_client.py::VLAClient` | Currently only Pi0.5 for LIBERO |
| WAM (World-Action-Model) | 🚧 | — | Not implemented |
| Code as Policy | 🚧 | Closest analogue: `robots/libero/tools.py::LiberoPrimitives` (hand-written scripted primitives, not LLM-generated) | Not implemented |
| "…" (extension slot) | — | — | Placeholder in the diagram |

## 4. Interface Layer

| Diagram element | Status | Code path | Notes |
|---|---|---|---|
| API Gateway | 🚧 | — | No gateway; cerebrums talk directly to each SDK / provider |
| gRPC/REST Services | ⚠️ naming | REST: `robots/libero/vla_server.py` (FastAPI)<br>Socket-RPC (**not gRPC**): `rpent/utils/socket_rpc.py::SocketRpcServer` / `SocketRpcClient` (pickle-framed TCP) | The "gRPC" wording in the diagram is inaccurate; it is actually pickle-over-TCP |
| Integration Connectors | 🚧 | — | No standalone module |
| RPC Client (arrow) | ✅ | `rpent/utils/rpc.py::RpcClient` Protocol<br>`rpent/utils/rpc.py::create_rpc_client`<br>`rpent/utils/socket_rpc.py::SocketRpcClient` | Code lives under `rpent/utils/` (former `rpc_driver/` has been merged in), aligned with the diagram's "RPC Client" semantics |
| (not shown in diagram) In-process MCP HTTP bridge | ✅ | `rpent/cerebrum/utils/http_mcp_server.py::HttpMcpServer` | Lets the Codex CLI consume the in-process toolkit |
| (not shown in diagram) Env Client | ✅ | `robots/libero/env_client.py::LiberoEnvClient` | Agent-side env proxy; forwards to env_server |

## 5. Environment Layer — Simulator

| Diagram element | Status | Code path | Notes |
|---|---|---|---|
| robocasa | 🚧 | `deployment/robocasa/` contains only `__pycache__/` | No source; the quick-start commands in the README (`scripts/setup_robocasa.sh`, etc.) are currently not executable |
| LIBERO Pro | ✅ | `robots/libero/` full directory:<br>`env_server.py` (RLinf/LIBERO bootstrap + Socket RPC)<br>`vla_server.py` (Pi0.5)<br>`env_client.py`, `toolkit.py`, `tools.py`<br>`prompt_bundle.py`, `prompts/`, `guides/` | Actually supports `LIBERO_TYPE ∈ {standard, pro, plus}` (see `rpent/utils/config.py::get_libero_type`) |
| RoboTwin | 🚧 | — | Not implemented |
| Other Simulators | ✅ extension point | Dynamic resolution: `rpent/envs/base.py::_resolve_env` via `importlib.import_module("robots.<name>")` | Currently only the `robots/libero/` package exists; adding a new env: see [`ADD_A_NEW_ENV.md`](ADD_A_NEW_ENV.md) |

## 6. Environment Layer — Real-world

| Diagram element | Status | Code path | Notes |
|---|---|---|---|
| Franka | 🚧 | — | Not implemented |
| Dual-Arm | 🚧 | — | Not implemented |
| Humanoid | 🚧 | — | Not implemented |

## 7. Cross-cutting infrastructure present in code but not shown in the diagram

| Concept | Code path | Notes |
|---|---|---|
| Prompt rendering | `rpent/context/prompt_utils.py` (`PromptNode`, `format_prompt`, `BulletList`, `Numbered`)<br>`rpent/context/prompts/prompt.py` (shared `OUTPUT` / `USER`) | Env-side assembly: `robots/libero/prompt_bundle.py`, `robots/libero/prompts/{system,shared}.py`, `robots/libero/prompts/perception_system_prompt.md` |
| EnvSpec / PromptBundle contracts | `rpent/envs/env_spec.py::EnvSpec`<br>`rpent/envs/prompt_bundle.py::PromptBundle`<br>`rpent/envs/base.py::get_env_spec` / `get_toolkit` | Env registry: dynamic import of `robots.<name>` by name |
| Common utilities (Utils) | `rpent/utils/config.py` (`get_repo_root`, `get_memory_dir`, `get_libero_type`, `get_pi05_checkpoint_path`, `get_rlinf_repo_path`)<br>`rpent/utils/logging.py` (`get_logger`, `init_output_dir`, `get_output_dir`)<br>`rpent/utils/templates.py` (`substitute`, `substitute_text`) | |
| CLI entrypoint | `rpent/cli/main.py` (`start_env_server`, `start_vla_server`, `main`) | Lifecycle: launch env_server → launch vla_server → build toolkit + cerebrum → `cerebrum.solve` → teardown |
| Scripts | `scripts/run_batch.py` (batch runner)<br>`scripts/run_one.sh` (single-task shell)<br>`scripts/install_libero_pro_plus.sh`<br>`scripts/liberopro_register_perturbations.patch`<br>`scripts/codex_proxy/` (litellm proxy)<br>`scripts/sam3/` (SAM3 server) | |

## 8. Process-boundary overview

```
   ┌───────────── agent process ──────────────┐
   │  cli/main.py                             │
   │   ├── rpent.cerebrum.*  (LLM in loop)    │
   │   ├── rpent.tools + robots.libero.*      │
   │   └── rpent.dashboard  (optional)        │
   └───────────┬────────────────┬─────────────┘
   pickle/TCP  │                │  HTTP/REST
   (rpent.utils.socket_rpc)     │  (rpent.utils.vla_client)
               ▼                ▼
     ┌── env_server process ──┐   ┌── vla_server process ──┐
     │ robots/libero/         │   │ robots/libero/         │
     │   env_server.py        │   │   vla_server.py        │
     │ + RLinf/LIBERO         │   │ + Pi0.5 weights        │
     │ + MuJoCo/EGL           │   │ (FastAPI /predict)     │
     └────────────────────────┘   └────────────────────────┘
```

The three processes start and exit independently; see the "Three-process architecture" section of `README.md` and `rpent/cli/main.py::start_env_server` / `start_vla_server` for details.
