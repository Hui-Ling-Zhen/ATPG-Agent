"""Score ATPG runs by coverage, pattern count, and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScoreWeights:
    """Weights for the first black-box optimization objective."""

    coverage: float = 1.0
    pattern: float = 0.01
    runtime: float = 0.1
    invalid_penalty: float = 1_000.0
    coverage_tolerance: float = 1e-6


def score_record(
    record: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
    weights: ScoreWeights = ScoreWeights(),
) -> dict[str, Any]:
    """Add constraint and score fields to one parsed Atalanta record.

    Hard constraint: if a baseline is supplied, candidate coverage must not be
    lower than baseline coverage. Invalid candidates get a large negative score.
    """

    coverage = float(record.get("fault_coverage") or 0.0)
    patterns = int(record.get("test_patterns") or 0)
    runtime = float(record.get("runtime_seconds") or 0.0)

    baseline_coverage = None
    passes_constraints = bool(record.get("success", True))
    constraint_reason = ""
    if not passes_constraints:
        constraint_reason = record.get("error") or "run did not produce parseable metrics"
    if baseline is not None and baseline.get("fault_coverage") is not None:
        baseline_coverage = float(baseline["fault_coverage"])
        if passes_constraints and coverage + weights.coverage_tolerance < baseline_coverage:
            passes_constraints = False
            constraint_reason = (
                f"coverage {coverage:.3f} is below baseline {baseline_coverage:.3f}"
            )

    raw_score = (
        weights.coverage * coverage
        - weights.pattern * patterns
        - weights.runtime * runtime
    )
    score = raw_score if passes_constraints else raw_score - weights.invalid_penalty

    enriched = dict(record)
    enriched.update(
        {
            "score": score,
            "raw_score": raw_score,
            "passes_constraints": passes_constraints,
            "constraint_reason": constraint_reason,
            "baseline_fault_coverage": baseline_coverage,
            "score_formula": (
                f"{weights.coverage}*coverage - {weights.pattern}*patterns "
                f"- {weights.runtime}*runtime"
            ),
        }
    )
    return enriched
