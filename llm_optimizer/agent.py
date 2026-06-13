"""LLM interface for proposing the next Atalanta optimization candidates."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .candidates import CandidateConfig


DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_INSTRUCTIONS = """You propose Atalanta ATPG CLI configurations.

Return strict JSON only. Prefer this object shape:
{
  "candidates": [
    {
      "name": "short_snake_case_name",
      "options": ["-B", "10", "-L"],
      "hypothesis": "why this configuration might improve ATPG metrics"
    }
  ]
}

Optimization priorities:
1. Do not reduce fault coverage below the baseline.
2. Reduce test pattern count when coverage is preserved.
3. Reduce runtime when coverage and pattern count are competitive.
4. Prefer small, interpretable changes to Atalanta CLI options.
"""


ALLOWED_FLAGS = {
    "-0",
    "-1",
    "-A",
    "-H",
    "-L",
    "-N",
    "-R",
    "-X",
    "-Z",
}
NUMERIC_OPTIONS = {
    "-B",
    "-D",
    "-b",
    "-c",
    "-r",
    "-s",
}
ALLOWED_OPTION_PREFIXES = ALLOWED_FLAGS | set(NUMERIC_OPTIONS)
SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")
UNSAFE_TEXT = re.compile(r"[;&|`$<>]")


def build_candidate_prompt(
    *,
    baseline_csv: str | Path | None = None,
    baseline_dir: str | Path | None = None,
    candidate_summary_csv: str | Path | None = None,
    candidate_comparison_csv: str | Path | None = None,
    max_candidates: int = 5,
) -> str:
    """Build a prompt for an LLM proposal step."""

    baseline_text = ""
    if baseline_csv is not None:
        baseline_text = _read_text_limited(Path(baseline_csv))
    elif baseline_dir is not None:
        baseline_parts = []
        for path in sorted(Path(baseline_dir).glob("*.csv")):
            baseline_parts.append(f"\n--- {path.name} ---\n{_read_text_limited(path)}")
        baseline_text = "\n".join(baseline_parts)

    parts = [
        SYSTEM_INSTRUCTIONS,
        f"\nPropose at most {max_candidates} new candidate configurations.",
        "\nDo not propose shell commands, file edits, output-path options, or arbitrary filenames.",
        "Allowed Atalanta options are: "
        + ", ".join(sorted(ALLOWED_OPTION_PREFIXES))
        + ". Numeric options must be followed by an integer.",
        "\nUse the previous results to identify effective candidates, failed candidates, and benchmarks that are runtime- or pattern-sensitive.",
        "\nBaseline CSV:",
        baseline_text,
    ]
    if candidate_summary_csv is not None:
        parts.extend(
            [
                "\nPrevious candidate summary CSV:",
                _read_text_limited(Path(candidate_summary_csv)),
            ]
        )
    if candidate_comparison_csv is not None:
        parts.extend(
            [
                "\nPrevious candidate comparison CSV:",
                _read_text_limited(Path(candidate_comparison_csv)),
            ]
        )
    return "\n".join(parts)


def _read_text_limited(path: Path, *, max_chars: int = 40_000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."


def parse_candidate_json(text: str, *, source: str = "llm") -> tuple[CandidateConfig, ...]:
    """Validate strict JSON candidate proposals from an LLM response."""

    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Candidate proposal must be a JSON list")

    candidates: list[CandidateConfig] = []
    seen_names: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each candidate must be a JSON object")

        name = str(item["name"]).strip()
        options = tuple(str(option).strip() for option in item.get("options", []))
        hypothesis = str(item.get("hypothesis", "")).strip()
        if not name:
            raise ValueError("Candidate name cannot be empty")
        if not SAFE_NAME.match(name):
            raise ValueError(f"Candidate name is not safe: {name}")
        if name in seen_names:
            raise ValueError(f"Duplicate candidate name: {name}")
        seen_names.add(name)
        if not hypothesis:
            raise ValueError(f"Candidate {name} is missing a hypothesis")
        _validate_options(name, options)

        candidates.append(
            CandidateConfig(
                name=name,
                options=options,
                hypothesis=hypothesis,
                source=source,
            )
        )
    return tuple(candidates)


def _validate_options(name: str, options: tuple[str, ...]) -> None:
    index = 0
    while index < len(options):
        option = options[index]
        if UNSAFE_TEXT.search(option):
            raise ValueError(f"Candidate {name} option contains unsafe shell characters: {option}")
        if option in ALLOWED_FLAGS:
            index += 1
            continue
        if option in NUMERIC_OPTIONS:
            if index + 1 >= len(options):
                raise ValueError(f"Candidate {name} option {option} requires an integer")
            value = options[index + 1]
            if not re.fullmatch(r"-?\d+", value):
                raise ValueError(
                    f"Candidate {name} option {option} requires an integer, got {value}"
                )
            index += 2
            continue
        if option.startswith("-"):
            raise ValueError(f"Candidate {name} uses unsupported option: {option}")
        raise ValueError(f"Candidate {name} has an unexpected bare argument: {option}")


def save_candidates_json(candidates: tuple[CandidateConfig, ...], path: str | Path) -> Path:
    """Save validated candidate proposals for `run_candidates.py`."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([candidate.to_dict() for candidate in candidates], indent=2),
        encoding="utf-8",
    )
    return output_path


