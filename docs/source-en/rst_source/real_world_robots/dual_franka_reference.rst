Dual-Arm Franka Reference
=========================

Tool surface, exploration, and Flash replay for the dual-arm deployment. Installation and the first run are in :doc:`dual_franka`.

**Page map:** tools and state artifacts → exploration mode → Flash replay.


Tools and State Artifacts
-------------------------

The extension exposes ``view_env_state``, ``view_camera_meta``,
``describe_dual_franka_setup``, ``back_project``, ``segment``, ``move_delta``,
``rotate_delta``, ``open_gripper``, ``close_gripper``,
``recover_joint_posture``, ``vla_right_grasp`` / ``vla_handoff`` /
``vla_left_place``, ``request_scene_reset``, and
``request_operator_verdict``. Each analytic motion selects exactly one arm,
``left`` or ``right``. ``back_project`` and ``segment`` use the configured
metric camera views; ``segment`` also requires a SAM3 client.
``recover_joint_posture`` re-commands each gripper's current open/closed state,
resets both arms to ``workspace.joint_reset_qpos``, and by default returns both
TCPs near their pre-recovery poses. Mutating tools capture per-arm state and
synchronized left-wrist, base, and right-wrist images in RPent's central
``EnvState``.

Exploration Mode
----------------

Append ``--explore`` to a task command to enable exploration. Set attempts per planner session
with ``--explore-attempts-per-session`` and session count with
``--explore-sessions``. Add ``--tui`` for terminal input or
``--dashboard`` for web interaction.

Each planner session begins with ``request_scene_reset``. Secure held objects,
restore the scene and reply ``done``. A successful reset and camera/state capture
start an attempt; a failed reset keeps motion blocked.
``--explore-attempts-per-session`` limits attempts within each session.
External ``--env-endpoint`` servers must advertise ``explicit_reset_only=True``
for both ordinary and exploration runs.

``request_operator_verdict`` asks for ``success``, ``failure``, ``continue`` or
``abort``, with optional notes. Its success/failure reply judges the current
attempt; ``continue`` resumes it and ``abort`` stops exploration. Further motion
clears the previous verdict. Closing terminal input also stops exploration.

With Codex/Claude and ``--tui``, use the displayed request ID, for example
``/operator <request-id> done`` or ``/operator <request-id> success object lifted``.
Other messages go to the agent. Without ``--tui``, answer the prompt
directly. With ``--dashboard``, use the commands below in the Dashboard message input.

Records and Memory
~~~~~~~~~~~~~~~~~~

Find camera and robot state in ``sessions/session_<NNN>/``, attempt boundaries in
``exploration.json`` and human feedback in ``operator_events.json``.
Failed attempts are retained; working notes are in
``<memory-dir>/_internal/inbox/<recipe_tag>/wip/``.

Memory merging is enabled by default. Normal completion merges valid ``global``
and ``task-family`` drafts, including lessons from failed attempts. Success also
saves a complete audit/recipe pair under ``task-specific``.
Use ``--no-auto-merge-memory`` to keep records without merging. Errors, aborts,
task replacement and Dashboard Session shutdown prevent merging. See
:doc:`../guides/memory` for the memory layout.

Exploration Commands
~~~~~~~~~~~~~~~~~~~~

In Codex/Claude terminal interaction (``--explore --tui``) or Dashboard
exploration, use:

* ``/success`` or ``/failure`` to end the task, rather than only judge an attempt.
  Success requires a confirmed reset. In the terminal, failure can end the task
  before the first reset; in Dashboard, answer a pending reset with ``/done`` or
  ``/abort`` first.
* ``/done`` to confirm a pending scene-reset request.
* ``/continue`` to answer a pending verdict and resume the attempt.
* ``/abort`` to stop the task, even if a camera is unavailable.

Enter each command on its own. Bare words such as ``success`` and ``failure``
are ordinary agent messages. Already-issued robot actions or RPCs may need to
return before the task can end; these commands are not an emergency stop.


Flash Replay
------------

Dual Franka uses the shared :ref:`Franka Flash workflow <franka-flash>`.
The example below uses task ``0``; for another task, change the ID in both the
generation and replay arguments. Generate with ``--robot dual_franka --task dual_franka_t0`` and replay with
``--robot dual_franka --planner flash --task-id 0``. Use a dual-arm plan and
robot configuration. Translation annotations name ``base``, ``d455``,
``left_wrist`` or ``right_wrist`` with depth and valid calibration.
Primitive moves specify ``arm: left`` or ``arm: right``; left-arm workspace
checks convert the shared right-base target into the left-base frame.
