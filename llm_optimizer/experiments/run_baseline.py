"""Run baseline Atalanta measurements for a small benchmark set."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm_optimizer.evaluator import score_record
from llm_optimizer.runner import (  # noqa: E402
    DEFAULT_BENCHMARK_DIR,
    DEFAULT_RESULTS_DIR,
    AtalantaRunConfig,
    benchmark_path,
    build_atalanta,
    run_atalanta,
)


DEFAULT_BENCHMARKS = ("pcitc", "destc", "DMAtc")
CSV_FIELDS = (
    "run_id",
    "benchmark",
    "options",
    "returncode",
    "success",
    "timed_out",
    "error",
    "fault_coverage",
    "test_patterns",
    "test_patterns_before_compaction",
    "test_patterns_after_compaction",
    "collapsed_faults",
    "redundant_faults",
    "aborted_faults",
    "backtrackings",
    "runtime_seconds",
    "score",
    "raw_score",
    "passes_constraints",
    "constraint_reason",
    "run_dir",
)


def _non_overwriting_path(path: Path) -> Path:
    if not path.exists():
        return path
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            normalized["options"] = json.dumps(normalized.get("options", []))
            for field in ("error", "constraint_reason"):
                value = str(normalized.get(field, ""))
                value = " ".join(value.split())
                if len(value) > 240:
                    value = value[:237] + "..."
                normalized[field] = value
            writer.writerow({field: normalized.get(field, "") for field in CSV_FIELDS})


def run_baseline(
    benchmarks: tuple[str, ...],
    output_csv: Path,
    *,
    timeout_seconds: int | None,
) -> Path:
    build_atalanta()

    rows: list[dict[str, Any]] = []
    for bench in benchmarks:
        record = run_atalanta(
            AtalantaRunConfig(
                benchmark=benchmark_path(bench, DEFAULT_BENCHMARK_DIR),
                label="baseline",
                options=(),
                timeout_seconds=timeout_seconds,
                metadata={"experiment": "baseline"},
            )
        )
        rows.append(score_record(record))

    output_path = _non_overwriting_path(output_csv)
    _write_csv(output_path, rows)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        default=list(DEFAULT_BENCHMARKS),
        help="Benchmark names with or without the .bench suffix.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "baseline" / "baseline.csv",
        help="Output CSV path. Existing files are not overwritten.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Per-benchmark timeout. Timed-out runs are recorded as failures.",
    )
    args = parser.parse_args()

    output_path = run_baseline(
        tuple(args.benchmarks),
        args.output,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"Wrote baseline results to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
