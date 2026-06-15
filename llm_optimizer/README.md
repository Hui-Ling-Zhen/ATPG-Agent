# llm_optimizer

This package contains the outer agent optimization loop for Atalanta.

The package name remains `llm_optimizer` for compatibility with existing scripts, but the project-level framing is agent-based: LLM proposal is combined with validation, local search, repeated-trial evaluation, and Atalanta signoff.

Implemented modules:

- `runner.py`: compile and run `atalanta-core` in isolated run directories.
- `parser.py`: parse Atalanta stdout/log summaries into structured records.
- `evaluator.py`: compute optimization metrics and scores.
- `candidates.py`: define candidate CLI configurations and load LLM-proposed JSON.
- `compare.py`: compare candidate results against a baseline, summarize wins, and aggregate repeated-trial mean/std statistics.
- `experiments/run_baseline.py`: run a baseline benchmark set and write CSV summaries.
- `experiments/run_candidates.py`: run candidate configurations across benchmarks, including repeated trials via `--trials`.
- `agent.py`: build proposal prompts, call an OpenAI-compatible LLM, validate strict JSON candidate proposals, and save them for evaluation. The LLM never executes commands directly.

Planned next step:

- Run agent proposals through `run_candidates.py --candidates-json ...` and compare them against the repeated-trial candidate statistics.
- Add controlled white-box optimization stages for compaction policy, fault ordering, and adaptive backtrack budgets while keeping Atalanta runs as the signoff oracle.
- `configs/`: experiment settings and benchmark selections.
- `prompts/`: prompt templates for optimization, analysis, and repair.
