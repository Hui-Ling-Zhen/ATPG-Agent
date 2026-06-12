# llm_optimizer

This package will contain the outer optimization loop for Atalanta.

Planned modules:

- `runner.py`: compile and run `atalanta-core`.
- `parser.py`: parse Atalanta stdout, `.test`, `.vec`, and log files.
- `evaluator.py`: compute optimization metrics and scores.
- `agent.py`: call an LLM and request the next candidate configuration.
- `configs/`: experiment settings and benchmark selections.
- `prompts/`: prompt templates for optimization, analysis, and repair.
