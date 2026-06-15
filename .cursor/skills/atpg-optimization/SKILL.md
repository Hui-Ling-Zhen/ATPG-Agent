---
name: atpg-optimization
description: Guides agent-based ATPG optimization in ATPG-Agent/Atalanta. Use when optimizing Atalanta, ATPG algorithms, stuck-at fault solving, FAN heuristics, fault ordering, adaptive test compaction, runtime, pattern count, repeated-trial evaluation, or when reusing previous fault solving experience for later faults.
---

# ATPG Optimization

## Purpose

Use this skill when working in ATPG-Agent to improve ATPG runtime, fault coverage, pattern count, or test compaction. The current core backend is `atalanta-core/`, a mostly isolated Atalanta implementation. Treat Atalanta runs as the signoff oracle: LLM/agent proposals are hypotheses until repeated experiments confirm them.

## Current Knowledge

- Default Atalanta uses shuffle compaction with `-c 2`.
- Black-box local search found `-c 1` is better for runtime-first optimization: coverage stays unchanged, runtime improves, and pattern count increases only slightly.
- The best prior runtime-local candidate was `c1_no_learning` (`-c 1`): `runtime_win_count = 3`, `stable_win_count = 3`, `average_score_delta_mean = +0.207`, `runtime_delta_mean = -2.304s`, `pattern_delta_mean = +2.333`.
- A first white-box adaptive shuffle-stop policy was added in `atalanta-core/sim.cpp`.
- Repeated-trial adaptive comparison found `adaptive_c1` (`-c 1`) is the best score-balanced candidate: `runtime_win_count = 3`, `stable_win_count = 2`, `wins = 3`, `average_score_delta_mean = +0.223`, `runtime_delta_mean = -2.442s`, `pattern_delta_mean = +2.111`.
- `adaptive_default` and `adaptive_c2` prove adaptive early-stop is meaningful as a runtime-first lever: both preserve coverage and reduce runtime on all three benchmarks, but increase pattern count too much.
- Static learning (`-L`) has not been a clear runtime win in these experiments; treat it as an ablation, not a default improvement.

## Optimization Principles

1. Preserve coverage first. Any candidate with lower fault coverage than baseline is not a win.
2. Prefer repeated trials over single-run conclusions. Runtime has noise.
3. Separate runtime-first conclusions from score-balanced conclusions.
4. Track pattern count explicitly; runtime gains that leave many extra patterns may be useful but should be labeled runtime-first.
5. Keep `atalanta-core/` changes narrow and measurable. Do not refactor unrelated code while changing ATPG heuristics.
6. Keep every run artifact under `results/runs/<run_id>/`.

## Fault-to-Fault Learning Direction

The next algorithmic direction is to reuse information from earlier fault solving to improve later fault solving. Do this as an instrument-then-optimize loop:

1. Instrument per-fault solving behavior before changing heuristics:
   - fault id, gate, stuck-at value, level, fanout/fanin context
   - solved / redundant / aborted status
   - backtrack count
   - FAN phase used
   - generated pattern index
   - whether the resulting pattern detects additional faults
   - contribution to later compaction

2. Derive transfer features from previous faults:
   - faults solved by the same or nearby pattern
   - gates repeatedly causing high backtracking
   - regions that often become redundant or aborted
   - implication decisions that repeatedly succeed
   - patterns with high multi-fault detection value

3. Apply transfer cautiously:
   - reorder remaining faults using observed difficulty and pattern utility
   - prioritize faults likely to be detected by recently effective patterns
   - adapt backtrack budget by fault difficulty instead of using one global value
   - reuse learned implication hints only when they are local and explainable
   - feed high-utility pattern information into compaction scoring

4. Validate with repeated trials against the unchanged baseline and current best candidate.

## Compaction-Specific Guidance

For adaptive compaction work:

- Continue to record per-shuffle pattern reduction and runtime.
- Treat `pattern_reduction / extra_runtime` as the first cost function, not the final one.
- Add a pattern-growth guard before stopping too aggressively.
- Compare against both repeated default and `adaptive_c1`.
- Report:
  - coverage delta
  - runtime delta mean/std
  - pattern delta mean/std
  - `runtime_win_count`
  - `stable_win_count`
  - adaptive early-stop rate

## Experiment Commands

Run a built-in candidate set:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set adaptive_compaction \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --output results/candidates/adaptive_compaction_results.csv
```

Compare against repeated default:

```bash
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.compare \
  --baseline results/baseline/default_repeated_baseline.csv \
  --candidates results/candidates/adaptive_compaction_results.csv \
  --output-dir results/comparisons/adaptive_compaction
```

## Reporting Template

When summarizing an ATPG optimization result, include:

- What changed in the algorithm or candidate options.
- Which baseline was used.
- Number of trials and benchmarks.
- Coverage regressions, if any.
- Runtime wins and stable wins.
- Runtime delta mean/std.
- Pattern delta mean/std.
- Whether the result is score-balanced or runtime-first.
- Next heuristic to try.
