# llm_optimizer

This package contains the outer optimization loop for Atalanta.

Implemented modules:

- `runner.py`: compile and run `atalanta-core` in isolated run directories.
- `parser.py`: parse Atalanta stdout/log summaries into structured records.
- `evaluator.py`: compute optimization metrics and scores.
- `candidates.py`: define candidate CLI configurations and load LLM-proposed JSON.
- `compare.py`: compare candidate results against a baseline, summarize wins, and aggregate repeated-trial mean/std statistics.
- `experiments/run_baseline.py`: run a baseline benchmark set and write CSV summaries.
- `experiments/run_candidates.py`: run candidate configurations across benchmarks, including repeated trials via `--trials`.
- `agent.py`: build proposal prompts, call an OpenAI-compatible LLM, validate strict JSON candidate proposals, and save them for evaluation.

Planned next step:

- Run LLM proposals through `run_candidates.py --candidates-json ...` and compare them against the repeated-trial candidate statistics.
- `configs/`: experiment settings and benchmark selections.
- `prompts/`: prompt templates for optimization, analysis, and repair.
