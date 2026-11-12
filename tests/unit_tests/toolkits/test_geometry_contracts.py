# Copyright 2026 The RPent Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Geometry implementation and evaluation contracts."""

from __future__ import annotations

import numpy as np

from rpent.tools.observation import Observation
from toolkits.geometry.core import (
    GeometryConfig,
    back_project,
    depth_region_mask,
    fit_mask,
    observation_world_xyz,
)
from toolkits.geometry.evaluation import corpus, experiment, metrics, replay
from toolkits.geometry.evaluation.references import reference_from_render
from toolkits.geometry.tool import GeometryToolConfig, estimate_geometry


def _clean_case() -> dict:
    return next(
        case
        for case in corpus.build_cases()
        if case["group"] == "clean"
    )


def _observation(rendered: corpus.RenderedCase) -> Observation:
    return Observation(
        view="synthetic",
        step=0,
        image_shape=rendered.rgb.shape[:2],
        rgb=rendered.rgb,
        depth=rendered.depth,
        intrinsics=rendered.intrinsics,
        world_from_camera=rendered.world_from_camera,
        camera_convention="opencv",
    )


def test_corpus_is_deterministic_and_covers_all_groups() -> None:
    first = corpus.build_cases()
    second = corpus.build_cases()

    assert corpus.fingerprint(first) == corpus.fingerprint(second)
    assert len(first) == 80
    assert {case["group"] for case in first} == {"clean", "noisy", "rejected"}
    assert sum(case["expect_visible"] for case in first) == 68
    for case in first:
        row, col = case["pixel"]
        assert 0 <= row < 120 and 0 <= col < 160


def test_back_projection_recovers_the_rendered_world_surface() -> None:
    rendered = corpus.render_case(_clean_case())

    world = back_project(
        rendered.depth,
        rendered.intrinsics,
        rendered.world_from_camera,
        convention="opencv",
    )

    np.testing.assert_allclose(world, rendered.exact_world_xyz, atol=1e-6)
    assert observation_world_xyz(
        {
            "image_shape": rendered.rgb.shape[:2],
            "depth": rendered.depth,
            "intrinsics": rendered.intrinsics,
            "world_from_camera": rendered.world_from_camera,
        }
    ).shape == (*rendered.rgb.shape[:2], 3)


def test_depth_region_mask_stops_at_the_target_boundary() -> None:
    case = _clean_case()
    rendered = corpus.render_case(case)

    mask = depth_region_mask(
        rendered.depth, rendered.rgb, tuple(case["pixel"])
    )

    assert mask[tuple(case["pixel"])]
    assert mask.sum() >= 40
    assert not (mask & ~rendered.exact_mask).any()


def test_fit_reports_the_analytic_surface_without_quality_warnings() -> None:
    rendered = corpus.render_case(_clean_case())
    reference = reference_from_render(rendered)

    fit = fit_mask(
        rendered.exact_world_xyz, rendered.exact_mask
    )

    np.testing.assert_allclose(fit.center, reference.center, atol=1e-9)
    np.testing.assert_allclose(fit.extent, reference.extent, atol=1e-9)
    assert fit.accepted is True
    assert fit.warnings == ()


def test_fit_refuses_a_mask_with_no_points() -> None:
    rendered = corpus.render_case(_clean_case())

    try:
        fit_mask(rendered.exact_world_xyz, np.zeros_like(rendered.exact_mask))
    except ValueError as error:
        assert "empty" in str(error)
    else:  # pragma: no cover - the contract requires refusal
        raise AssertionError("empty mask should not produce a fit")


def test_estimate_geometry_matches_the_frozen_reference() -> None:
    case = _clean_case()
    rendered = corpus.render_case(case)
    reference = reference_from_render(rendered)

    payload = estimate_geometry(
        _observation(rendered),
        pixel=tuple(case["pixel"]),
        quantities=("center", "extent"),
        segmenter=replay.FrozenMaskSegmenter(rendered.mask),
        config=GeometryToolConfig(),
    )

    assert payload["status"] in {"usable", "warning"}
    assert payload["fit_accepted"] is True
    assert np.linalg.norm(
        np.asarray(payload["center"]["value"]) - reference.center
    ) < 0.005
    assert np.linalg.norm(
        np.asarray(payload["extent"]["value"]) - reference.extent
    ) < 0.02
    assert payload["center"]["unit"] == "metre"
    assert payload["method"]["back_projection"] == "depth_and_calibration"
    assert payload["pixel_rc"] == case["pixel"]


def test_estimate_geometry_refuses_an_empty_segmentation() -> None:
    case = next(c for c in corpus.build_cases() if c["group"] == "rejected")
    rendered = corpus.render_case(case)

    payload = estimate_geometry(
        _observation(rendered),
        pixel=tuple(case["pixel"]),
        segmenter=replay.FrozenMaskSegmenter(rendered.mask),
    )

    assert payload["status"] == "error"
    assert payload["error"]["code"] == "target_not_segmented"


def test_estimate_geometry_reports_missing_and_invalid_inputs() -> None:
    rendered = corpus.render_case(_clean_case())
    observation = _observation(rendered)

    assert estimate_geometry(observation)["error"]["code"] == "missing_target"
    assert (
        estimate_geometry(observation, pixel=(500, 500))["error"]["code"]
        == "pixel_out_of_bounds"
    )
    assert (
        estimate_geometry(
            observation, target="the block", pixel=None
        )["error"]["code"]
        == "grounding_unavailable"
    )
    assert (
        estimate_geometry(
            observation, pixel=(0, 0), quantities=("volume",)
        )["error"]["code"]
        == "invalid_quantity"
    )


def test_replay_summary_covers_acceptance_and_refusal() -> None:
    cases = corpus.build_cases()[:16]
    summary = metrics.summarize(replay.replay(cases))

    assert summary["cases"] == 16
    assert summary["status_counts"]["error"] == sum(
        not case["expect_visible"] for case in cases
    )
    assert summary["visible_refused"] == 0
    assert summary["center_error"]["count"] > 0
    assert summary["center_error"]["max"] < 0.05


def test_fallback_manifest_records_excluded_refusal_cases() -> None:
    cases = corpus.build_cases()
    replayed = [case for case in cases if case["expect_visible"]]

    manifest = experiment.build_manifest(
        cases,
        quality=GeometryConfig(),
        use_frozen_mask=False,
        replayed=replayed,
    )

    assert manifest["corpus_cases"] == 80
    assert manifest["case_count"] == 68
    assert manifest["excluded_cases"] == 12
    assert "cannot infer" in manifest["exclusion_reason"]


def test_experiment_writes_a_complete_report(tmp_path) -> None:
    outcome = experiment.run(tmp_path, limit=4)

    report = (tmp_path / "report.md").read_text()
    assert "{{" not in report
    assert outcome["summary"]["cases"] == 4
    assert (tmp_path / "results.jsonl").read_text().count("\n") == 4


def test_fallback_segmenter_needs_no_model() -> None:
    case = _clean_case()
    rendered = corpus.render_case(case)

    payload = estimate_geometry(
        _observation(rendered),
        pixel=tuple(case["pixel"]),
        quantities=("center",),
        segmenter=None,
    )

    assert payload["status"] in {"usable", "warning"}
    assert payload["method"]["segmentation"] == "depth_region"
    assert payload["fit_accepted"] is True
