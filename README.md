# LLM-Atalanta

LLM-Atalanta is an experimental workspace for optimizing the Atalanta ATPG flow with LLM-assisted search, analysis, and feedback loops.

The initial design keeps the original Atalanta C++ implementation mostly isolated as a backend, while the LLM optimization pipeline lives outside the core tool.

## Repository Layout

```text
LLM-Atalanta/
  atalanta-core/        # Copied Atalanta C++ source code.
  benchmarks/           # Benchmark .bench designs and existing generated data.
  llm_optimizer/        # LLM-driven optimization pipeline.
    prompts/            # Prompt templates.
    configs/            # Experiment and search configs.
    experiments/        # Experiment orchestration code or notebooks.
  results/
    baseline/           # Baseline Atalanta measurements.
    runs/               # Iterative optimization outputs.
```

## Intended Workflow

The first implementation should treat `atalanta-core` as a black-box ATPG backend:

1. Compile Atalanta.
2. Select benchmark circuits from `benchmarks/`.
3. Run Atalanta with candidate options or heuristics.
4. Parse fault coverage, pattern count, runtime, and undetected faults.
5. Ask an LLM to propose the next candidate configuration.
6. Compare against baseline, random search, and grid search.

After this loop is stable, the project can add controlled white-box optimization, such as modifying fault ordering, X-fill, D-frontier selection, backtrace heuristics, or compaction logic.

## Baseline Evaluation Loop

The initial black-box evaluation loop is implemented in `llm_optimizer/`.

Run the default baseline set:

```bash
python3 llm_optimizer/experiments/run_baseline.py
```

Useful options:

```bash
python3 llm_optimizer/experiments/run_baseline.py \
  --benchmarks pcitc destc DMAtc \
  --timeout-seconds 60
```

Each Atalanta run is isolated under `results/runs/<run_id>/` and keeps:

- `stdout.txt` / `stderr.txt`
- copied benchmark `.bench`
- generated `.test`, `.vec`, and `.log` files when Atalanta produces them
- `metadata.json`
- `result.json`

Baseline summaries are written under `results/baseline/`. Existing CSV files are never overwritten; a timestamped filename is created when needed.

## Candidate Evaluation

Run the built-in black-box candidate set:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --benchmarks pcitc destc DMAtc \
  --candidate-limit 8 \
  --trials 3 \
  --timeout-seconds 75
```

Candidate summaries are written under `results/candidates/`, while every raw run is still preserved under `results/runs/<run_id>/`.

Compare candidates against a baseline CSV:

```bash
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.compare \
  --baseline results/baseline/baseline_20260612-221054.csv \
  --candidates results/candidates/candidate_results.csv
```

The comparison step writes:

- `results/comparisons/candidate_comparison.csv`: per-candidate, per-benchmark deltas.
- `results/comparisons/candidate_stats.csv`: repeated-trial mean/std statistics by `(candidate, benchmark)`.
- `results/comparisons/candidate_summary.csv`: candidate-level win counts and average deltas.

`llm_optimizer/agent.py` provides the LLM-facing proposal loop: build a prompt from baseline/candidate summaries, call an OpenAI-compatible chat endpoint, validate strict JSON candidate proposals, and save them for `run_candidates.py`.

```bash
export OPENAI_API_KEY=...
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.agent \
  --candidate-summary results/comparisons/candidate_summary.csv \
  --candidate-comparison results/comparisons/candidate_comparison.csv \
  --max-candidates 5
```

If you already have an LLM response JSON, validate and save it without calling the API:

```bash
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.agent \
  --response-json results/proposals/assistant_llm_response.json
```

Then run the proposal:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidates-json results/proposals/proposal_<timestamp>.json \
  --benchmarks pcitc destc DMAtc \
  --trials 3
```

## Comparison Experiment Summary

This repository contains a completed comparison experiment for the LLM proposal in `results/proposals/proposal_20260613-215430.json`.

