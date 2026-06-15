"""Candidate Atalanta CLI configurations for black-box optimization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CandidateConfig:
    """One Atalanta option set proposed for evaluation."""

    name: str
    options: tuple[str, ...]
    hypothesis: str
    source: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "options": list(self.options),
            "hypothesis": self.hypothesis,
            "source": self.source,
        }


DEFAULT_CANDIDATES: tuple[CandidateConfig, ...] = (
    CandidateConfig(
        name="default",
        options=(),
        hypothesis="Baseline Atalanta options for comparison.",
    ),
    CandidateConfig(
        name="no_compaction",
        options=("-N",),
        hypothesis="Disable test compaction to measure its effect on runtime and coverage.",
    ),
    CandidateConfig(
        name="reverse_only_compaction",
        options=("-c", "0"),
        hypothesis="Use reverse compaction only, avoiding shuffle overhead.",
    ),
    CandidateConfig(
        name="phase2_b10",
        options=("-B", "10"),
        hypothesis="Enable dynamic unique path sensitization with a moderate backtrack limit.",
    ),
    CandidateConfig(
        name="phase2_b20",
        options=("-B", "20"),
        hypothesis="Enable deeper phase-2 FAN search for hard aborted faults.",
    ),
    CandidateConfig(
        name="static_learning",
        options=("-L",),
        hypothesis="Use static learning to reduce repeated implication work.",
    ),
    CandidateConfig(
        name="phase2_b10_learning",
        options=("-B", "10", "-L"),
        hypothesis="Combine phase-2 search with static learning.",
    ),
    CandidateConfig(
        name="hope_sim",
        options=("-H",),
        hypothesis="Use HOPE three-valued fault simulation for different X behavior.",
    ),
    CandidateConfig(
        name="fill_zero",
        options=("-0",),
        hypothesis="Fill unspecified inputs with zero to reduce random variation.",
    ),
    CandidateConfig(
        name="fill_one",
        options=("-1",),
        hypothesis="Fill unspecified inputs with one to test deterministic X-fill bias.",
    ),
    CandidateConfig(
        name="fill_x",
        options=("-X",),
        hypothesis="Leave unspecified inputs as X and force HOPE simulation.",
    ),
    CandidateConfig(
        name="fill_random_seed_1",
        options=("-R", "-s", "1"),
        hypothesis="Use random fill with a fixed seed for reproducibility.",
    ),
)


COMPACTION_RUNTIME_LOCAL_CANDIDATES: tuple[CandidateConfig, ...] = (
    CandidateConfig(
        name="c1_learning",
        options=("-c", "1", "-L"),
        hypothesis="Local search center: reduce shuffle compaction effort while keeping static learning enabled.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c2_learning",
        options=("-c", "2", "-L"),
        hypothesis="Default compaction effort with static learning; checks whether learning alone explains the gain.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c1_phase2_b5_learning",
        options=("-c", "1", "-B", "5", "-L"),
        hypothesis="Combine the best compaction-learning direction with a shallow phase-2 retry budget.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c1_phase2_b10_learning",
        options=("-c", "1", "-B", "10", "-L"),
        hypothesis="Test whether moderate dynamic sensitization helps after reducing compaction effort.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c2_phase2_b5_learning",
        options=("-c", "2", "-B", "5", "-L"),
        hypothesis="Keep default shuffle limit and add shallow phase-2 search with learning.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c2_phase2_b10_learning",
        options=("-c", "2", "-B", "10", "-L"),
        hypothesis="Default compaction plus moderate phase-2 search and learning.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c1_no_learning",
        options=("-c", "1"),
        hypothesis="Ablation for c1_learning: isolate whether the runtime gain comes from compaction effort alone.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c2_no_learning",
        options=("-c", "2"),
        hypothesis="Default compaction without learning; anchors local search against default Atalanta behavior.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c1_phase2_b5",
        options=("-c", "1", "-B", "5"),
        hypothesis="Ablation for c1_phase2_b5_learning without static learning.",
        source="compaction_runtime_local",
    ),
    CandidateConfig(
        name="c1_phase2_b10",
        options=("-c", "1", "-B", "10"),
        hypothesis="Ablation for c1_phase2_b10_learning without static learning.",
        source="compaction_runtime_local",
    ),
)


CANDIDATE_SETS: dict[str, tuple[CandidateConfig, ...]] = {
    "default": DEFAULT_CANDIDATES,
    "compaction_runtime_local": COMPACTION_RUNTIME_LOCAL_CANDIDATES,
}


def get_default_candidates(limit: int | None = None) -> tuple[CandidateConfig, ...]:
    """Return the built-in candidate list, optionally truncated."""

    return get_candidate_set("default", limit=limit)


def get_candidate_set(name: str, *, limit: int | None = None) -> tuple[CandidateConfig, ...]:
    """Return a named built-in candidate set."""

    if name not in CANDIDATE_SETS:
        available = ", ".join(sorted(CANDIDATE_SETS))
        raise ValueError(f"Unknown candidate set {name!r}. Available sets: {available}")
    candidates = CANDIDATE_SETS[name]
    if limit is None:
        return candidates
    return candidates[:limit]


def load_candidates_json(path: str | Path) -> tuple[CandidateConfig, ...]:
    """Load candidate configs from a JSON file.

    Expected format is a list of objects with `name`, `options`, and optional
    `hypothesis` / `source` fields.
    """

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    candidates: list[CandidateConfig] = []
    for item in data:
        candidates.append(
            CandidateConfig(
                name=str(item["name"]),
                options=tuple(str(option) for option in item.get("options", [])),
                hypothesis=str(item.get("hypothesis", "")),
                source=str(item.get("source", "json")),
            )
        )
    return tuple(candidates)
