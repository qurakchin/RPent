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

"""Aggregate metrics for a geometry replay run."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

STATUSES = ("usable", "warning", "partial", "error", "missing")


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), fraction))


def _error_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p95": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p95": _percentile(values, 0.95),
        "max": float(array.max()),
    }


def _case_errors(result: dict[str, Any]) -> tuple[float | None, float | None]:
    payload = result["payload"]
    if payload.get("status") == "error" or "center" not in payload:
        return None, None
    reference = result["reference"]
    center = np.asarray(payload["center"]["value"], dtype=np.float64)
    extent = np.asarray(payload["extent"]["value"], dtype=np.float64)
    center_error = float(np.linalg.norm(center - np.asarray(reference["center"])))
    extent_error = float(np.linalg.norm(extent - np.asarray(reference["extent"])))
    return center_error, extent_error


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate outcomes, residual errors, and warning reasons."""
    status_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cases": 0, "center_errors": [], "extent_errors": [], "refused": 0}
    )
    center_errors: list[float] = []
    extent_errors: list[float] = []
    visible_refused = 0
    unexpected_accept = 0

    for result in results:
        payload = result["payload"]
        status = str(payload.get("status", "missing"))
        if payload.get("error"):
            status = "error"
        status_counts[status] += 1
        for warning in payload.get("warnings", []):
            warning_counts[str(warning.get("code"))] += 1
        group = groups[result["group"]]
        group["cases"] += 1
        center_error, extent_error = _case_errors(result)
        if status == "error":
            group["refused"] += 1
            if result["expect_visible"]:
                visible_refused += 1
        else:
            if not result["expect_visible"]:
                unexpected_accept += 1
            if center_error is not None:
                center_errors.append(center_error)
                group["center_errors"].append(center_error)
            if extent_error is not None:
                extent_errors.append(extent_error)
                group["extent_errors"].append(extent_error)

    by_group = {
        name: {
            "cases": data["cases"],
            "refused": data["refused"],
            "center_error": _error_stats(data["center_errors"]),
            "extent_error": _error_stats(data["extent_errors"]),
        }
        for name, data in sorted(groups.items())
    }
    return {
        "cases": len(results),
        "status_counts": {status: status_counts.get(status, 0) for status in STATUSES},
        "center_error": _error_stats(center_errors),
        "extent_error": _error_stats(extent_errors),
        "warning_counts": dict(sorted(warning_counts.items())),
        "visible_refused": visible_refused,
        "unexpected_accept": unexpected_accept,
        "by_group": by_group,
    }


__all__ = ["STATUSES", "summarize"]
