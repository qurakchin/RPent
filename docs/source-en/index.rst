.. _home:

Welcome to RPent
================

.. image:: https://raw.githubusercontent.com/RLinf/misc/main/pic/rpent_logo.png
   :alt: RPent
   :class: rpent-home-logo

RPent (Recursive Physical Agent) is an open-source framework for building embodied agents that accumulate experience and improve their behavior through interaction with the physical world. It supports different foundation models and integrates perception, reasoning, memory, execution, and self-evolution in a unified agent framework. Through ongoing interaction, agents reflect on and adjust their behavior, accumulate experience, and develop new capabilities beyond their initial design.

RPent is for robotics and embodied-AI researchers and engineers who want to compare foundation models, planners, and memory strategies under one evaluation harness, or run the same agent loop in simulation and on a real robot.

The navigation follows the reader's task: get started, run in simulation, deploy on a robot, watch a demo, compare results, configure a feature, or extend the framework.

The navigation follows the reader's task rather than the project's file layout:

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Section
     - Question it answers
   * - Get Started
     - What is RPent, and how do I complete one task?
   * - Simulators
     - Which simulated platform do I run, and how do I reproduce its results?
   * - Real-World Robots
     - How do I deploy and operate a physical robot safely?
   * - Real-World Demos
     - What does a task look like on the hardware?
   * - Leaderboard
     - How do the reported methods compare, and what do the numbers count?
   * - Guides
     - How do I configure memory, planners, tools, the CLI, the Dashboard, or remote services?
   * - Concepts & Development
     - How does RPent work inside, and how do I extend it?
   * - Resources
     - What does the paper report, how do I contribute, and what changed in v0.1?

.. button-ref:: rst_source/get_started/quickstart
   :ref-type: doc
   :color: primary
   :shadow:
   :expand:

   Install RPent and run your first task

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: Introduction to RPent
      :link: rst_source/get_started/overview
      :link-type: doc

      Learn how planning, perception, actions, and memory work together.

   .. grid-item-card:: Memory and Exploration
      :link: rst_source/guides/memory
      :link-type: doc

      Use published experience or build memory through exploration.

   .. grid-item-card:: Leaderboard
      :link: rst_source/leaderboard/index
      :link-type: doc

      Compare reported success rates, runtime, and token costs.

   .. grid-item-card:: Real-World Demos
      :link: rst_source/real_world_demos/franka
      :link-type: doc

      Watch dual-arm Franka tasks and follow the deployment guide.

   .. grid-item-card:: Extend RPent
      :link: rst_source/development/architecture
      :link-type: doc

      Understand the execution flow and add robots, tools, or planners.

Choose an environment: :doc:`LIBERO <rst_source/simulators/libero>`, :doc:`RoboCasa365 <rst_source/simulators/robocasa>`, or :doc:`RoboTwin <rst_source/simulators/robotwin>`. For robot deployment, see :doc:`Single-Arm Franka <rst_source/real_world_robots/franka>`, :doc:`Dual-Arm Franka <rst_source/real_world_robots/dual_franka>`, and :doc:`YAM <rst_source/real_world_robots/yam>`.

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Get Started

   Introduction to RPent <rst_source/get_started/overview>
   Quick Start <rst_source/get_started/quickstart>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Simulators

   LIBERO <rst_source/simulators/libero>
   RoboCasa365 <rst_source/simulators/robocasa>
   RoboTwin <rst_source/simulators/robotwin>
   RoboDojo <rst_source/simulators/robodojo>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Real-World Robots

   Single-Arm Franka <rst_source/real_world_robots/franka>
   Dual-Arm Franka <rst_source/real_world_robots/dual_franka>
   YAM <rst_source/real_world_robots/yam>
   SO-101 <rst_source/real_world_robots/so101>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Real-World Demos

   Dual-Arm Franka <rst_source/real_world_demos/franka>
   YAM <rst_source/real_world_demos/yam>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Leaderboard

   Performance <rst_source/leaderboard/performance>
   Evaluation Protocol <rst_source/leaderboard/methodology>
   Time & Token Costs <rst_source/leaderboard/time-token-costs>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Guides

   Memory and Exploration <rst_source/guides/memory>
   Action Primitives and Tools <rst_source/guides/configure_primitives>
   Planner Configuration <rst_source/guides/configure_planner>
   Command-Line Reference <rst_source/guides/cli>
   Interactive Usage <rst_source/guides/dashboard>
   Flash Mode <rst_source/guides/flash>
   Data Flywheel <rst_source/guides/flywheel>
   Remote Services and Parallel Runs <rst_source/guides/advanced_deployment>
   Troubleshooting <rst_source/guides/troubleshooting>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Concepts & Development

   Architecture and Execution <rst_source/development/architecture>
   Core Interfaces <rst_source/development/interfaces>
   Memory Design <rst_source/development/memory>
   Add a Robot or Simulator <rst_source/development/add_robot>
   Add an Action Primitive <rst_source/development/add_primitive>
   Add an Action Model <rst_source/development/add_action_model>
   Add a Planner <rst_source/development/add_planner>

.. toctree::
   :maxdepth: 2
   :includehidden:
   :titlesonly:
   :hidden:
   :caption: Resources

   Harness VLA <rst_source/resources/harnessvla>
   Contributing <rst_source/resources/contributing>
   v0.1 Release Notes <rst_source/resources/release_v0.1>

.. toctree::
   :maxdepth: 1
   :hidden:

   Action Model Reference <rst_source/development/action_model_reference>
   Robot Integration Reference <rst_source/development/add_robot_reference>
   Dual-Arm Franka Reference <rst_source/real_world_robots/dual_franka_reference>
   RoboDojo Reference <rst_source/simulators/robodojo_reference>
