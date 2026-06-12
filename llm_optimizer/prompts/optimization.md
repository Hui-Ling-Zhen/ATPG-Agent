# Atalanta Optimization Prompt

You are optimizing Atalanta ATPG runs.

Given benchmark results, propose the next candidate configuration as strict JSON.

The optimization should balance:

- Higher fault coverage.
- Fewer generated test patterns.
- Lower runtime.
- Fewer undetected or aborted faults.
