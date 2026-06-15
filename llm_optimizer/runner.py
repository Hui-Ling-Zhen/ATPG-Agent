"""Compile and run the Atalanta backend."""

from __future__ import annotations

import json
import csv
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .parser import parse_atalanta_output


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE_DIR = REPO_ROOT / "atalanta-core"
DEFAULT_BENCHMARK_DIR = REPO_ROOT / "benchmarks"
DEFAULT_RESULTS_DIR = REPO_ROOT / "results"


@dataclass(frozen=True)
class AtalantaRunConfig:
    """Configuration for one black-box Atalanta run."""

    benchmark: Path
    options: tuple[str, ...] = ()
    run_id: str | None = None
    core_dir: Path = DEFAULT_CORE_DIR
    results_dir: Path = DEFAULT_RESULTS_DIR
    label: str = "run"
    create_log: bool = True
    timeout_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def build_atalanta(core_dir: str | Path = DEFAULT_CORE_DIR) -> Path:
    """Compile the Atalanta binary and return its path."""

    core_path = Path(core_dir).resolve()
    completed = subprocess.run(
        ["make", "atalanta"],
        cwd=core_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    build_log = core_path / "build.log"
    build_log.write_text(
        completed.stdout + "\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Atalanta build failed. See {build_log}")

    binary = core_path / "atalanta"
    if not binary.exists():
        raise FileNotFoundError(f"Build finished but binary is missing: {binary}")
    return binary


def _make_run_id(label: str, benchmark: Path) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    return f"{timestamp}_{label}_{benchmark.stem}_{suffix}"


def run_atalanta(config: AtalantaRunConfig) -> dict[str, Any]:
    """Run Atalanta in an isolated result directory.

    The benchmark is copied into the run directory before execution. This keeps
    generated `.test`, `.vec`, and `.log` files out of `benchmarks/` and
    `atalanta-core/`, including Atalanta's hard-coded `.vec` naming behavior.
    """

    benchmark = config.benchmark.resolve()
    if not benchmark.exists():
        raise FileNotFoundError(f"Benchmark does not exist: {benchmark}")

    binary = config.core_dir.resolve() / "atalanta"
    if not binary.exists():
        binary = build_atalanta(config.core_dir)

    run_id = config.run_id or _make_run_id(config.label, benchmark)
    run_dir = config.results_dir.resolve() / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    local_benchmark = run_dir / benchmark.name
    shutil.copy2(benchmark, local_benchmark)

    test_file = run_dir / f"{benchmark.stem}.test"
    log_file = run_dir / f"{benchmark.stem}.log"
    stdout_file = run_dir / "stdout.txt"
    stderr_file = run_dir / "stderr.txt"
    metadata_file = run_dir / "metadata.json"
    result_file = run_dir / "result.json"
    fault_trace_file = run_dir / f"{test_file.name}.faulttrace.csv"
    pattern_trace_file = run_dir / f"{test_file.name}.patterntrace.csv"

    command = [str(binary), "-t", test_file.name]
    if config.create_log:
        command.extend(["-l", log_file.name])
    command.extend(config.options)
    command.append(local_benchmark.name)

    started_at = datetime.now().isoformat(timespec="seconds")
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=run_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=config.timeout_seconds,
            check=False,
        )
        stdout_text = completed.stdout
        stderr_text = completed.stderr
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        returncode = -1
        if isinstance(stdout_text, bytes):
            stdout_text = stdout_text.decode(errors="replace")
        if isinstance(stderr_text, bytes):
            stderr_text = stderr_text.decode(errors="replace")
        stderr_text = (
            f"{stderr_text}\nTimeout after {config.timeout_seconds} seconds"
        ).strip()
    finished_at = datetime.now().isoformat(timespec="seconds")

    stdout_file.write_text(stdout_text, encoding="utf-8")
    stderr_file.write_text(stderr_text, encoding="utf-8")

    parse_source = stdout_text
    if "Fault coverage" not in parse_source and log_file.exists():
        parse_source = log_file.read_text(errors="replace")

    parsed = parse_atalanta_output(parse_source)
    stderr_text = stderr_text.strip()
    success = returncode == 0 and parsed.get("fault_coverage") is not None
    trace_summary = _summarize_fault_trace(fault_trace_file)

    parsed.update(
        {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "benchmark": benchmark.name,
            "benchmark_path": str(benchmark),
            "options": list(config.options),
            "returncode": returncode,
            "success": success,
            "timed_out": timed_out,
            "error": stderr_text if not success else "",
            "stdout_path": str(stdout_file),
            "stderr_path": str(stderr_file),
            "test_path": str(test_file) if test_file.exists() else None,
            "fault_trace_path": str(fault_trace_file) if fault_trace_file.exists() else None,
            "pattern_trace_path": str(pattern_trace_file)
            if pattern_trace_file.exists()
            else None,
            "vec_path": str(run_dir / f"{benchmark.stem}.vec")
            if (run_dir / f"{benchmark.stem}.vec").exists()
            else None,
            "log_path": str(log_file) if log_file.exists() else None,
        }
    )
    parsed.update(trace_summary)
    result_file.write_text(json.dumps(parsed, indent=2, sort_keys=True), encoding="utf-8")

    metadata = {
        "run_id": run_id,
        "label": config.label,
        "command": command,
        "cwd": str(run_dir),
        "started_at": started_at,
        "finished_at": finished_at,
        "metadata": config.metadata,
    }
    metadata_file.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return parsed


def benchmark_path(name: str, benchmark_dir: str | Path = DEFAULT_BENCHMARK_DIR) -> Path:
    """Resolve a benchmark name like `b15f` or `b15f.bench`."""

    stem = name if name.endswith(".bench") else f"{name}.bench"
    return Path(benchmark_dir).resolve() / stem


def _summarize_fault_trace(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    attempts = 0
    generated_patterns = 0
    total_detected = 0
    total_extra_drops = 0
    max_extra_drops = 0

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            attempts += 1
            pattern_index = int(row.get("generated_pattern_index") or 0)
            if pattern_index <= 0:
                continue
            generated_patterns += 1
            detected = int(row.get("pattern_detected_faults") or 0)
            extra_drops = int(row.get("pattern_extra_drops") or 0)
            total_detected += detected
            total_extra_drops += extra_drops
            max_extra_drops = max(max_extra_drops, extra_drops)

    return {
        "fault_trace_attempts": attempts,
        "generated_patterns_traced": generated_patterns,
        "faults_dropped_per_generated_pattern_mean": (
            total_detected / generated_patterns if generated_patterns else None
        ),
        "extra_drops_per_generated_pattern_mean": (
            total_extra_drops / generated_patterns if generated_patterns else None
        ),
        "max_pattern_extra_drops": max_extra_drops if generated_patterns else None,
    }
