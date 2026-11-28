Introduction to RPent
=====================

**RPent (Recursive Physical Agent)** is an open framework for embodied agents
that improve through recursive interaction with the physical world.
Rather than prescribing a single foundation model, RPent brings perception,
reasoning, memory, execution, and self-evolution into one architecture so agents
acquire new capabilities through interaction and reflection.

The name Pent draws from the five-pointed star: perception, reasoning, memory,
execution, and self-evolution. The infinity symbol (∞) at its center marks the
recursive loop that connects them.

.. image:: https://raw.githubusercontent.com/RLinf/misc/main/pic/rpent_framework.png
   :alt: RPent planning, perception, memory, and execution architecture
   :width: 100%

RPent follows three design principles: **service-oriented, standardized, and
composable**. Capabilities run as reusable services behind unified interfaces,
so you can swap models or compose them across simulators and real robots.

Leaderboard
-----------

Compare success rates on LIBERO, LIBERO-PRO, RoboCasa365 Target50, and RoboTwin
C2R. Rankings apply to the methods and evaluation coverage shown; see
:doc:`../leaderboard/index` for detailed results, configurations, and sources.

.. raw:: html

   <a href="../leaderboard/index.html">
     <img class="only-light" src="../../_static/leaderboard/leaderboard-en-light.svg" alt="RPent Leaderboard" width="100%">
     <img class="only-dark" src="../../_static/leaderboard/leaderboard-en-dark.svg" alt="RPent Leaderboard" width="100%">
   </a>

Choose a Platform
-----------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Platform
     - Documentation
   * - :doc:`LIBERO <../simulators/libero>`
     - Pi0.5, SAM3, and LIBERO / LIBERO-PRO runs and reproduction.
   * - :doc:`RoboCasa365 <../simulators/robocasa>`
     - RLDX-1, kitchen tasks, and Target50 reproduction.
   * - :doc:`RoboTwin <../simulators/robotwin>`
     - LingBot-VLA, dual-arm simulation tasks, and C2R reproduction.
   * - :doc:`RoboDojo <../simulators/robodojo>`
     - Dual-arm ARX-X5 manipulation in Isaac Sim, with VPP2 and Awomo05 policies.
   * - :doc:`RoboLab <../simulators/robolab>`
     - RLinf RoboLab Isaac Sim environment and policy deployment.
   * - :doc:`EFE <../simulators/efe>`
     - Embodied First Exam (EFE) tasks via Harbor with Skills or native actions.
   * - :doc:`Single-Arm Franka <../real_world_robots/franka>`
     - Hardware preparation, calibration, motion checks, and operation.
   * - :doc:`Dual-Arm Franka <../real_world_robots/dual_franka>`
     - Two-node deployment, operation, and exploration with an operator.
   * - :doc:`YAM <../real_world_robots/yam>`
     - Dual-arm two-machine deployment, manual skill checks, and task execution.
   * - :doc:`SO-101 <../real_world_robots/so101>`
     - Planned (not yet supported).

Choose ``api``, ``claude_code``, ``codex``, ``gemini_cli``, or ``opencode`` for online planning. LIBERO also supports :doc:`Flash Mode <../guides/flash>` for executing stored plans. See :doc:`../guides/configure_planner` for model-service configuration.

Start with :doc:`quickstart`. See :doc:`../leaderboard/index` for reported results and resource costs, and :doc:`../resources/harnessvla` for the research background.
For WAM backends such as Cosmos Policy, Fast-WAM, and UniWAM, see :doc:`../simulators/libero` and :doc:`../development/add_action_model`; DreamZero is on the roadmap and has no usage guide yet.
