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

## Notes

- `atalanta-core/` should stay close to the original Atalanta source until the evaluation loop is reliable.
- `benchmarks/` was extracted from the original `Atalanta/data/` directory.
- Generated `.test`, `.vec`, `.log`, and temporary run outputs should be written under `results/` rather than mixed into the core source tree.
