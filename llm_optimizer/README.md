# llm_optimizer

This package contains the outer optimization loop for Atalanta.

Implemented modules:

- `runner.py`: compile and run `atalanta-core` in isolated run directories.
- `parser.py`: parse Atalanta stdout/log summaries into structured records.
- `evaluator.py`: compute optimization metrics and scores.
- `experiments/run_baseline.py`: run a baseline benchmark set and write CSV summaries.

Planned next module:

- `agent.py`: call an LLM and request the next candidate configuration.
- `configs/`: experiment settings and benchmark selections.
- `prompts/`: prompt templates for optimization, analysis, and repair.
