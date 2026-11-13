Add a Planner
=============

A planner receives prompts, chooses tools, and consumes their results. To add
one, subclass ``Planner``, implement ``solve``, and expose it through the
construction path and CLI choices.

.. page-head::
   :for: Developers adding a planner backend
   :outcome: You can implement ``solve``, register the backend, and validate tool dispatch and limits
   :read-when: You are adding a planning backend or changing the planner contract
   :skip-when: You only configure an existing backend; see :doc:`../guides/configure_planner`

**Page map:** when to add one → prerequisites → implement ``solve`` → register
the backend → wire the runtime → test → troubleshooting and next steps.

When to add a planner
---------------------

Add a planner when a model SDK or agent loop cannot be expressed through the
existing ``api``, ``claude_code``, or ``codex`` backends. Tool definitions,
prompt rendering, and the environment stay unchanged: a planner only turns
prompts and tool schemas into model calls and executes the returned tool calls.
If you only need to change the model, base URL, or reasoning effort, configure
an existing backend instead.

Prerequisites
-------------

- An RPent checkout with its base dependencies installed, and the test extra
  (``pip install -e ".[test]"``) for the offline planner tests.
- Reads: ``rpent/planner/base.py`` for ``Planner`` and ``PlannerResult``,
  ``rpent/planner/api_loop.py`` for a complete backend, and
  ``rpent/tools/toolkit.py`` for ``list_tools`` and ``execute_tool``.
- A model endpoint and credentials, if you will test a real connection. The
  offline tests do not require one.

Implement ``solve``
-------------------

The following interface sketch omits model requests and the tool loop; it is
not a runnable implementation. See ``rpent/planner/api_loop.py`` for a
complete backend.

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
           # Call the model with system_prompt, user_message, and tools.
           # Execute each tool call through this interface:
           tool_result = toolkit.execute_tool(tool_name, arguments)
           ...
           return PlannerResult(
               finish_result=finish_result,
               messages=messages,
               stats=stats,
               error=error,
           )

Any planner must:

1. Accept the rendered ``system_prompt`` and ``user_message``.
2. Read each tool's ``name``, ``description``, and ``input_schema`` from
   ``toolkit.list_tools()`` and execute tools with
   ``toolkit.execute_tool(name, arguments)``.
3. Convert ``ToolResult.to_text()`` and PNG bytes in ``ToolResult.images`` to
   the format expected by the model SDK.
4. Detect ``ToolResult.data.get("_finish")`` and stop according to
   ``max_turns`` and any other limits.
5. Return a ``PlannerResult`` containing the finish state, messages,
   statistics, and an optional error.

Because the RPent tool schemas and prompt-rendering path stay the same, adding
a planner does not require changes to tools or environment servers.

Register the backend
--------------------

Add a construction branch in ``rpent/planner/base.py:build_planner`` and a CLI
choice in ``rpent/cli/main.py``. The branch resolves credentials and timeout
defaults for the new backend; keep them in the same place as the existing
branches.

Wire the runtime
----------------

- **Dashboard.** Expose the planner in the Dashboard's planner selection if it
  supports the same interaction callbacks as the existing backends.
- **Connection diagnostics.** Add the backend to ``rpent/planner/check.py`` so
  ``rpent-check-llm --planner <name>`` can verify credentials.
- **Interaction.** Implement the interruption and input paths you support
  (``input_queue``, ``dashboard_interaction``); leaving them unimplemented is
  fine only if the CLI does not offer them for this backend.
- **Limits.** Apply ``max_turns`` and the planner timeout passed by the
  runner; do not read them from global state.

Test
----

Verify tool dispatch, text and image results, ``finish``, turn limits, errors,
and the interruption and interaction paths you support. Reuse test patterns in
``tests/unit_tests/rpent/planner/``. Validate real model connectivity
separately.

Troubleshooting and next steps
------------------------------

- **No tool calls reach the environment.** Check that the model receives the
  schemas from ``list_tools()`` and that tool arguments are passed unchanged to
  ``execute_tool``.
- **The run ignores ``finish``.** Read ``ToolResult.data.get("_finish")``
  before the next model turn, and return ``PlannerResult`` instead of looping.
- **Images are missing.** ``ToolResult.images`` holds PNG bytes; encode them in
  the SDK's expected content format rather than passing file paths.
- **The run never stops.** Apply ``max_turns`` on every loop iteration,
  including retries.

Next: add the tools the planner can call in :doc:`add_primitive`, or review the
interface in :doc:`architecture`.