The LLM proposal was evaluated on `pcitc`, `destc`, and `DMAtc` with three repeated trials per `(candidate, benchmark)` pair:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidates-json results/proposals/proposal_20260613-215430.json \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --output results/candidates/llm_proposal_results.csv
```

The complete run artifacts are preserved under `results/runs/<run_id>/`. The key result files are:

- `results/candidates/llm_proposal_results.csv`
- `results/baseline/default_repeated_baseline.csv`
- `results/comparisons/llm_proposal/candidate_summary.csv`
- `results/comparisons/llm_vs_repeated_default/candidate_summary.csv`
- `results/comparisons/llm_vs_repeated_default/candidate_stats.csv`

### LLM Proposal vs Original Baseline

This comparison uses the earlier single-run baseline in `results/baseline/baseline_20260612-221054.csv`.

| Candidate | Wins | Stable wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean |
|---|---:|---:|---:|---:|---:|
| `compaction_c1_learning` | 3 | 3 | +0.765 | -7.687 | +0.333 |
| `phase1_b20_learning` | 3 | 3 | +0.462 | -4.480 | -1.444 |
| `phase2_b5_learning` | 3 | 3 | +0.423 | -4.096 | -1.333 |
| `phase2_b20_learning_seed1` | 2 | 2 | +0.180 | -1.563 | -2.333 |
| `reverse_phase2_b10` | 1 | 1 | -0.220 | -10.396 | +126.000 |

### LLM Proposal vs Repeated Default

This comparison is more conservative: it uses `results/baseline/default_repeated_baseline.csv`, where default Atalanta was also run three times per benchmark.

| Candidate | Wins | Stable wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean |
|---|---:|---:|---:|---:|---:|
| `compaction_c1_learning` | 2 | 1 | +0.039 | -0.668 | +2.778 |
| `reverse_phase2_b10` | 1 | 1 | -0.947 | -3.378 | +128.444 |
| `phase1_b20_learning` | 0 | 0 | -0.264 | +2.539 | +1.000 |
| `phase2_b5_learning` | 0 | 0 | -0.303 | +2.922 | +1.111 |
| `phase2_b20_learning_seed1` | 0 | 0 | -0.547 | +5.456 | +0.111 |

The best LLM-generated candidate is `compaction_c1_learning` (`-c 1 -L`). It preserved coverage on all three benchmarks. Against the repeated default baseline, it was a stable win on `DMAtc`, a small non-stable win on `destc`, and slightly worse on `pcitc`.

| Benchmark | Candidate | Coverage delta | Runtime delta (s) | Pattern delta | Score delta | Stable win |
|---|---|---:|---:|---:|---:|---|
| `DMAtc.bench` | `compaction_c1_learning` | 0.000 | -1.062 | +0.333 | +0.103 | yes |
| `destc.bench` | `compaction_c1_learning` | 0.000 | -0.977 | +7.000 | +0.028 | no |
| `pcitc.bench` | `compaction_c1_learning` | 0.000 | +0.034 | +1.000 | -0.013 | no |

Summary: the LLM proposal produced a useful new local-search direction around compaction effort plus static learning. It does not yet prove a broad advantage over default Atalanta, but it does show that the LLM-assisted loop can identify a coverage-preserving configuration with benchmark-specific gains. The next step is to search locally around `-c 1 -L`, for example `-c 1/-c 2`, with and without `-B 5/-B 10`, using more trials.

### Runtime-First Local Search

The runtime-focused search space is implemented as the built-in candidate set `compaction_runtime_local`. It expands around the best observed LLM candidate `compaction_c1_learning` and tests:

- `-c 1` vs `-c 2`
- with and without `-L`
- with and without `-B 5` / `-B 10`

Methodologically, this is a local search around the LLM-discovered direction: reduce the test compaction shuffle effort first, then ablate whether static learning or phase-2 FAN search is actually responsible for the runtime improvement.

The full local-search experiment was run with three repeated trials per `(candidate, benchmark)` pair:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set compaction_runtime_local \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --output results/candidates/compaction_runtime_local_results.csv
```

The results were compared against the repeated default baseline:

```bash
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.compare \
  --baseline results/baseline/default_repeated_baseline.csv \
  --candidates results/candidates/compaction_runtime_local_results.csv \
  --output-dir results/comparisons/compaction_runtime_local
```

The key result files are:

- `results/candidates/compaction_runtime_local_results.csv`
- `results/comparisons/compaction_runtime_local/candidate_summary.csv`
- `results/comparisons/compaction_runtime_local/candidate_stats.csv`
- `results/comparisons/compaction_runtime_local/candidate_comparison.csv`

`candidate_summary.csv` includes `runtime_win_count`, which counts benchmarks where coverage is preserved and mean runtime improves over the baseline. This is the preferred first-pass signal when runtime is the priority.

| Candidate | Runtime wins | Stable wins | Wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean |
|---|---:|---:|---:|---:|---:|---:|
| `c1_no_learning` | 3 | 3 | 3 | +0.207 | -2.304 | +2.333 |
| `c1_phase2_b5` | 2 | 2 | 2 | +0.003 | -0.307 | +2.778 |
| `c1_phase2_b10` | 2 | 2 | 2 | -0.060 | +0.357 | +2.444 |
| `c2_no_learning` | 1 | 1 | 1 | -0.008 | +0.128 | -0.444 |
| `c1_learning` | 0 | 0 | 0 | -0.105 | +0.671 | +3.778 |
| `c2_phase2_b5_learning` | 0 | 0 | 0 | -0.323 | +3.276 | -0.444 |
| `c2_learning` | 0 | 0 | 0 | -0.355 | +3.458 | +0.889 |
| `c1_phase2_b5_learning` | 0 | 0 | 0 | -0.366 | +3.328 | +3.333 |
| `c1_phase2_b10_learning` | 0 | 0 | 0 | -0.401 | +3.776 | +2.333 |
| `c2_phase2_b10_learning` | 0 | 0 | 0 | -0.437 | +4.359 | +0.111 |

The best runtime-first candidate is `c1_no_learning` (`-c 1`). It preserved coverage on all three benchmarks and was a stable win on all three. This is an important ablation result: the improvement comes primarily from reducing compaction shuffle effort (`-c 1`), not from static learning (`-L`).

| Benchmark | Candidate | Coverage delta | Runtime delta (s) | Pattern delta | Score delta | Stable win |
|---|---|---:|---:|---:|---:|---|
| `DMAtc.bench` | `c1_no_learning` | 0.000 | -2.184 | +2.333 | +0.195 | yes |
| `destc.bench` | `c1_no_learning` | 0.000 | -4.066 | +2.333 | +0.383 | yes |
| `pcitc.bench` | `c1_no_learning` | 0.000 | -0.661 | +2.333 | +0.043 | yes |

Updated conclusion: the LLM-assisted loop first identified `-c 1 -L` as a promising direction. The follow-up local search showed that `-c 1` alone is stronger for runtime-first optimization. In other words, LLM was useful for pointing to the compaction-effort region, while the local search isolated the simpler and better setting.

## Notes

- `atalanta-core/` should stay close to the original Atalanta source until the evaluation loop is reliable.
- `benchmarks/` was extracted from the original `Atalanta/data/` directory.
- Generated `.test`, `.vec`, `.log`, and temporary run outputs should be written under `results/` rather than mixed into the core source tree.
