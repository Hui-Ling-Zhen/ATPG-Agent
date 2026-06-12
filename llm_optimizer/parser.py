"""Parse Atalanta outputs into structured experiment records."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_FLOAT = r"([0-9]+(?:\.[0-9]+)?)"
_INT = r"([0-9]+)"


def _search_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _search_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_atalanta_output(text: str) -> dict[str, Any]:
    """Parse the summary printed by Atalanta.

    The parser is intentionally tolerant because some options change whether
    compaction metrics are printed as a single count or before/after counts.
    """

    patterns = _search_int(r"Number of test patterns\s*:\s*" + _INT, text)
    patterns_before = _search_int(
        r"Number of test patterns before compaction\s*:\s*" + _INT,
        text,
    )
    patterns_after = _search_int(
        r"Number of test patterns after compaction\s*:\s*" + _INT,
        text,
    )

    return {
        "fault_coverage": _search_float(r"Fault coverage\s*:\s*" + _FLOAT, text),
        "test_patterns": patterns_after if patterns_after is not None else patterns,
        "test_patterns_before_compaction": patterns_before,
        "test_patterns_after_compaction": patterns_after,
        "collapsed_faults": _search_int(r"Number of collapsed faults\s*:\s*" + _INT, text),
        "redundant_faults": _search_int(
            r"Number of identified redundant faults\s*:\s*" + _INT,
            text,
        ),
        "aborted_faults": _search_int(r"Number of aborted faults\s*:\s*" + _INT, text),
        "backtrackings": _search_int(r"Total number of backtrackings\s*:\s*" + _INT, text),
        "runtime_seconds": _search_float(r"Total\s*:\s*" + _FLOAT + r"\s*Secs", text),
    }


def parse_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Parse a run directory produced by :mod:`llm_optimizer.runner`."""

    run_path = Path(run_dir)
    stdout_path = run_path / "stdout.txt"
    if not stdout_path.exists():
        raise FileNotFoundError(f"Missing stdout file: {stdout_path}")

    text = stdout_path.read_text(errors="replace")
    record = parse_atalanta_output(text)
    record["run_dir"] = str(run_path)
    return record
