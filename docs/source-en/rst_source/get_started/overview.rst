Introduction to RPent
=====================

This page introduces the framework, its benchmark coverage, and the supported
platforms. Installation and a first run are in :doc:`quickstart`.

**RPent (Recursive Physical Agent)** is an open framework for building embodied
agents that continuously evolve through recursive interaction with the physical world.
Rather than prescribing a single foundation model, RPent provides a recursive agent
framework that harnesses heterogeneous intelligence, including perception, reasoning,
memory, execution, and self-evolution, into a unified physical agent.
Through continuous interaction, reflection, and adaptation, RPent enables physical agents
to acquire new capabilities and evolve beyond their initial design.

The name Pent is inspired by the Pentagram, whose five points symbolize the integration
of multimodal intelligence into a unified embodied agent. At its center, the infinity
symbol (∞) represents the endless recursive cycle of perception, reasoning,
execution, and self-evolution, through which intelligence continuously expands into the physical world.

.. image:: ../../../_static/img/architecture-en.svg
   :alt: RPent layers: user, agent, model and environment services, and environments
   :width: 100%

RPent is built upon three core design principles: **service-oriented, standardized, and composable**.
RPent enables capabilities to be deployed as reusable services,
connected through unified interfaces, and flexibly composed into diverse physical agents.
Together, these principles allow RPent to move beyond traditional robot control frameworks
and establish an agentic infrastructure for the physical world, where intelligence
is not only deployed, but continuously built, expanded, and evolved.

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
     - LingBot-VLA or Fast-WAM, dual-arm simulation tasks, and C2R reproduction.
   * - :doc:`RoboDojo <../simulators/robodojo>`
     - Dual-arm ARX-X5 manipulation in Isaac Sim, with VPP2 or Awomo05 policy actions.
   * - :doc:`Single-Arm Franka <../real_world_robots/franka>`
     - Hardware preparation, calibration, motion checks, and operation.
   * - :doc:`Dual-Arm Franka <../real_world_robots/dual_franka>`
     - Two-node deployment, operation, and exploration with an operator.
   * - :doc:`YAM <../real_world_robots/yam>`
     - Bimanual deployment with Pi0.5 actions, calibration, exploration, and task demos.
   * - :doc:`SO-101 <../real_world_robots/so101>`
     - Not yet integrated; no robot adapter is provided.

Choose ``api``, ``claude_code``, or ``codex`` for online planning. LIBERO also supports :doc:`Flash Mode <../guides/flash>` for executing stored plans. See :doc:`../guides/configure_planner` for model-service configuration.

Start with :doc:`quickstart`. See :doc:`../leaderboard/index` for reported results and resource costs, and :doc:`../resources/harnessvla` for the research background.

DreamZero is a planned WAM backend. It is not yet integrated and has no usage documentation.
