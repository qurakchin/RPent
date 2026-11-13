添加规划器
===============

规划器负责接收提示词、选择工具并处理工具结果。接入自定义规划器时，继承 ``Planner`` 并实现 ``solve``，然后在构建入口和 CLI 选项中注册。

.. page-head::
   :for: 要新增规划器后端的开发者
   :outcome: 实现 ``solve``、注册后端，并验证工具调用与运行限制
   :read-when: 新增规划后端，或修改规划器契约时
   :skip-when: 只配置已有后端；见 :doc:`../guides/configure_planner`

**本文结构：** 何时新增规划器 → 前置条件 → 实现 ``solve`` → 注册后端 →
运行时接线 → 测试 → 排查与下一步。

何时新增规划器
--------------

当现有 ``api``、``claude_code`` 或 ``codex`` 后端无法表达某个模型 SDK 或智能体循环时，才新增规划器。工具定义、提示词渲染和环境都不变：规划器只把提示词与工具 schema 转成模型请求，并执行模型返回的工具调用。如果只想换模型、服务地址或推理强度，请配置已有后端。

前置条件
--------

- 已安装基础依赖的 RPent 检出，以及测试 extra（``pip install -e ".[test]"``）。
- 先读 ``rpent/planner/base.py`` 中的 ``Planner`` 和 ``PlannerResult``、``rpent/planner/api_loop.py`` 中的完整后端，以及 ``rpent/tools/toolkit.py`` 中的 ``list_tools`` 和 ``execute_tool``。
- 要验证真实连接时，准备模型端点和凭据；离线测试不需要。

实现 ``solve``
--------------

以下为接口示意，省略了模型请求和工具循环，不能直接作为实现运行。完整示例可参考 ``rpent/planner/api_loop.py``。

.. code-block:: python

   # rpent/planner/my_planner.py
   from rpent.planner.base import Planner, PlannerResult

   class MyPlanner(Planner):
       def solve(
           self,
           *,
           system_prompt,
           user_message,
           toolkit,
           max_turns,
           input_queue=None,
           dashboard_interaction=None,
       ):
           tools = toolkit.list_tools()
           # 使用 system_prompt、user_message 和 tools 调用模型。
           # 每次工具调用都通过下面的接口执行：
           tool_result = toolkit.execute_tool(tool_name, arguments)
           ...
           return PlannerResult(
               finish_result=finish_result,
               messages=messages,
               stats=stats,
               error=error,
           )

任何规划器都必须：

1. 接收已经渲染好的 ``system_prompt`` 和 ``user_message``。
2. 从 ``toolkit.list_tools()`` 取得工具的 ``name``、``description`` 和 ``input_schema``，并通过 ``toolkit.execute_tool(name, arguments)`` 执行工具。
3. 将 ``ToolResult.to_text()`` 的文本和 ``ToolResult.images`` 中的 PNG 字节转换成模型 SDK 所需的格式。
4. 识别 ``ToolResult.data.get("_finish")``，并按 ``max_turns`` 等限制终止循环。
5. 返回包含结束状态、消息、统计信息和可选错误的 ``PlannerResult``。

RPent 的工具定义和提示词渲染流程保持不变，因此新增规划器不需要修改工具或环境服务。

注册后端
--------

在 ``rpent/planner/base.py:build_planner`` 中添加构建分支，并在 ``rpent/cli/main.py`` 的 ``--planner`` 选项中加入名称。新分支负责解析凭据和超时默认值，位置与现有分支保持一致。

运行时接线
----------

- **Dashboard**：规划器支持与现有后端相同的交互回调时，把它加入 Dashboard 的规划器选择。
- **连接诊断**：把后端加入 ``rpent/planner/check.py``，让 ``rpent-check-llm --planner <name>`` 能检查凭据。
- **交互**：实现你支持的打断和输入路径（``input_queue``、``dashboard_interaction``）；只有 CLI 不为该后端提供这些入口时，才可以不实现。
- **限制**：使用运行器传入的 ``max_turns`` 和超时，不要从全局状态读取。

测试
----

验证工具调用、文本和图像返回、``finish``、轮数上限、错误结果，以及你支持的中断和交互路径。复用 ``tests/unit_tests/rpent/planner/`` 中的测试模式；真实模型连接需要单独验证。

排查与下一步
------------

- **工具调用没有到达环境**：确认模型收到了 ``list_tools()`` 的 schema，并且参数原样传给了 ``execute_tool``。
- **运行忽略 ``finish``**：在下一轮模型请求前读取 ``ToolResult.data.get("_finish")``，直接返回 ``PlannerResult``，不要继续循环。
- **图像缺失**：``ToolResult.images`` 是 PNG 字节；请按 SDK 的内容格式编码，不要传文件路径。
- **运行不停止**：在每次循环（包括重试）都应用 ``max_turns``。

下一步：在 :doc:`add_primitive` 中为规划器添加可调用工具，或阅读 :doc:`architecture` 了解接口。
