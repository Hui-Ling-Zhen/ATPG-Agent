"""Run Atalanta candidate configurations across benchmarks."""

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

from llm_optimizer.candidates import (  # noqa: E402
    CandidateConfig,
    get_default_candidates,
    load_candidates_json,
)
from llm_optimizer.evaluator import score_record  # noqa: E402
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
    "candidate",
    "candidate_source",
    "hypothesis",
    "trial_index",
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


def _compact_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            normalized["options"] = json.dumps(normalized.get("options", []))
            for field in ("error", "constraint_reason", "hypothesis"):
                normalized[field] = _compact_text(normalized.get(field))
            writer.writerow({field: normalized.get(field, "") for field in CSV_FIELDS})


def run_candidates(
    benchmarks: tuple[str, ...],
    candidates: tuple[CandidateConfig, ...],
    output_csv: Path,
    *,
    timeout_seconds: int | None,
    trials: int,
) -> Path:
    if trials < 1:
        raise ValueError("trials must be >= 1")

    build_atalanta()

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        for bench in benchmarks:
            for trial_index in range(1, trials + 1):
                record = run_atalanta(
                    AtalantaRunConfig(
                        benchmark=benchmark_path(bench, DEFAULT_BENCHMARK_DIR),
                        label=f"candidate_{candidate.name}_trial{trial_index}",
                        options=candidate.options,
                        timeout_seconds=timeout_seconds,
                        metadata={
                            "experiment": "candidates",
                            "candidate": candidate.to_dict(),
                            "trial_index": trial_index,
                            "trials": trials,
                        },
                    )
                )
                scored = score_record(record)
                scored.update(
                    {
                        "candidate": candidate.name,
                        "candidate_source": candidate.source,
                        "hypothesis": candidate.hypothesis,
                        "trial_index": trial_index,
                    }
                )
                rows.append(scored)

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
        "--candidates-json",
        type=Path,
        help="Optional JSON file containing candidate configurations.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="Limit the built-in candidate set for quick smoke tests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "candidates" / "candidate_results.csv",
        help="Output CSV path. Existing files are not overwritten.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="Per-candidate timeout. Timed-out runs are recorded as failures.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Repeated trials per (candidate, benchmark) pair.",
    )
    args = parser.parse_args()

    if args.candidates_json:
        candidates = load_candidates_json(args.candidates_json)
    else:
        candidates = get_default_candidates(args.candidate_limit)

    output_path = run_candidates(
        tuple(args.benchmarks),
        candidates,
        args.output,
        timeout_seconds=args.timeout_seconds,
        trials=args.trials,
    )
    print(f"Wrote candidate results to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
