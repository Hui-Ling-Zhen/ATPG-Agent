"""Compare candidate Atalanta runs against a baseline CSV."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
CSV_FIELDS = (
    "candidate",
    "benchmark",
    "trial_index",
    "success",
    "timed_out",
    "coverage_below_baseline",
    "candidate_fault_coverage",
    "baseline_fault_coverage",
    "coverage_delta",
    "pattern_delta",
    "pattern_delta_pct",
    "runtime_delta",
    "runtime_delta_pct",
    "score_delta",
    "wins_benchmark",
    "candidate_patterns",
    "baseline_patterns",
    "candidate_runtime",
    "baseline_runtime",
    "candidate_score",
    "baseline_score",
    "adaptive_compaction_enabled",
    "adaptive_shuffle_limit",
    "adaptive_compaction_stopped_early",
    "adaptive_compaction_min_benefit",
    "run_id",
    "run_dir",
)
STATS_FIELDS = (
    "candidate",
    "benchmark",
    "trials",
    "successful_runs",
    "success_rate",
    "timeout_rate",
    "coverage_mean",
    "coverage_std",
    "baseline_coverage_mean",
    "coverage_delta_mean",
    "coverage_below_baseline",
    "patterns_mean",
    "patterns_std",
    "baseline_patterns_mean",
    "pattern_delta_mean",
    "pattern_delta_pct_mean",
    "runtime_mean",
    "runtime_std",
    "baseline_runtime_mean",
    "runtime_delta_mean",
    "runtime_delta_pct_mean",
    "score_mean",
    "score_std",
    "baseline_score_mean",
    "score_delta_mean",
    "adaptive_enabled_rate",
    "adaptive_shuffle_limit_mean",
    "adaptive_stopped_early_rate",
    "adaptive_min_benefit_mean",
    "wins_benchmark",
    "runtime_win",
    "stable_win",
)
SUMMARY_FIELDS = (
    "candidate",
    "benchmarks",
    "successful_runs",
    "success_rate_mean",
    "timeout_rate_mean",
    "coverage_below_baseline_count",
    "wins",
    "runtime_win_count",
    "stable_win_count",
    "average_score_delta_mean",
    "runtime_delta_mean",
    "runtime_delta_std",
    "pattern_delta_mean",
    "pattern_delta_std",
    "adaptive_enabled_rate_mean",
    "adaptive_shuffle_limit_mean",
    "adaptive_stopped_early_rate_mean",
)


def _read_csv(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _json_options(value: str) -> tuple[str, ...]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ()
    return tuple(str(item) for item in data)


def _baseline_by_benchmark(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _to_bool(row.get("success")):
            grouped[row["benchmark"]].append(row)

    baseline: dict[str, dict[str, Any]] = {}
    for benchmark, bench_rows in grouped.items():
        baseline[benchmark] = {
            "benchmark": benchmark,
            "fault_coverage": _mean_present(bench_rows, "fault_coverage"),
            "test_patterns": _mean_present(bench_rows, "test_patterns"),
            "runtime_seconds": _mean_present(bench_rows, "runtime_seconds"),
            "score": _mean_present(bench_rows, "score"),
        }
    return baseline


def _pct_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline in (None, 0):
        return None
    return (candidate - baseline) / baseline * 100.0


def compare_rows(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    baseline = _baseline_by_benchmark(baseline_rows)
    comparisons: list[dict[str, Any]] = []

    for row in candidate_rows:
        bench = row["benchmark"]
        base = baseline.get(bench)
        if base is None:
            continue

        cand_cov = _to_float(row.get("fault_coverage"))
        base_cov = _to_float(base.get("fault_coverage"))
        cand_patterns = _to_float(row.get("test_patterns"))
        base_patterns = _to_float(base.get("test_patterns"))
        cand_runtime = _to_float(row.get("runtime_seconds"))
        base_runtime = _to_float(base.get("runtime_seconds"))
        cand_score = _to_float(row.get("score"))
        base_score = _to_float(base.get("score"))

        coverage_delta = (
            cand_cov - base_cov if cand_cov is not None and base_cov is not None else None
        )
        pattern_delta = (
            cand_patterns - base_patterns
            if cand_patterns is not None and base_patterns is not None
            else None
        )
        runtime_delta = (
            cand_runtime - base_runtime
            if cand_runtime is not None and base_runtime is not None
            else None
        )
        score_delta = (
            cand_score - base_score if cand_score is not None and base_score is not None else None
        )
        coverage_below = bool(coverage_delta is not None and coverage_delta < -1e-6)
        wins = bool(
            _to_bool(row.get("success"))
            and not coverage_below
            and score_delta is not None
            and score_delta > 0
        )

        comparisons.append(
            {
                "candidate": row.get("candidate") or _candidate_name_from_options(row),
                "benchmark": bench,
                "trial_index": row.get("trial_index", ""),
                "success": row.get("success", ""),
                "timed_out": row.get("timed_out", ""),
                "coverage_below_baseline": coverage_below,
                "candidate_fault_coverage": cand_cov,
                "baseline_fault_coverage": base_cov,
                "coverage_delta": coverage_delta,
                "pattern_delta": pattern_delta,
                "pattern_delta_pct": _pct_delta(cand_patterns, base_patterns),
                "runtime_delta": runtime_delta,
                "runtime_delta_pct": _pct_delta(cand_runtime, base_runtime),
                "score_delta": score_delta,
                "wins_benchmark": wins,
                "candidate_patterns": cand_patterns,
                "baseline_patterns": base_patterns,
                "candidate_runtime": cand_runtime,
                "baseline_runtime": base_runtime,
                "candidate_score": cand_score,
                "baseline_score": base_score,
                "adaptive_compaction_enabled": row.get("adaptive_compaction_enabled", ""),
                "adaptive_shuffle_limit": row.get("adaptive_shuffle_limit", ""),
                "adaptive_compaction_stopped_early": row.get(
                    "adaptive_compaction_stopped_early",
                    "",
                ),
                "adaptive_compaction_min_benefit": row.get(
                    "adaptive_compaction_min_benefit",
                    "",
                ),
                "run_id": row.get("run_id", ""),
                "run_dir": row.get("run_dir", ""),
            }
        )

    stats = aggregate_repeated_trials(comparisons)
    return comparisons, stats, summarize_stats(stats)


def _candidate_name_from_options(row: dict[str, Any]) -> str:
    options = _json_options(str(row.get("options", "[]")))
    return " ".join(options) if options else "default"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def _mean_present(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [
        value
        for value in (_to_float(row.get(field)) for row in rows)
        if value is not None
    ]
    return _mean(values)


def _field_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [
        value
        for value in (_to_float(row.get(field)) for row in rows)
        if value is not None
    ]


def _bool_rate(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [row.get(field) for row in rows if row.get(field) not in (None, "")]
    if not values:
        return None
    return sum(1 for value in values if _to_bool(value)) / len(values)


def aggregate_repeated_trials(comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in comparisons:
        grouped[f"{row['candidate']}::{row['benchmark']}"].append(row)

    stats: list[dict[str, Any]] = []
    for rows in grouped.values():
        candidate = str(rows[0]["candidate"])
        benchmark = str(rows[0]["benchmark"])
        successful = [row for row in rows if _to_bool(row.get("success"))]
        trials = len(rows)
        coverage_values = _field_values(successful, "candidate_fault_coverage")
        pattern_values = _field_values(successful, "candidate_patterns")
        runtime_values = _field_values(successful, "candidate_runtime")
        score_values = _field_values(successful, "candidate_score")
        adaptive_limit_values = _field_values(successful, "adaptive_shuffle_limit")
        adaptive_min_benefit_values = _field_values(
            successful,
            "adaptive_compaction_min_benefit",
        )

        coverage_mean = _mean(coverage_values)
        patterns_mean = _mean(pattern_values)
        runtime_mean = _mean(runtime_values)
        score_mean = _mean(score_values)
        score_std = _std(score_values)

        baseline_coverage = _to_float(rows[0].get("baseline_fault_coverage"))
        baseline_patterns = _to_float(rows[0].get("baseline_patterns"))
        baseline_runtime = _to_float(rows[0].get("baseline_runtime"))
        baseline_score = _to_float(rows[0].get("baseline_score"))

        coverage_delta_mean = (
            coverage_mean - baseline_coverage
            if coverage_mean is not None and baseline_coverage is not None
            else None
        )
        pattern_delta_mean = (
            patterns_mean - baseline_patterns
            if patterns_mean is not None and baseline_patterns is not None
            else None
        )
        runtime_delta_mean = (
            runtime_mean - baseline_runtime
            if runtime_mean is not None and baseline_runtime is not None
            else None
        )
        score_delta_mean = (
            score_mean - baseline_score
            if score_mean is not None and baseline_score is not None
            else None
        )
        coverage_below = bool(coverage_delta_mean is not None and coverage_delta_mean < -1e-6)
        wins = bool(
            successful
            and not coverage_below
            and score_delta_mean is not None
            and score_delta_mean > 0
        )
        runtime_win = bool(
            successful
            and not coverage_below
            and runtime_delta_mean is not None
            and runtime_delta_mean < 0
        )
        stable_win = bool(
            successful
            and not coverage_below
            and score_mean is not None
            and baseline_score is not None
            and score_mean - score_std > baseline_score
        )

        stats.append(
            {
                "candidate": candidate,
                "benchmark": benchmark,
                "trials": trials,
                "successful_runs": len(successful),
                "success_rate": len(successful) / trials if trials else 0.0,
                "timeout_rate": sum(1 for row in rows if _to_bool(row.get("timed_out"))) / trials
                if trials
                else 0.0,
                "coverage_mean": coverage_mean,
                "coverage_std": _std(coverage_values),
                "baseline_coverage_mean": baseline_coverage,
                "coverage_delta_mean": coverage_delta_mean,
                "coverage_below_baseline": coverage_below,
                "patterns_mean": patterns_mean,
                "patterns_std": _std(pattern_values),
                "baseline_patterns_mean": baseline_patterns,
                "pattern_delta_mean": pattern_delta_mean,
                "pattern_delta_pct_mean": _pct_delta(patterns_mean, baseline_patterns),
                "runtime_mean": runtime_mean,
                "runtime_std": _std(runtime_values),
                "baseline_runtime_mean": baseline_runtime,
                "runtime_delta_mean": runtime_delta_mean,
                "runtime_delta_pct_mean": _pct_delta(runtime_mean, baseline_runtime),
                "score_mean": score_mean,
                "score_std": score_std,
                "baseline_score_mean": baseline_score,
                "score_delta_mean": score_delta_mean,
                "adaptive_enabled_rate": _bool_rate(
                    successful,
                    "adaptive_compaction_enabled",
                ),
                "adaptive_shuffle_limit_mean": _mean(adaptive_limit_values),
                "adaptive_stopped_early_rate": _bool_rate(
                    successful,
                    "adaptive_compaction_stopped_early",
                ),
                "adaptive_min_benefit_mean": _mean(adaptive_min_benefit_values),
                "wins_benchmark": wins,
                "runtime_win": runtime_win,
                "stable_win": stable_win,
            }
        )
    stats.sort(key=lambda row: (str(row["candidate"]), str(row["benchmark"])))
    return stats


def summarize_stats(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stats:
        grouped[str(row["candidate"])].append(row)

    summary: list[dict[str, Any]] = []
    for candidate, rows in sorted(grouped.items()):
        summary.append(
            {
                "candidate": candidate,
                "benchmarks": len(rows),
                "successful_runs": sum(int(row.get("successful_runs") or 0) for row in rows),
                "success_rate_mean": _mean(
                    [float(row["success_rate"]) for row in rows if row.get("success_rate") is not None]
                ),
                "timeout_rate_mean": _mean(
                    [float(row["timeout_rate"]) for row in rows if row.get("timeout_rate") is not None]
                ),
                "coverage_below_baseline_count": sum(
                    1 for row in rows if bool(row.get("coverage_below_baseline"))
                ),
                "wins": sum(1 for row in rows if bool(row.get("wins_benchmark"))),
                "runtime_win_count": sum(1 for row in rows if bool(row.get("runtime_win"))),
                "stable_win_count": sum(1 for row in rows if bool(row.get("stable_win"))),
                "average_score_delta_mean": _mean(
                    [float(row["score_delta_mean"]) for row in rows if row.get("score_delta_mean") is not None]
                ),
                "runtime_delta_mean": _mean(
                    [float(row["runtime_delta_mean"]) for row in rows if row.get("runtime_delta_mean") is not None]
                ),
                "runtime_delta_std": _std(
                    [float(row["runtime_delta_mean"]) for row in rows if row.get("runtime_delta_mean") is not None]
                ),
                "pattern_delta_mean": _mean(
                    [float(row["pattern_delta_mean"]) for row in rows if row.get("pattern_delta_mean") is not None]
                ),
                "pattern_delta_std": _std(
                    [float(row["pattern_delta_mean"]) for row in rows if row.get("pattern_delta_mean") is not None]
                ),
                "adaptive_enabled_rate_mean": _mean(
                    [float(row["adaptive_enabled_rate"]) for row in rows if row.get("adaptive_enabled_rate") is not None]
                ),
                "adaptive_shuffle_limit_mean": _mean(
                    [float(row["adaptive_shuffle_limit_mean"]) for row in rows if row.get("adaptive_shuffle_limit_mean") is not None]
                ),
                "adaptive_stopped_early_rate_mean": _mean(
                    [float(row["adaptive_stopped_early_rate"]) for row in rows if row.get("adaptive_stopped_early_rate") is not None]
                ),
            }
        )
    summary.sort(
        key=lambda row: (
            int(row["runtime_win_count"]),
            int(row["stable_win_count"]),
            int(row["wins"]),
            float(row["average_score_delta_mean"] or -1e9),
        ),
        reverse=True,
    )
    return summary


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _non_overwriting_path(path: Path) -> Path:
    if not path.exists():
        return path
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "comparisons",
    )
    args = parser.parse_args()

    comparisons, stats, summary = compare_rows(_read_csv(args.baseline), _read_csv(args.candidates))
    detail_path = _non_overwriting_path(args.output_dir / "candidate_comparison.csv")
    stats_path = _non_overwriting_path(args.output_dir / "candidate_stats.csv")
    summary_path = _non_overwriting_path(args.output_dir / "candidate_summary.csv")
    _write_csv(detail_path, comparisons, CSV_FIELDS)
    _write_csv(stats_path, stats, STATS_FIELDS)
    _write_csv(summary_path, summary, SUMMARY_FIELDS)
    print(f"Wrote comparison details to {detail_path}")
    print(f"Wrote repeated-trial stats to {stats_path}")
    print(f"Wrote comparison summary to {summary_path}")
    if summary:
        best = summary[0]
        print(
            "Best candidate: "
            f"{best['candidate']} stable_wins={best['stable_win_count']} "
            f"wins={best['wins']} avg_score_delta={best['average_score_delta_mean']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