def call_openai_compatible_chat(
    prompt: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint."""

    resolved_api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to call the LLM")

    resolved_base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    resolved_model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    payload = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    request = urllib.request.Request(
        f"{resolved_base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed: HTTP {exc.code}: {detail}") from exc

    content = body["choices"][0]["message"]["content"]
    return _extract_candidate_json(content)


def _extract_candidate_json(content: str) -> str:
    """Accept either a raw JSON list or an object with a `candidates` list."""

    data = json.loads(content)
    if isinstance(data, list):
        return json.dumps(data)
    if isinstance(data, dict) and isinstance(data.get("candidates"), list):
        return json.dumps(data["candidates"])
    raise ValueError("LLM response must be a JSON list or an object with a candidates list")


def propose_candidates(
    *,
    baseline_dir: str | Path,
    candidate_summary_csv: str | Path,
    candidate_comparison_csv: str | Path | None,
    output_dir: str | Path,
    max_candidates: int,
    model: str | None = None,
    base_url: str | None = None,
    response_json: str | Path | None = None,
) -> Path:
    """Generate, validate, and save the next candidate JSON proposal."""

    prompt = build_candidate_prompt(
        baseline_dir=baseline_dir,
        candidate_summary_csv=candidate_summary_csv,
        candidate_comparison_csv=candidate_comparison_csv,
        max_candidates=max_candidates,
    )
    if response_json is not None:
        candidate_json = Path(response_json).read_text(encoding="utf-8")
    else:
        candidate_json = call_openai_compatible_chat(
            prompt,
            model=model,
            base_url=base_url,
        )

    candidates = parse_candidate_json(candidate_json, source="llm")
    if len(candidates) > max_candidates:
        raise ValueError(
            f"LLM returned {len(candidates)} candidates, max allowed is {max_candidates}"
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(output_dir) / f"proposal_{timestamp}.json"
    return save_candidates_json(candidates, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "baseline",
        help="Directory containing baseline CSV files.",
    )
    parser.add_argument(
        "--candidate-summary",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "comparisons" / "candidate_summary.csv",
    )
    parser.add_argument(
        "--candidate-comparison",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "comparisons" / "candidate_comparison.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "proposals",
    )
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument(
        "--response-json",
        type=Path,
        help="Validate/save a provided LLM JSON response instead of calling the API.",
    )
    args = parser.parse_args()

    comparison_path = args.candidate_comparison if args.candidate_comparison.exists() else None
    output_path = propose_candidates(
        baseline_dir=args.baseline_dir,
        candidate_summary_csv=args.candidate_summary,
        candidate_comparison_csv=comparison_path,
        output_dir=args.output_dir,
        max_candidates=args.max_candidates,
        model=args.model,
        base_url=args.base_url,
        response_json=args.response_json,
    )
    print(f"Wrote LLM proposal to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
