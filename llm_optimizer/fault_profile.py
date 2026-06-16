"""Build offline fault-to-fault learning profiles from Atalanta traces."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
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
    group_id: int = -1
    group_size: int = 1
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

    def to_profile_row(
        self,
        *,
        base_backtrack_budget: int,
        group_score: float,
        group_budget: int,
        wait_score: float,
        representative_fault_score: float,
    ) -> dict[str, Any]:
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
            + self.scores["zeta"] * group_score
        )

        if wait_score > group_score and avg_extra_drops < 5:
            budget = 1
        elif abort_rate > 0.5 and avg_extra_drops < 5:
            budget = 1
        elif representative_fault_score >= group_score * 0.8 and group_score > 0:
            budget = group_budget
        elif avg_extra_drops < 2 and retained_rate < 0.25:
            budget = min(3, base_backtrack_budget)
        elif stem_bonus and avg_extra_drops >= 10:
            budget = max(base_backtrack_budget, min(20, group_budget))
        elif avg_backtracks > base_backtrack_budget and avg_extra_drops >= 10:
            budget = max(base_backtrack_budget, min(20, int(base_backtrack_budget * 1.5)))
        else:
            budget = min(base_backtrack_budget, group_budget)

        return {
            "key": self.key,
            "fault_gate": self.fault_gate,
            "line": self.line,
            "stuck_at": self.stuck_at,
            "group_id": self.group_id,
            "group_size": self.group_size,
            "attempts": self.attempts,
            "generated_patterns": self.generated_patterns,
            "avg_extra_drops": avg_extra_drops,
            "avg_backtracks": avg_backtracks,
            "abort_rate": abort_rate,
            "redundant_rate": self.redundant / attempts,
            "retained_rate": retained_rate,
            "stem_bonus": stem_bonus,
            "max_extra_drops": self.max_extra_drops,
            "group_score": group_score,
            "group_budget": group_budget,
            "wait_score": wait_score,
            "representative_fault_score": representative_fault_score,
            "score": score,
            "backtrack_budget": budget,
        }


@dataclass
class GroupStats:
    group_id: int
    group_size: int = 0
    attempts: int = 0
    generated_patterns: int = 0
    extra_drops_total: int = 0
    backtracks_total: int = 0
    aborted: int = 0
    retained_patterns: int = 0
    max_extra_drops: int = 0
    inbound_drops_from_other_groups: int = 0
    outbound_drops_to_other_groups: int = 0
    pair_distribution: Counter[int] = field(default_factory=Counter)
    faults: set[str] = field(default_factory=set)

    def add_fault_row(self, key: str, row: dict[str, str], *, retained: set[int]) -> None:
        self.faults.add(key)
        self.group_size = max(self.group_size, _int(row.get("fault_group_size")) or 1)
        self.attempts += 1
        self.backtracks_total += _int(row.get("backtracks"))
        if str(row.get("result", "")).strip().lower() == "aborted":
            self.aborted += 1
        pattern_index = _int(row.get("generated_pattern_index"))
        if pattern_index > 0:
            self.generated_patterns += 1
            extra_drops = _int(row.get("pattern_extra_drops"))
            self.extra_drops_total += extra_drops
            self.max_extra_drops = max(self.max_extra_drops, extra_drops)
            if pattern_index in retained:
                self.retained_patterns += 1

    def to_profile_row(self, weights: dict[str, float]) -> dict[str, Any]:
        generated = max(self.generated_patterns, 1)
        attempts = max(self.attempts, 1)
        avg_extra_drops = self.extra_drops_total / generated
        avg_backtracks = self.backtracks_total / attempts
        abort_rate = self.aborted / attempts
        retained_rate = self.retained_patterns / generated
        reuse_probability = self.generated_patterns / attempts
        wait_score = self.inbound_drops_from_other_groups / max(self.group_size, 1)
        score = (
            weights["group_alpha"] * avg_extra_drops
            + weights["group_beta"] * retained_rate
            + weights["group_eta"] * reuse_probability
            - weights["group_gamma"] * avg_backtracks
            - weights["group_delta"] * abort_rate
            - weights["group_wait_penalty"] * wait_score
        )
        if avg_extra_drops >= 100 or self.max_extra_drops >= 1000:
            group_budget = 20
        elif score > wait_score and avg_extra_drops >= 10:
            group_budget = 15
        elif wait_score > score:
            group_budget = 3
        else:
            group_budget = 10
        return {
            "group_id": self.group_id,
            "group_size": self.group_size or len(self.faults),
            "unique_faults": len(self.faults),
            "attempts": self.attempts,
            "generated_patterns": self.generated_patterns,
            "avg_extra_drops": avg_extra_drops,
            "avg_backtracks": avg_backtracks,
            "abort_rate": abort_rate,
            "retained_rate": retained_rate,
            "reuse_probability": reuse_probability,
            "max_extra_drops": self.max_extra_drops,
            "inbound_drops_from_other_groups": self.inbound_drops_from_other_groups,
            "outbound_drops_to_other_groups": self.outbound_drops_to_other_groups,
            "wait_score": wait_score,
            "group_budget": group_budget,
            "dropped_group_distribution": dict(self.pair_distribution.most_common(20)),
            "score": score,
        }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _int(value: str | None) -> int:
    return int(float(value or 0))


def _fault_key(row: dict[str, str]) -> str:
    return f"{row.get('fault_gate', '')}|{row.get('line', '')}|{row.get('stuck_at', '')}"


def _group_id(row: dict[str, str]) -> int:
    if row.get("fault_group_id") not in (None, ""):
        return _int(row.get("fault_group_id"))
    return _int(row.get("fault_index"))


def _retained_origins(pattern_trace: Path | None) -> set[int]:
    if pattern_trace is None or not pattern_trace.exists():
        return set()
    retained: set[int] = set()
    with pattern_trace.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if _truthy(row.get("retained")):
                retained.add(_int(row.get("origin_pattern_index")))
    return retained


def _apply_drop_reuse_trace(
    drop_trace: Path | None,
    group_stats: dict[int, GroupStats],
) -> dict[str, Counter[int]]:
    target_fault_distribution: dict[str, Counter[int]] = defaultdict(Counter)
    if drop_trace is None or not drop_trace.exists():
        return target_fault_distribution

    with drop_trace.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            target_group = _int(row.get("target_group_id"))
            dropped_group = _int(row.get("dropped_group_id"))
            target_fault_key = str(row.get("target_fault_key", ""))
            if target_group not in group_stats:
                group_stats[target_group] = GroupStats(group_id=target_group)
            if dropped_group not in group_stats:
                group_stats[dropped_group] = GroupStats(group_id=dropped_group)

            group_stats[target_group].pair_distribution[dropped_group] += 1
            target_fault_distribution[target_fault_key][dropped_group] += 1
            if dropped_group != target_group:
                group_stats[target_group].outbound_drops_to_other_groups += 1
                group_stats[dropped_group].inbound_drops_from_other_groups += 1

    return target_fault_distribution


def build_fault_profile(
    fault_trace: Path,
    pattern_trace: Path | None,
    drop_trace: Path | None,
    *,
    benchmark: str,
    output: Path,
    alpha: float,
    beta: float,
    gamma: float,
    delta: float,
    epsilon: float,
    zeta: float,
    group_alpha: float,
    group_beta: float,
    group_gamma: float,
    group_delta: float,
    group_eta: float,
    group_wait_penalty: float,
    base_backtrack_budget: int,
) -> Path:
    retained = _retained_origins(pattern_trace)
    stats: dict[str, FaultStats] = {}
    group_stats: dict[int, GroupStats] = {}
    weights = {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
        "epsilon": epsilon,
        "zeta": zeta,
        "group_alpha": group_alpha,
        "group_beta": group_beta,
        "group_gamma": group_gamma,
        "group_delta": group_delta,
        "group_eta": group_eta,
        "group_wait_penalty": group_wait_penalty,
    }

    with fault_trace.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = _fault_key(row)
            group_id = _group_id(row)
            if key not in stats:
                stats[key] = FaultStats(
                    key=key,
                    fault_gate=str(row.get("fault_gate", "")),
                    line=_int(row.get("line")),
                    stuck_at=_int(row.get("stuck_at")),
                    group_id=group_id,
                    group_size=_int(row.get("fault_group_size")) or 1,
                    is_stem=_truthy(row.get("is_stem")),
                    is_fanout=_truthy(row.get("is_fanout")),
                    fanout_count=_int(row.get("fanout_count")),
                    scores=weights,
                )
            if group_id not in group_stats:
                group_stats[group_id] = GroupStats(group_id=group_id)
            group_stats[group_id].add_fault_row(key, row, retained=retained)
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

    target_fault_distribution = _apply_drop_reuse_trace(drop_trace, group_stats)
    group_rows = [item.to_profile_row(weights) for item in group_stats.values()]
    group_rows.sort(key=lambda row: float(row["score"]), reverse=True)
    group_score_by_id = {
        int(row["group_id"]): float(row["score"])
        for row in group_rows
    }
    group_budget_by_id = {
        int(row["group_id"]): int(row["group_budget"])
        for row in group_rows
    }
    wait_score_by_id = {
        int(row["group_id"]): float(row["wait_score"])
        for row in group_rows
    }

    representative_by_fault: dict[str, float] = {}
    for item in stats.values():
        generated = max(item.generated_patterns, 1)
        attempts = max(item.attempts, 1)
        retained_rate = item.retained_patterns / generated
        local_score = (
            item.extra_drops_total / generated
            + 50.0 * retained_rate
            - 0.2 * (item.backtracks_total / attempts)
        )
        representative_by_fault[item.key] = local_score

    rows = [
        item.to_profile_row(
            base_backtrack_budget=base_backtrack_budget,
            group_score=group_score_by_id.get(item.group_id, 0.0),
            group_budget=group_budget_by_id.get(item.group_id, base_backtrack_budget),
            wait_score=wait_score_by_id.get(item.group_id, 0.0),
            representative_fault_score=representative_by_fault.get(item.key, 0.0),
        )
        for item in stats.values()
    ]
    rows.sort(key=lambda row: float(row["score"]), reverse=True)
    for row in rows:
        distribution = target_fault_distribution.get(str(row["key"]), Counter())
        row["dropped_group_distribution"] = dict(distribution.most_common(20))

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": benchmark,
        "source_fault_trace": str(fault_trace),
        "source_pattern_trace": str(pattern_trace) if pattern_trace else None,
        "source_drop_trace": str(drop_trace) if drop_trace else None,
        "weights": weights,
        "base_backtrack_budget": base_backtrack_budget,
        "groups": group_rows,
        "faults": rows,
    }
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault-trace", required=True, type=Path)
    parser.add_argument("--pattern-trace", type=Path)
    parser.add_argument("--drop-trace", type=Path)
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
    parser.add_argument(
        "--zeta",
        type=float,
        default=1.0,
        help="Weight for group-level reuse score in each fault score.",
    )
    parser.add_argument("--group-alpha", type=float, default=1.0)
    parser.add_argument("--group-beta", type=float, default=50.0)
    parser.add_argument("--group-gamma", type=float, default=0.2)
    parser.add_argument("--group-delta", type=float, default=25.0)
    parser.add_argument("--group-eta", type=float, default=10.0)
    parser.add_argument("--group-wait-penalty", type=float, default=1.0)
    parser.add_argument("--base-backtrack-budget", type=int, default=10)
    args = parser.parse_args()

    output = args.output or (
        DEFAULT_RESULTS_DIR / "profiles" / f"{Path(args.benchmark).stem}_fault_profile.json"
    )
    path = build_fault_profile(
        args.fault_trace,
        args.pattern_trace,
        args.drop_trace,
        benchmark=args.benchmark,
        output=output,
        alpha=args.alpha,
        beta=args.beta,
        gamma=args.gamma,
        delta=args.delta,
        epsilon=args.epsilon,
        zeta=args.zeta,
        group_alpha=args.group_alpha,
        group_beta=args.group_beta,
        group_gamma=args.group_gamma,
        group_delta=args.group_delta,
        group_eta=args.group_eta,
        group_wait_penalty=args.group_wait_penalty,
        base_backtrack_budget=args.base_backtrack_budget,
    )
    print(f"Wrote fault profile to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
