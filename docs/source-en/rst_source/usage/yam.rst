YAM
===

RPent drives a physical dual-arm YAM through RLinf's real-world YAM runtime
(i2rt) and reads three RealSense RGBD cameras. The control machine is the only
CAN writer; the agent machine observes and dispatches primitives over RPC.

Install
-------

YAM reuses RLinf's real-world runtime and the i2rt SDK, so RPent has no
dedicated extra for it:

.. code-block:: bash

   uv sync --extra rlinf

The control machine also needs the RealSense bindings (``pyrealsense2``) and an
RLinf checkout that provides i2rt and the YAM backend. RPent locates that
checkout through ``RPENT_RLINF_ROOT`` (or ``RLINF_REPO_PATH``); see
:doc:`advanced_deployment`.

.. note::

   This installs only the Python side; it does **not** build the CAN and motor
   control stack. Before taking over, an operator must confirm that all four
   arms are supported, the emergency stop is reachable, the workspace and
   allowed range are defined, and other data-collection or teleoperation
   programs have exited cleanly and will not be restarted.

Site configuration
------------------

``robots/yam/config/example.yaml`` is the single configuration for the whole
rig: machine identity (follower CAN channels, three camera serials, hand-eye
extrinsics, work-surface geometry), primitive-control knobs, and the operator
receipt path. Copy it to a site config and replace each value:

* ``robot.*.channel`` must be a kernel SocketCAN interface name (``can0`` /
  ``can1`` in ``ip link``), not a logical alias.
* ``cameras`` is fixed at 640x480@30; the serials must match the cameras on
  site.
* ``extrinsics_path`` points at the JSON produced by hand-eye calibration. When
  it is ``null``, world-frame projection that depends on the wrist cameras is
  disabled.
* ``table_z`` (level surface) and ``table_surface`` (finite tilted surface) are
  mutually exclusive and drive the table-clearance check. With neither
  configured, every primitive motion is refused and only observation is
  allowed.
* ``operator_receipt_path`` is the local file where the operator writes
  ready/success/failure/abort receipts. Without it, startup is refused.

The task name, task language, seed, and step budget are command-line flags and
must match the agent side exactly; putting them in the YAML is an error, not an
override. The safety and robustness knobs in the ``control:`` section (slew,
timeouts, camera warm-up, table clearance, path spacing, stationary tolerance)
may be retuned on site; the packaged values are the defaults, and there is no
second copy in Python.

Start the env server
--------------------

The env server owns CAN and the cameras. Start it before the agent, and run it
exclusively — no other CAN program (data collection, teleoperation, hover
tools) may run at the same time:

.. code-block:: bash

   export RPENT_RLINF_ROOT=/path/to/RLinf
   python -m robots.yam.env_server \
     --robot-config /path/to/site.yaml \
     --task-name tabletop_cleanup --task-language 'put the cube in the bin' \
     --seed 0 --max-episode-steps 12000 \
     --transport http --host 127.0.0.1 --port 8110

``healthz`` and the static metadata do not open hardware; the first
observe/reset/render opens the three cameras, connects the motors, and outputs
holding torque. ``gripper_limits: null`` triggers end-to-end gripper
calibration, so the gripper must be empty and its travel clear. Exiting the
server may release torque; support all four arms before exiting.

Run an agent
------------

Start the agent with exactly the same task, seed, and step budget as the env
server:

.. code-block:: bash

   export RPENT_RLINF_ROOT=/path/to/RLinf
   python -m rpent.cli.main --robot yam --planner codex \
     --task-name tabletop_cleanup --task-language 'put the cube in the bin' \
     --seed 0 --max-episode-steps 12000 \
     --env-endpoint http://127.0.0.1:8110 --without-vla \
     --memory-profile local --memory-dir /path/to/memory/yam

YAM defaults to local memory (``default_memory_profile="local"``) and never
implicitly syncs a remote corpus. ``--without-vla`` means primitives only:
``pi05_act`` is not registered and the prompt states that it is unavailable.
Passing ``--vla-endpoint`` enables ``pi05_act``; keep chunks short on the real
robot.

Operator receipts
-----------------

Physical scene restoration and success verdicts belong to the on-site operator.
RPent does not auto-reset, clear faults, or re-enable the robot. Read the
episode ID with ``status`` first, then have the operator confirm and write
``start``:

.. code-block:: bash

   python -m robots.yam.operator_control --robot-config /path/to/site.yaml \
     --event status
   python -m robots.yam.operator_control --robot-config /path/to/site.yaml \
     --event start --episode-id ACTUAL_EPISODE_ID --note 'scene prepared and range confirmed'

``status`` calls observe, so use it only after the takeover is confirmed. When
Explore requires a human-restored scene, write ``--event ready`` after the
restoration actually happened; the agent's reset consumes that receipt. Never
write ready/success based on elapsed time, an agent claim, or a script
succeeding. Final ``success``/``failure``/``abort`` must likewise come from
real on-site feedback and be bound to the current episode ID.

Exploration
-----------

Append to the same command:

.. code-block:: bash

   --explore --explore-sessions 1 --explore-attempts-per-session 3

Explore follows the LIBERO organization: independent planner sessions, a
per-session attempt budget, failure attribution, and successful-recipe
induction. A real-robot reset only consumes the operator's ready receipt and
advances the episode ID; it does not rebuild the physical scene.

Memory and verdicts
-------------------

Explore drafts are written under ``memory/yam/_internal/inbox/<tag>/``, and
successful recipes are published through the shared MemoryManager. A tool's
local ``success=True`` only means the primitive ran; it cannot publish a
successful task memory. Only human success evidence for the current episode
produces a success recipe. Failed audits are retained and never presented as
validated skills.

Check ``environment_success`` in ``result.json`` for each run.
``planner_finish_request`` is only the agent's claim; its success field alone
does not establish real-robot success.

Tools and artifacts
-------------------

YAM exposes ``view_env_state``, ``sample_world_xyz``, ``query_world_map``,
``render``, ``move_to``, ``rotate_wrist``, ``set_gripper``, ``release``, and
``finish``. Connecting a VLA adds ``pi05_act``; exploration mode adds
``reset``.

The state and action layout is absolute ``qpos14``:
``[left_q0..q5, left_gripper, right_q0..q5, right_gripper]`` with joints in rad
and grippers as ``0=closed, 1=open``. The three views are ``top``, ``left``,
and ``right``; the latter two are wrist cameras. All xyz targets use
``left_base`` as the world frame, in metres, with **wxyz** pose quaternions.

Each observe returns one snapshot binding the three RGB views, aligned depth,
intrinsics, CV cam2world, image device times, and joint measurement times. The
three cameras are not hardware-synchronized, and host arrival time is not
exposure time. ``sample_world_xyz`` and ``query_world_map`` read persisted
same-frame depth projections; a stale frame or an invalid projection returns
invalid points instead of silently treating them as table targets.

Safety
------

Keep an operator at the emergency stop. A software stop only sets an event that
the execution loop honours at the next boundary; its ACK is not a physical
e-stop. The table check covers sampled TCP clearance only and is not collision
planning: links, self-collision, arm-to-arm collision, held objects, bags, and
bowls are not in the model. Re-observe after every grasp, lift, and release;
primitive success does not substitute for verifying object state.

``enable_auto_recovery=false`` means faults are never cleared and the robot is
never re-enabled during a run; both must be done by an on-site operator during
startup. RPent takes a per-channel process lock and checks for existing
SocketCAN subscriptions, but other programs do not share that lock, so
exclusivity remains the operator's responsibility.
