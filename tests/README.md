# Test suite structure

RPent keeps fast, offline unit tests under `unit_tests/`, repository layout and
import-boundary checks under `tooling/`, and real-simulator / model integration
tests under `e2e_tests/`.

For CI workflows (simulator environment builds including `--no-cache`, GPU E2E
targets, and PR comment commands), see the Testing and CI guide in
[English](../docs/source-en/rst_source/development/testing.rst) or
[Chinese](../docs/source-zh/rst_source/development/testing.rst).
For simulator-specific prerequisites, checkpoints, and standalone smoke runs,
see the guides under `docs/source-en/rst_source/simulators/` (or `docs/source-zh/`).

## Directory layout

```text
tests/
├── README.md
├── conftest.py           # fixtures shared by more than one test directory
├── tooling/              # repository layout and import-boundary checks
│   ├── layout.py         # component manifest, import boundary, and lazy entry checks
│   └── run.sh            # bootstrap entry point for layout checks
├── e2e_tests/
│   ├── common.py         # shared assertions and runtime lifecycle helpers
│   ├── run_gpu_suite.sh  # clean-environment entry point for one robot stack
│   └── <robot>/          # simulator smoke, model component, and policy-chain suites
└── unit_tests/
    ├── rpent/            # tests mirroring the core package (including rpent/install/)
    ├── installs/         # contracts over checked-in component.toml manifests
    ├── tooling/          # tests for repository layout checks
    ├── robots/<name>/    # offline tests for one robot slice
    └── components/
        ├── models/       # model service tests
        └── tools/        # toolkit and utility tests
```

## Quick commands

Run the offline CPU unit test suite:

```bash
./rpent-install.sh install infra-unit_cpu --venv .venv-unit-cpu
.venv-unit-cpu/bin/python -m pytest tests/unit_tests -v
```

Run repository layout and import-boundary checks without an installed environment:

```bash
./tests/tooling/run.sh layout
```

Run one GPU E2E suite in a clean environment on a host with a dedicated NVIDIA GPU and EGL:

```bash
export CUDA_VISIBLE_DEVICES=<one-physical-GPU-ordinal>
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl

bash tests/e2e_tests/run_gpu_suite.sh \
  <target> \
  /path/to/new-output-dir \
  /path/to/new-venv-root
```
