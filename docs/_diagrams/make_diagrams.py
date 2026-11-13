#!/usr/bin/env python3
"""Generate the architecture diagrams used by both documentation trees.

The diagrams are checked in as SVG under ``docs/_static/img`` so a Sphinx build
needs no Graphviz installation. Edit the labels below and rerun this script
(``make diagrams`` from ``docs``) after changing the system structure.

Requires the Graphviz ``dot`` executable on ``PATH``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
OUTPUT = DOCS / "_static" / "img"

COLORS = {
    "user": {"fill": "#f2f8ea", "border": "#a9cf85", "title": "#3f6b1f"},
    "agent": {"fill": "#eaf1fd", "border": "#93b4f0", "title": "#1d4ed8"},
    "service": {"fill": "#e7f7f5", "border": "#7fd3c8", "title": "#0f766e"},
    "env": {"fill": "#f3ecfe", "border": "#b79bea", "title": "#6d28d9"},
}

LABELS = {
    "en": {
        "font": "Helvetica",
        "user": "User",
        "agent": "Agent",
        "service": "Model and environment services",
        "env": "Environments",
        "dashboard": ("Web Dashboard", "Session · TaskRun · SSE"),
        "cli": ("CLI / TUI", "rpent --robot &lt;name&gt;"),
        "planner": ("Planner", "api · claude_code · codex · flash"),
        "toolkit": ("Toolkit", "tool schemas · dispatch · ToolResult"),
        "memory": ("MemoryManager", "read · merge · index"),
        "prompts": ("Prompts", "system · user templates"),
        "vla": ("VLA / WAM service", "Pi0.5 · RLDX-1 · LingBot-VLA<BR/>VPP2 · Awomo05"),
        "perception": ("Perception service", "SAM3 · Molmo2<BR/>(Flash localization)"),
        "env_service": ("Environment service", "simulator or robot connection"),
        "sims": ("Simulators", "LIBERO · RoboCasa365<BR/>RoboTwin · RoboDojo"),
        "real": ("Real robots", "Franka · Dual-Arm Franka · YAM"),
        "e_task": "task",
        "e_memory": "memory",
            "e_action": "action",
        "e_state": "state",
        "e_connect": "connection",
        "flow_title": "Task execution",
        "f_cli": ("CLI", "load RobotSpec · parse RunConfig"),
        "f_session": ("Session / TaskRun", "memory sync · planner · prompts"),
        "f_services": ("Runtime services", "VLA · perception · environment"),
        "f_loop": ("Planner loop", "list_tools → execute_tool → ToolResult"),
        "f_end": ("Planner stops", "finish · turn limit · error"),
        "f_result": ("Run artifacts", "episode.mp4 · transcript · run.log"),
        "f_note": "Success is decided by the environment or the robot operator, not by finish.",
        "f_loop_edge": "next turn",
        "f_fail": ("Tool failure / timeout", "error returned to the planner"),
        "f_error": "error / timeout",
        "f_obs": ("Observation", "images and state after each action"),
        "legend": "Green: user entry · Blue: agent · Teal: services · Purple: environments",
    },
    "zh": {
        "font": "Hiragino Sans GB,Noto Sans CJK SC,sans-serif",
        "user": "用户层",
        "agent": "智能体层",
        "service": "模型与环境服务",
        "env": "环境层",
        "dashboard": ("Web Dashboard", "Session · TaskRun · SSE"),
        "cli": ("CLI / TUI", "rpent --robot &lt;name&gt;"),
        "planner": ("Planner", "api · claude_code · codex · flash"),
        "toolkit": ("Toolkit", "工具定义 · 调用分发 · ToolResult"),
        "memory": ("MemoryManager", "读取 · 合并 · 索引"),
        "prompts": ("提示词", "system · user 模板"),
        "vla": ("VLA / WAM 服务", "Pi0.5 · RLDX-1 · LingBot-VLA<BR/>VPP2 · Awomo05"),
        "perception": ("感知服务", "SAM3 · Molmo2<BR/>（Flash 定位）"),
        "env_service": ("环境服务", "仿真器或真机连接"),
        "sims": ("仿真环境", "LIBERO · RoboCasa365<BR/>RoboTwin · RoboDojo"),
        "real": ("真机", "单臂 Franka · 双臂 Franka · YAM"),
        "e_task": "任务",
        "e_memory": "记忆",
        "e_action": "动作",
        "e_state": "状态",
        "e_connect": "连接",
        "flow_title": "一次任务的执行流程",
        "f_cli": ("CLI", "加载 RobotSpec · 解析 RunConfig"),
        "f_session": ("Session / TaskRun", "同步记忆 · 构造规划器 · 渲染提示词"),
        "f_services": ("运行服务", "VLA · 感知 · 环境"),
        "f_loop": ("规划循环", "list_tools → execute_tool → ToolResult"),
        "f_end": ("规划结束", "finish · 回合上限 · 错误"),
        "f_result": ("运行产物", "episode.mp4 · transcript · run.log"),
        "f_note": "成功由环境或真机操作员判定，finish 本身不代表任务成功。",
        "f_loop_edge": "下一轮",
        "f_fail": ("工具失败 / 超时", "错误返回规划器"),
        "f_error": "错误 / 超时",
        "f_obs": ("环境观测", "每次动作后的图像与状态"),
        "legend": "绿色：用户入口 · 蓝色：智能体 · 青色：服务 · 紫色：环境",
    },
}


def node(lang: str, key: str, role: str) -> str:
    """Return one styled node whose label carries a bold title and a detail line."""
    title, detail = LABELS[lang][key]
    color = COLORS[role]
    group = ", group=spine" if key in ("toolkit", "env_service") else ""
    return (
        f'  {key} [label=<<FONT POINT-SIZE="13"><B>{title}</B></FONT>'
        f'<BR/><FONT POINT-SIZE="10" COLOR="#4b5563">{detail}</FONT>>,'
        f' fillcolor="{color["fill"]}", color="{color["border"]}"{group}];\n'
    )


def cluster(
    lang: str, name: str, role: str, body: str, labelloc: str = "t"
) -> str:
    color = COLORS[role]
    return (
        f"  subgraph cluster_{name} {{\n"
        f'    label="{LABELS[lang][name]}"; labeljust="l"; labelloc="{labelloc}";\n'
        f'    fontsize=14; margin=14;\n'
        f'    fontcolor="{color["title"]}"; style="rounded,filled";\n'
        f'    fillcolor="{color["fill"]}66"; color="{color["border"]}";\n'
        f"{body}"
        f"  }}\n"
    )


def architecture_dot(lang: str) -> str:
    labels = LABELS[lang]
    user = "{rank=same; dashboard; cli;}\n" + node(lang, "dashboard", "user") + node(lang, "cli", "user")
    agent = (
        "{rank=same; prompts; planner; toolkit; memory;}\n"
        + node(lang, "prompts", "agent")
        + node(lang, "planner", "agent")
        + node(lang, "toolkit", "agent")
        + node(lang, "memory", "agent")
    )
    services = (
        "{rank=same; vla; perception; env_service;}\n"
        + node(lang, "vla", "service")
        + node(lang, "perception", "service")
        + node(lang, "env_service", "service")
    )
    environments = (
        "{rank=same; sims; real;}\n"
        + node(lang, "sims", "env")
        + node(lang, "real", "env")
    )
    return f"""digraph architecture {{
  graph [rankdir=TB, splines=ortho, nodesep=0.50, ranksep=0.55, pad=0.20,
         newrank=true, fontname="{labels["font"]}", bgcolor="white",
         label="{labels["legend"]}", labelloc="b", labeljust="l", fontsize=10,
         fontcolor="#4b5563"];
  node [shape=box, style="rounded,filled", fontname="{labels["font"]}", fontsize=12,
        margin="0.16,0.09", penwidth=1.2];
  edge [color="#7c889a", penwidth=1.3, arrowsize=0.7, fontname="{labels["font"]}",
        fontsize=10.5, fontcolor="#4b5563"];

{cluster(lang, "user", "user", user)}
{cluster(lang, "agent", "agent", agent)}
{cluster(lang, "service", "service", services, labelloc="b")}
{cluster(lang, "env", "env", environments)}
  dashboard -> planner [xlabel="{labels["e_task"]}"];
  cli -> planner [xlabel="{labels["e_task"]}"];
  prompts -> planner [style=dashed];
  planner -> toolkit;
  toolkit -> memory [dir=both, xlabel="{labels["e_memory"]}"];
  toolkit -> vla [xlabel="{labels["e_action"]}"];
  toolkit -> perception;
  toolkit -> env_service [xlabel="{labels["e_state"]}"];
  env_service -> sims [dir=both, xlabel="{labels["e_connect"]}"];
  env_service -> real [dir=both, xlabel="{labels["e_connect"]}"];
}}
"""


def flow_dot(lang: str) -> str:
    labels = LABELS[lang]
    steps = ["f_cli", "f_session", "f_services", "f_loop", "f_end", "f_result"]
    body = "".join(node(lang, key, "agent") for key in steps)
    edges = (
        "  f_cli -> f_session;\n"
        "  f_session -> f_services;\n"
        f'  f_services -> f_loop [label="{labels["f_obs"][0]}"];\n'
        "  f_loop -> f_end;\n"
        "  f_end -> f_result;\n"
    )
    return f"""digraph flow {{
  graph [rankdir=TB, splines=spline, nodesep=0.30, ranksep=0.30, pad=0.15,
         fontname="{labels["font"]}", bgcolor="white"];
  node [shape=box, style="rounded,filled", fontname="{labels["font"]}", fontsize=12,
        margin="0.16,0.09", penwidth=1.2, fillcolor="{COLORS["agent"]["fill"]}",
        color="{COLORS["agent"]["border"]}"];
  edge [color="#7c889a", penwidth=1.3, arrowsize=0.7, fontname="{labels["font"]}",
        fontsize=10.5, fontcolor="#4b5563"];

{body}{edges}  {{rank=same; f_loop; f_fail;}}
  f_loop -> f_fail [dir=both, label="{labels["f_error"]}", style=dashed,
                    constraint=false];
  f_note [label="{labels["f_note"]}", shape=note, style="filled",
          fillcolor="#fff8e1", color="#e0c36b", fontsize=10, margin="0.12,0.08",
          penwidth=1.0];
  f_end -> f_note [style=dotted, arrowhead=none];
  f_fail [label=<<FONT POINT-SIZE="13"><B>{labels["f_fail"][0]}</B></FONT><BR/><FONT POINT-SIZE="10" COLOR="#4b5563">{labels["f_fail"][1]}</FONT>>, fillcolor="#fef3e2", color="#d9a05b"];
}}
"""


def render(name: str, source: str) -> None:
    dot_path = Path(__file__).with_name(f"{name}.dot")
    dot_path.write_text(source, encoding="utf-8")
    svg_path = OUTPUT / f"{name}.svg"
    subprocess.run(
        ["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)], check=True
    )
    print(f"wrote {svg_path.relative_to(DOCS)}")


def main() -> int:
    if shutil.which("dot") is None:
        print("Graphviz 'dot' is required: https://graphviz.org/download/", file=sys.stderr)
        return 1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "zh"):
        render(f"architecture-{lang}", architecture_dot(lang))
        render(f"execution-flow-{lang}", flow_dot(lang))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
