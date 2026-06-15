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
- First fault-ordering experiments added `-O easy` and `-O stem`. `stem_first` is the strongest initial ordering signal: against repeated default it achieved `runtime_win_count = 3`, `stable_win_count = 3`, `average_score_delta_mean = +0.420`, `runtime_delta_mean = -6.237s`; against `adaptive_c1` it still achieved `wins = 3`, `stable_win_count = 2`, `average_score_delta_mean = +0.197`.
- Offline fault-to-fault history profiles are now supported. `llm_optimizer/fault_profile.py` reads `faulttrace.csv` / `patterntrace.csv`, generates `results/profiles/<benchmark>_fault_profile.json`, and Atalanta can consume the profile through `-O history -F <profile.json>`.
- `-O history` uses profile scores for fault ordering and profile-suggested per-fault backtrack budgets to override the global `g_iMaxBackTrack1` on selected faults. A pcitc smoke test loaded `pcitc_fault_profile.json` successfully and ran with `fault_ordering_mode = history`.

## Optimization Principles

1. Preserve coverage first. Any candidate with lower fault coverage than baseline is not a win.
2. Prefer repeated trials over single-run conclusions. Runtime has noise.
3. Separate runtime-first conclusions from score-balanced conclusions.
4. Track pattern count explicitly; runtime gains that leave many extra patterns may be useful but should be labeled runtime-first.
5. Keep `atalanta-core/` changes narrow and measurable. Do not refactor unrelated code while changing ATPG heuristics.
6. Keep every run artifact under `results/runs/<run_id>/`.

## Fault-to-Fault Learning Direction

The next algorithmic direction is to reuse information from earlier fault solving to improve later fault solving. Do this as an instrument-then-optimize loop:

1. Use the existing per-fault instrumentation before changing heuristics:
   - fault id, gate, stuck-at value, level, fanout/fanin context
   - solved / redundant / aborted status
   - backtrack count
   - FAN phase used
   - generated pattern index
   - whether the resulting pattern detects additional faults
   - contribution to later compaction

The instrumentation writes:

- `<benchmark>.test.faulttrace.csv`: one row per selected fault attempt, including structure, testability, result, backtracks, runtime, generated pattern, and extra dropped faults.
- `<benchmark>.test.patterntrace.csv`: retained compacted patterns and their origin pattern indices.

`result.json`, baseline CSVs, and candidate CSVs expose `fault_trace_path` and `pattern_trace_path`.

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

4. Prefer offline profile policies before invasive C++ inference changes:
   - Generate `results/profiles/<benchmark>_fault_profile.json` from completed traces.
   - Use `-O history -F <profile.json>` for the next run.
   - Let the LLM/agent tune `alpha`, `beta`, `gamma`, `delta`, and `epsilon` in the profile builder, not execute arbitrary commands.
   - Keep `stem_first` and `adaptive_c1` as references.

5. Validate with repeated trials against the unchanged baseline and current best candidate.

## Fault Ordering Guidance

Use `-O stem` as the first ordering baseline. It prioritizes fanout/stem-related faults and has shown the most robust repeated-trial gains so far. Use `-O easy` as an ablation for high-observability / low-controllability-difficulty ordering; it can reduce runtime, but its score is less consistent because pattern count can rise.

Use `-O history -F results/profiles/<benchmark>_fault_profile.json` when testing fault-to-fault learning. The score is:

```text
score =
  + alpha   * historical_extra_drops
  + beta    * compaction_retained_rate
  - gamma   * historical_backtracks
  - delta   * historical_abort_rate
  + epsilon * stem_bonus
```

The built-in candidate set is `fault_to_fault_learning`; pass `--profile-dir results/profiles` so `run_candidates.py` can attach benchmark-specific profiles.

When reporting ordering results, include:

- coverage delta
- aborted fault delta
- redundant fault delta
- backtracking delta
- runtime delta mean/std
- pattern delta mean/std
- faults dropped per generated pattern
- extra drops per generated pattern

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

Build a history profile from a completed run:

```bash
python3 -m llm_optimizer.fault_profile \
  --fault-trace results/runs/<run_id>/<benchmark>.test.faulttrace.csv \
  --pattern-trace results/runs/<run_id>/<benchmark>.test.patterntrace.csv \
  --benchmark pcitc \
  --output results/profiles/pcitc_fault_profile.json
```

Run history-based fault-to-fault candidates:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set fault_to_fault_learning \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --profile-dir results/profiles \
  --output results/candidates/fault_to_fault_learning_results.csv
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
