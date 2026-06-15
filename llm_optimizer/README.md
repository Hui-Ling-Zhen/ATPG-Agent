# llm_optimizer

This package contains the outer agent optimization loop for ATPG-Agent.

The current backend is `atalanta-core`, so the package compiles and runs Atalanta today. The project-level framing is broader: LLM proposal is combined with validation, local search, repeated-trial evaluation, and ATPG signoff. Future backends can reuse the same runner/parser/evaluator structure if they expose comparable metrics.

Implemented modules:

- `runner.py`: compile and run the current `atalanta-core` backend in isolated run directories.
- `parser.py`: parse ATPG stdout/log summaries into structured records, including adaptive compaction metadata.
- `evaluator.py`: compute optimization metrics and scores.
- `candidates.py`: define candidate CLI configurations and load LLM-proposed JSON. Built-in sets include `default`, `compaction_runtime_local`, and `adaptive_compaction`.
- `compare.py`: compare candidate results against a baseline, summarize wins, aggregate repeated-trial mean/std statistics, and report adaptive compaction metrics.
- `experiments/run_baseline.py`: run a baseline benchmark set and write CSV summaries.
- `experiments/run_candidates.py`: run candidate configurations across benchmarks, including repeated trials via `--trials`.
- `agent.py`: build proposal prompts, call an OpenAI-compatible LLM, validate strict JSON candidate proposals, and save them for evaluation. The LLM never executes commands directly.

Planned next step:

- Tune the adaptive shuffle-stop cost function to reduce the pattern-count penalty seen in `adaptive_default` / `adaptive_c2`.
- Run agent proposals through `run_candidates.py --candidates-json ...` and compare them against the repeated-trial candidate statistics.
- Add controlled white-box optimization stages for fault ordering and adaptive backtrack budgets while keeping ATPG runs as the signoff oracle.
- `configs/`: experiment settings and benchmark selections.
- `prompts/`: prompt templates for optimization, analysis, and repair.
