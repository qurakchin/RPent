.. _home:

Welcome to RPent
================

.. image:: https://raw.githubusercontent.com/RLinf/misc/main/pic/rpent_logo.png
   :alt: RPent
   :class: rpent-home-logo

RPent (Recursive Physical Agent) is an open-source framework for building embodied agents that accumulate experience and improve their behavior through interaction with the physical world. It supports different foundation models and integrates perception, reasoning, memory, execution, and self-evolution in a unified agent loop.

RPent is for robotics and embodied-AI researchers and engineers who want to compare foundation models, planners, and memory strategies under one evaluation harness, or run the same agent loop in simulation and on a real robot. After the Quick Start you will have installed RPent, run one LIBERO-PRO episode, and know where its result files are written.

.. button-ref:: rst_source/get_started/quickstart
   :ref-type: doc
   :color: primary
   :shadow:
   :expand:

   Install RPent and run your first task

.. grid:: 1 2 2 2
   :gutter: 3

   .. grid-item-card:: 1. Run something
      :link: rst_source/get_started/quickstart
      :link-type: doc

      Start with :doc:`Quick Start <rst_source/get_started/quickstart>`, then
      open :doc:`LIBERO <rst_source/simulators/libero>`,
      :doc:`RoboCasa365 <rst_source/simulators/robocasa>`,
      :doc:`RoboTwin <rst_source/simulators/robotwin>`, or
      :doc:`RoboDojo <rst_source/simulators/robodojo>`. Deploy on
      :doc:`Single-Arm Franka <rst_source/real_world_robots/franka>`,
      :doc:`Dual-Arm Franka <rst_source/real_world_robots/dual_franka>`, or
      :doc:`YAM <rst_source/real_world_robots/yam>`, and watch the
      :doc:`real-world demos <rst_source/real_world_demos/franka>`.

   .. grid-item-card:: 2. Compare results
      :link: rst_source/leaderboard/index
      :link-type: doc

      Read :doc:`Performance <rst_source/leaderboard/performance>`, the
      :doc:`Evaluation Protocol <rst_source/leaderboard/methodology>`, and
      :doc:`Time & Token Costs <rst_source/leaderboard/time-token-costs>`.

   .. grid-item-card:: 3. Configure the agent
      :link: rst_source/guides/memory
      :link-type: doc

      Configure :doc:`memory <rst_source/guides/memory>`,
      :doc:`tools <rst_source/guides/configure_primitives>`,
      :doc:`planner <rst_source/guides/configure_planner>`, the
      :doc:`CLI <rst_source/guides/cli>`, the
      :doc:`Dashboard <rst_source/guides/dashboard>`,
      :doc:`Flash mode <rst_source/guides/flash>`, the
      :doc:`data flywheel <rst_source/guides/flywheel>`, or
      :doc:`remote services <rst_source/guides/advanced_deployment>`.

   .. grid-item-card:: 4. Understand and extend
      :link: rst_source/development/architecture
      :link-type: doc

      Follow the :doc:`architecture <rst_source/development/architecture>`, then
      :doc:`add a robot <rst_source/development/add_robot>`, an
      :doc:`action primitive <rst_source/development/add_primitive>`, an
      :doc:`action model <rst_source/development/add_action_model>`, or a
      :doc:`planner <rst_source/development/add_planner>`. Background:
      :doc:`Harness VLA <rst_source/resources/harnessvla>`.

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
   Reproducing a Result <rst_source/leaderboard/reproduction>

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
