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

"""CLI and report writer for the geometry replay experiment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from toolkits.geometry.core import GeometryConfig
from toolkits.geometry.evaluation import corpus, metrics, replay

TEMPLATE_PATH = Path(__file__).with_name("report_template.md")


def _git_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_manifest(
    cases: list[dict[str, Any]],
    *,
    quality: GeometryConfig,
    use_frozen_mask: bool,
    replayed: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Describe exactly what was replayed and with which inputs.

    Refusal cases require an empty supplied mask; the model-free fallback
    segmenter cannot know that a target is absent, so fallback runs replay only
    the visible cases and record the exclusion here.
    """
    replayed = cases if replayed is None else replayed
    excluded = len(cases) - len(replayed)
    return {
        "corpus_version": corpus.CORPUS_VERSION,
        "corpus_fingerprint": corpus.fingerprint(cases),
        "renderer": "toolkits.geometry.evaluation.corpus.render_case",
        "corpus_cases": len(cases),
        "case_count": len(replayed),
        "excluded_cases": excluded,
        "exclusion_reason": (
            "Refusal cases need a supplied mask; the fallback segmenter cannot "
            "infer that the target is absent."
            if excluded
            else None
        ),
        "groups": {
            name: sum(1 for case in replayed if case["group"] == name)
            for name in sorted({case["group"] for case in replayed})
        },
        "mask_source": "frozen" if use_frozen_mask else "depth_region",
        "tool": "toolkits.geometry.tool.estimate_geometry",
        "quality": asdict(quality),
        "git_revision": _git_revision(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "not_a_baseline": (
            "Synthetic analytic RGB-D. Errors measure pipeline consistency with "
            "ideal geometry, not real-sensor accuracy or task success."
        ),
    }


def _format_error(stats: dict[str, Any], unit: str = "m") -> str:
    if not stats.get("count"):
        return "—"
    return (
        f"{stats['mean']:.4f} / {stats['median']:.4f} / "
        f"{stats['p95']:.4f} / {stats['max']:.4f} {unit}"
    )


def _status_table(summary: dict[str, Any]) -> str:
    rows = ["| status | cases |", "| --- | ---: |"]
    for status, count in summary["status_counts"].items():
        rows.append(f"| `{status}` | {count} |")
    return "\n".join(rows)


def _group_table(summary: dict[str, Any]) -> str:
    rows = [
        "| group | cases | refused | center error mean/median/p95/max | "
        "extent error mean/median/p95/max |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for name, data in summary["by_group"].items():
        rows.append(
            f"| `{name}` | {data['cases']} | {data['refused']} | "
            f"{_format_error(data['center_error'])} | "
            f"{_format_error(data['extent_error'])} |"
        )
    return "\n".join(rows)


def _warning_table(summary: dict[str, Any]) -> str:
    if not summary["warning_counts"]:
        return "No quality warnings were emitted."
    rows = ["| warning | count |", "| --- | ---: |"]
    for name, count in summary["warning_counts"].items():
        rows.append(f"| `{name}` | {count} |")
    return "\n".join(rows)


def _bad_cases(results: list[dict[str, Any]], limit: int = 20) -> str:
    lines: list[str] = []
    for result in results:
        if not result["expect_visible"]:
            continue
        payload = result["payload"]
        center_error = result["center_error_m"]
        if (
            payload.get("status") in {"error", "partial"}
            or payload.get("fit_accepted") is False
            or (center_error is not None and center_error > 0.02)
        ):
            reason = payload.get("error", {}).get("code") or ", ".join(
                result["warnings"]
            )
            lines.append(
                f"- `{result['case_id']}` ({result['group']}): status="
                f"`{result['status']}`, center_error="
                f"{'—' if center_error is None else f'{center_error:.4f} m'}, "
                f"reasons={reason or 'none'}"
            )
        if len(lines) >= limit:
            lines.append(f"- … truncated at {limit} cases")
            break
    return "\n".join(lines) if lines else "No case crossed the review threshold."


def render_report(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
) -> str:
    """Fill the checked-in report template with one run's evidence."""
    replacements = {
        "CORPUS_VERSION": str(manifest["corpus_version"]),
        "CORPUS_FINGERPRINT": str(manifest["corpus_fingerprint"]),
        "CORPUS_CASES": str(manifest["corpus_cases"]),
        "CASE_COUNT": str(manifest["case_count"]),
        "EXCLUDED_CASES": str(manifest["excluded_cases"]),
        "EXCLUSION_REASON": str(manifest["exclusion_reason"] or "none"),
        "MASK_SOURCE": str(manifest["mask_source"]),
        "GIT_REVISION": str(manifest["git_revision"] or "unknown"),
        "GENERATED_AT": str(manifest["generated_at"]),
        "QUALITY": json.dumps(manifest["quality"], sort_keys=True),
        "STATUS_TABLE": _status_table(summary),
        "GROUP_TABLE": _group_table(summary),
        "WARNING_TABLE": _warning_table(summary),
        "CENTER_ERROR": _format_error(summary["center_error"]),
        "EXTENT_ERROR": _format_error(summary["extent_error"]),
        "VISIBLE_REFUSED": str(summary["visible_refused"]),
        "UNEXPECTED_ACCEPT": str(summary["unexpected_accept"]),
        "BAD_CASES": _bad_cases(results),
    }
    template = TEMPLATE_PATH.read_text()
    for key, value in replacements.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def run(
    output_dir: Path,
    *,
    limit: int | None = None,
    use_frozen_mask: bool = True,
    quality: GeometryConfig | None = None,
    seed: int = corpus.DEFAULT_SEED,
) -> dict[str, Any]:
    """Replay the corpus and write manifest, raw results, and a report."""
    quality = quality or GeometryConfig()
    cases = corpus.build_cases(seed=seed)
    if limit is not None:
        cases = cases[:limit]
    replayed = (
        cases
        if use_frozen_mask
        else [case for case in cases if case["expect_visible"]]
    )
    results = replay.replay(
        replayed, quality=quality, use_frozen_mask=use_frozen_mask
    )
    summary = metrics.summarize(results)
    manifest = build_manifest(
        cases,
        quality=quality,
        use_frozen_mask=use_frozen_mask,
        replayed=replayed,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    corpus.write_manifest(cases, str(output_dir / "corpus_manifest.json"))
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True)
    )
    with (output_dir / "results.jsonl").open("w") as handle:
        for result in results:
            handle.write(json.dumps(result, default=str) + "\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)
    )
    (output_dir / "report.md").write_text(
        render_report(summary, manifest, results)
    )
    return {"summary": summary, "manifest": manifest, "results": results}


def main(argv: list[str] | None = None) -> int:
    """Run the geometry replay from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("geometry-eval-output"),
        help="Directory for manifest, raw results, and report.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--fallback-mask",
        action="store_true",
        help="Exercise the depth-region segmenter instead of frozen masks.",
    )
    parser.add_argument("--seed", type=int, default=corpus.DEFAULT_SEED)
    args = parser.parse_args(argv)
    outcome = run(
        args.output_dir,
        limit=args.limit,
        use_frozen_mask=not args.fallback_mask,
        seed=args.seed,
    )
    summary = outcome["summary"]
    print(
        f"cases={summary['cases']} "
        f"status={summary['status_counts']} "
        f"visible_refused={summary['visible_refused']}"
    )
    print(f"report={args.output_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_manifest", "main", "render_report", "run"]
