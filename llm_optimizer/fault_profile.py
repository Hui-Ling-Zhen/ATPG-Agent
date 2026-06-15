"""Build offline fault-to-fault learning profiles from Atalanta traces."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .runner import DEFAULT_RESULTS_DIR


@dataclass
class FaultStats:
    key: str
    fault_gate: str
    line: int
    stuck_at: int
    attempts: int = 0
    generated_patterns: int = 0
    extra_drops_total: int = 0
    backtracks_total: int = 0
    aborted: int = 0
    redundant: int = 0
    retained_patterns: int = 0
    is_stem: bool = False
    is_fanout: bool = False
    fanout_count: int = 0
    max_extra_drops: int = 0
    scores: dict[str, float] = field(default_factory=dict)

    def to_profile_row(self, *, base_backtrack_budget: int) -> dict[str, Any]:
        generated = max(self.generated_patterns, 1)
        attempts = max(self.attempts, 1)
        avg_extra_drops = self.extra_drops_total / generated
        avg_backtracks = self.backtracks_total / attempts
        abort_rate = self.aborted / attempts
        retained_rate = self.retained_patterns / generated
        stem_bonus = 1.0 if (self.is_stem or self.is_fanout or self.fanout_count > 1) else 0.0
        score = (
            self.scores["alpha"] * avg_extra_drops
            + self.scores["beta"] * retained_rate
            - self.scores["gamma"] * avg_backtracks
            - self.scores["delta"] * abort_rate
            + self.scores["epsilon"] * stem_bonus
        )

        if abort_rate > 0.5 and avg_extra_drops < 5:
            budget = max(1, base_backtrack_budget // 4)
        elif stem_bonus and avg_extra_drops >= 10:
            budget = max(base_backtrack_budget, int(base_backtrack_budget * 2))
        elif avg_backtracks > base_backtrack_budget and avg_extra_drops >= 10:
            budget = int(base_backtrack_budget * 1.5)
        elif avg_extra_drops >= 100:
            budget = max(1, base_backtrack_budget // 2)
        else:
            budget = base_backtrack_budget

        return {
            "key": self.key,
            "fault_gate": self.fault_gate,
            "line": self.line,
            "stuck_at": self.stuck_at,
            "attempts": self.attempts,
            "generated_patterns": self.generated_patterns,
            "avg_extra_drops": avg_extra_drops,
            "avg_backtracks": avg_backtracks,
            "abort_rate": abort_rate,
            "redundant_rate": self.redundant / attempts,
            "retained_rate": retained_rate,
            "stem_bonus": stem_bonus,
            "max_extra_drops": self.max_extra_drops,
            "score": score,
            "backtrack_budget": budget,
        }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _int(value: str | None) -> int:
    return int(float(value or 0))


def _fault_key(row: dict[str, str]) -> str:
    return f"{row.get('fault_gate', '')}|{row.get('line', '')}|{row.get('stuck_at', '')}"


def _retained_origins(pattern_trace: Path | None) -> set[int]:
    if pattern_trace is None or not pattern_trace.exists():
        return set()
    retained: set[int] = set()
    with pattern_trace.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if _truthy(row.get("retained")):
                retained.add(_int(row.get("origin_pattern_index")))
    return retained


def build_fault_profile(
    fault_trace: Path,
    pattern_trace: Path | None,
    *,
    benchmark: str,
    output: Path,
    alpha: float,
    beta: float,
    gamma: float,
    delta: float,
    epsilon: float,
    base_backtrack_budget: int,
) -> Path:
    retained = _retained_origins(pattern_trace)
    stats: dict[str, FaultStats] = {}
    weights = {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
        "epsilon": epsilon,
    }

    with fault_trace.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = _fault_key(row)
            if key not in stats:
                stats[key] = FaultStats(
                    key=key,
                    fault_gate=str(row.get("fault_gate", "")),
                    line=_int(row.get("line")),
                    stuck_at=_int(row.get("stuck_at")),
                    is_stem=_truthy(row.get("is_stem")),
                    is_fanout=_truthy(row.get("is_fanout")),
                    fanout_count=_int(row.get("fanout_count")),
                    scores=weights,
                )
            item = stats[key]
            item.attempts += 1
            item.backtracks_total += _int(row.get("backtracks"))
            result = str(row.get("result", "")).strip().lower()
            if result == "aborted":
                item.aborted += 1
            elif result == "redundant":
                item.redundant += 1

            pattern_index = _int(row.get("generated_pattern_index"))
            if pattern_index > 0:
                item.generated_patterns += 1
                extra_drops = _int(row.get("pattern_extra_drops"))
                item.extra_drops_total += extra_drops
                item.max_extra_drops = max(item.max_extra_drops, extra_drops)
                if pattern_index in retained:
                    item.retained_patterns += 1

    rows = [
        item.to_profile_row(base_backtrack_budget=base_backtrack_budget)
        for item in stats.values()
    ]
    rows.sort(key=lambda row: float(row["score"]), reverse=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": benchmark,
        "source_fault_trace": str(fault_trace),
        "source_pattern_trace": str(pattern_trace) if pattern_trace else None,
        "weights": weights,
        "base_backtrack_budget": base_backtrack_budget,
        "faults": rows,
    }
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault-trace", required=True, type=Path)
    parser.add_argument("--pattern-trace", type=Path)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON profile path. Defaults to results/profiles/<benchmark>_fault_profile.json.",
    )
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--beta", type=float, default=50.0)
    parser.add_argument("--gamma", type=float, default=0.2)
    parser.add_argument("--delta", type=float, default=25.0)
    parser.add_argument("--epsilon", type=float, default=10.0)
    parser.add_argument("--base-backtrack-budget", type=int, default=10)
    args = parser.parse_args()

    output = args.output or (
        DEFAULT_RESULTS_DIR / "profiles" / f"{Path(args.benchmark).stem}_fault_profile.json"
    )
    path = build_fault_profile(
        args.fault_trace,
        args.pattern_trace,
        benchmark=args.benchmark,
        output=output,
        alpha=args.alpha,
        beta=args.beta,
        gamma=args.gamma,
        delta=args.delta,
        epsilon=args.epsilon,
        base_backtrack_budget=args.base_backtrack_budget,
    )
    print(f"Wrote fault profile to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
