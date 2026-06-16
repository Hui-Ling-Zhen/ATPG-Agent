# ATPG-Agent

ATPG-Agent is an experimental agent-based optimization framework for automatic test pattern generation (ATPG).

The current implementation uses Atalanta as the core ATPG algorithm and signoff backend. The outer agent loop proposes candidates, runs experiments, parses metrics, compares against baselines, and feeds the results into the next optimization round. The LLM is one component of the agent loop: it proposes and explains candidates, but all wins must be signed off by real ATPG runs.

## Repository Layout

```text
ATPG-Agent/
  atalanta-core/        # Atalanta C++ source code, used as the current core ATPG backend.
  benchmarks/           # Benchmark .bench designs and existing generated data.
  llm_optimizer/        # Agent optimization pipeline around the ATPG backend.
    prompts/            # Prompt templates.
    configs/            # Experiment and search configs.
    experiments/        # Experiment orchestration code or notebooks.
  results/
    baseline/           # Baseline Atalanta measurements.
    runs/               # Iterative optimization outputs.
```

## Agent Workflow

The current implementation treats `atalanta-core` as a black-box ATPG core:

1. Compile the ATPG backend, currently Atalanta.
2. Select benchmark circuits from `benchmarks/`.
3. Run the backend with candidate options or heuristics.
4. Parse fault coverage, pattern count, runtime, and undetected faults.
5. Compare candidates against repeated baselines and signoff constraints.
6. Ask the agent/LLM to propose the next candidate configuration.
7. Expand each proposal with local search or ablation candidates.
8. Repeat the run/compare/signoff loop.

After this loop is stable, the project can add controlled white-box optimization inside the core algorithm, such as modifying compaction policy, fault ordering, X-fill, D-frontier selection, backtrace heuristics, or adaptive backtrack budgets. Even then, all algorithm patches should be ranked only by full ATPG signoff results.

## Current Core Algorithm

The first backend is `atalanta-core/`, a mostly isolated copy of the original Atalanta implementation. Atalanta is a classical ATPG tool for stuck-at faults in combinational circuits. It uses the FAN algorithm for test generation, parallel pattern single fault propagation for fault simulation, and built-in test compaction options.

Keeping Atalanta isolated is intentional: the agent can first optimize and evaluate command-line configurations from outside the tool, then later make controlled white-box changes to the core algorithm once the evaluation loop is reliable.

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

`llm_optimizer/agent.py` provides the proposal step of the agent loop: build a prompt from baseline/candidate summaries, call an OpenAI-compatible chat endpoint, validate strict JSON candidate proposals, and save them for `run_candidates.py`.

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

## Why Agent-Based?

This project is called ATPG-Agent because the optimization target is the ATPG process, not only one specific implementation. Atalanta is the current core algorithm, while the agent loop includes:

- structured candidate generation
- strict JSON validation
- isolated Atalanta execution
- repeated-trial statistics
- baseline-constrained signoff
- local search and ablation around promising proposals
- persistent run artifacts under `results/runs/`

The LLM proposes hypotheses and candidate options; the agent infrastructure decides whether they survive executable evaluation.

## Comparison Experiment Summary

This repository contains a completed comparison experiment for the agent/LLM proposal in `results/proposals/proposal_20260613-215430.json`.

The proposal was evaluated on `pcitc`, `destc`, and `DMAtc` with three repeated trials per `(candidate, benchmark)` pair:

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

### Agent Proposal vs Original Baseline

This comparison uses the earlier single-run baseline in `results/baseline/baseline_20260612-221054.csv`.

| Candidate | Wins | Stable wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean |
|---|---:|---:|---:|---:|---:|
| `compaction_c1_learning` | 3 | 3 | +0.765 | -7.687 | +0.333 |
| `phase1_b20_learning` | 3 | 3 | +0.462 | -4.480 | -1.444 |
| `phase2_b5_learning` | 3 | 3 | +0.423 | -4.096 | -1.333 |
| `phase2_b20_learning_seed1` | 2 | 2 | +0.180 | -1.563 | -2.333 |
| `reverse_phase2_b10` | 1 | 1 | -0.220 | -10.396 | +126.000 |

### Agent Proposal vs Repeated Default

This comparison is more conservative: it uses `results/baseline/default_repeated_baseline.csv`, where default Atalanta was also run three times per benchmark.

| Candidate | Wins | Stable wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean |
|---|---:|---:|---:|---:|---:|
| `compaction_c1_learning` | 2 | 1 | +0.039 | -0.668 | +2.778 |
| `reverse_phase2_b10` | 1 | 1 | -0.947 | -3.378 | +128.444 |
| `phase1_b20_learning` | 0 | 0 | -0.264 | +2.539 | +1.000 |
| `phase2_b5_learning` | 0 | 0 | -0.303 | +2.922 | +1.111 |
| `phase2_b20_learning_seed1` | 0 | 0 | -0.547 | +5.456 | +0.111 |

The best generated candidate is `compaction_c1_learning` (`-c 1 -L`). It preserved coverage on all three benchmarks. Against the repeated default baseline, it was a stable win on `DMAtc`, a small non-stable win on `destc`, and slightly worse on `pcitc`.

| Benchmark | Candidate | Coverage delta | Runtime delta (s) | Pattern delta | Score delta | Stable win |
|---|---|---:|---:|---:|---:|---|
| `DMAtc.bench` | `compaction_c1_learning` | 0.000 | -1.062 | +0.333 | +0.103 | yes |
| `destc.bench` | `compaction_c1_learning` | 0.000 | -0.977 | +7.000 | +0.028 | no |
| `pcitc.bench` | `compaction_c1_learning` | 0.000 | +0.034 | +1.000 | -0.013 | no |

Summary: the agent proposal produced a useful new local-search direction around compaction effort plus static learning. It does not yet prove a broad advantage over default Atalanta, but it does show that the agent-assisted loop can identify a coverage-preserving configuration with benchmark-specific gains. The next step is to search locally around `-c 1 -L`, for example `-c 1/-c 2`, with and without `-B 5/-B 10`, using more trials.

### Runtime-First Local Search

The runtime-focused search space is implemented as the built-in candidate set `compaction_runtime_local`. It expands around the best observed agent candidate `compaction_c1_learning` and tests:

- `-c 1` vs `-c 2`
- with and without `-L`
- with and without `-B 5` / `-B 10`

Methodologically, this is a local search around the agent-discovered direction: reduce the test compaction shuffle effort first, then ablate whether static learning or phase-2 FAN search is actually responsible for the runtime improvement.

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

Updated conclusion: the agent-assisted loop first identified `-c 1 -L` as a promising direction. The follow-up local search showed that `-c 1` alone is stronger for runtime-first optimization. In other words, the LLM component was useful for pointing to the compaction-effort region, while the agent's local search isolated the simpler and better setting.

### Adaptive Shuffle Stop

The first white-box compaction change is implemented in `atalanta-core/sim.cpp`. It turns the black-box observation about `-c 1` into an adaptive shuffle policy inside the core algorithm.

The new policy keeps `-c` as the user-requested upper bound, but the core computes an effective adaptive shuffle limit from circuit size and the number of patterns before compaction. During shuffle compaction, each round records:

- pattern count after the round
- pattern reduction versus the previous round
- CPU time spent in the round
- benefit score: `pattern_reduction / extra_runtime`
- whether the next shuffle should continue

The first version is runtime-first. It stops early when the dynamic shuffle limit is reached, when a round gives no additional pattern reduction, or when the observed benefit falls below the threshold. This keeps fault coverage as the signoff constraint while accepting a small pattern increase if runtime improves.

The summary output now includes adaptive fields such as:

```text
Adaptive shuffling compaction             : ON
Effective adaptive shuffle limit          : 1
Adaptive compaction stopped early         : YES
Adaptive compaction min benefit           : 1.000 patterns/sec
```

The Python parser and CSV writers also record:

- `adaptive_compaction_enabled`
- `adaptive_shuffle_limit`
- `adaptive_compaction_stopped_early`
- `adaptive_compaction_min_benefit`

A first smoke test was run on the standard three benchmarks:

```bash
python3 llm_optimizer/experiments/run_baseline.py \
  --benchmarks pcitc destc DMAtc \
  --timeout-seconds 75 \
  --output results/baseline/adaptive_smoke_3bench.csv
```

| Benchmark | Coverage | Patterns before | Patterns after | Runtime (s) | Adaptive limit | Stopped early |
|---|---:|---:|---:|---:|---:|---|
| `pcitc.bench` | 99.826 | 7069 | 5968 | 11.267 | 1 | yes |
| `destc.bench` | 100.000 | 477 | 387 | 12.467 | 1 | yes |
| `DMAtc.bench` | 94.562 | 12557 | 10806 | 30.200 | 1 | yes |

Compared with the earlier repeated default baseline, this first adaptive version preserves coverage on all three smoke benchmarks. It is intentionally more aggressive about runtime than pattern minimization, so pattern count can increase relative to default `-c 2`.

### Adaptive Compaction Repeated-Trial Comparison

The formal repeated-trial experiment is implemented as the built-in candidate set `adaptive_compaction` in `llm_optimizer/candidates.py`. It evaluates the adaptive core against the previous repeated default baseline with three trials per `(candidate, benchmark)` pair:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set adaptive_compaction \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --output results/candidates/adaptive_compaction_results.csv
```

The comparison was generated with:

```bash
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.compare \
  --baseline results/baseline/default_repeated_baseline.csv \
  --candidates results/candidates/adaptive_compaction_results.csv \
  --output-dir results/comparisons/adaptive_compaction
```

The key result files are:

- `results/candidates/adaptive_compaction_results.csv`
- `results/comparisons/adaptive_compaction/candidate_summary.csv`
- `results/comparisons/adaptive_compaction/candidate_stats.csv`
- `results/comparisons/adaptive_compaction/candidate_comparison.csv`

The comparison output now also tracks adaptive-specific metrics:

- `adaptive_enabled_rate`
- `adaptive_shuffle_limit_mean`
- `adaptive_stopped_early_rate`
- `adaptive_min_benefit_mean`

| Candidate | Runtime wins | Stable wins | Wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean | Early-stop rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| `adaptive_c1` | 3 | 2 | 3 | +0.223 | -2.442 | +2.111 | 0.000 |
| `adaptive_default` | 3 | 1 | 1 | +0.125 | -6.496 | +52.444 | 1.000 |
| `adaptive_c2` | 3 | 1 | 1 | +0.099 | -6.098 | +51.111 | 1.000 |
| `adaptive_c1_learning` | 3 | 1 | 1 | +0.021 | -0.509 | +3.000 | 0.000 |
| `adaptive_c2_learning` | 2 | 1 | 1 | -0.329 | -2.094 | +53.889 | 1.000 |

The best score-balanced candidate is `adaptive_c1` (`-c 1`). It preserves coverage on all three benchmarks, wins all three by score, wins all three by runtime, and has only a small mean pattern increase. It is close to the earlier `c1_no_learning` result, but slightly stronger in this repeated comparison: `average_score_delta_mean` improves from `+0.207` to `+0.223`, and `runtime_delta_mean` improves from `-2.304s` to `-2.442s`.

| Benchmark | Candidate | Coverage delta | Runtime delta (s) | Pattern delta | Score delta | Stable win |
|---|---|---:|---:|---:|---:|---|
| `destc.bench` | `adaptive_c1` | 0.000 | -5.083 | +4.333 | +0.465 | yes |
| `pcitc.bench` | `adaptive_c1` | 0.000 | -0.777 | +1.667 | +0.061 | yes |
| `DMAtc.bench` | `adaptive_c1` | 0.000 | -1.467 | +0.333 | +0.143 | no |

#### Runtime-First Finding

The adaptive early-stop policy itself is confirmed to trigger for the default `-c 2` path: `adaptive_default` and `adaptive_c2` both have `adaptive_stopped_early_rate_mean = 1.0` and reduce runtime on all three benchmarks. This is a meaningful result even though these candidates are not the best score-balanced choices.

| Candidate | Runtime wins | Runtime delta mean (s) | Runtime delta std (s) | Pattern delta mean | Early-stop rate |
|---|---:|---:|---:|---:|---:|
| `adaptive_default` | 3 | -6.496 | 4.258 | +52.444 | 1.000 |
| `adaptive_c2` | 3 | -6.098 | 3.977 | +51.111 | 1.000 |

This shows that adaptive shuffle stopping can be a strong runtime-first control knob: it preserves coverage while cutting substantial runtime from the default compaction path. The trade-off is that the first policy stops too aggressively and leaves more patterns after compaction. Therefore, the next optimization target is not whether adaptive stopping works, but how to tune its cost function so it keeps most of the runtime gain while reducing the pattern-count penalty.

### Fault Ordering Observability

The first step toward fault-ordering optimization is now implemented as instrumentation only. It does not change the current fault order. The active fault-oriented ATPG traversal is in `atalanta-core/sim.cpp::testgen()`: Atalanta scans `g_pFaultList` backward, selects the next `UNDETECTED` fault, runs `fan()` in phase 1 or `fan1()` in phase 2, then updates the fault status after fault simulation.

Each run now writes two trace files next to the generated `.test` file:

- `<benchmark>.test.faulttrace.csv`
- `<benchmark>.test.patterntrace.csv`

`result.json` records these paths as `fault_trace_path` and `pattern_trace_path`, and the baseline/candidate CSV writers include the same fields for batch experiments.

`faulttrace.csv` records one row per selected fault attempt:

- fault identity: fault index, gate, fault site, input/output line, stuck-at value
- structural features: gate/site level from PI/PO, fanout count, fanin count, stem/fanout flags
- testability features: `cont0` / `cont1` for the gate and fault site
- solving result: detected, redundant, or aborted
- solving cost: FAN state, backtracks, FAN runtime, phase 1 vs phase 2
- pattern value: generated pattern index, faults detected by that pattern, and extra dropped faults

`patterntrace.csv` records which generated pattern origins survive compaction:

- compaction engine and mode
- shuffle round
- compacted pattern index
- origin pattern index
- detected faults for the retained pattern

A smoke run confirmed both traces are produced:

```bash
python3 llm_optimizer/experiments/run_baseline.py \
  --benchmarks pcitc \
  --timeout-seconds 75 \
  --output results/baseline/fault_trace_smoke.csv
```

Example `faulttrace.csv` rows show that early PI/stem faults can drop many faults at once. For example, the first selected `pcitc` fault generated pattern `1`, detected `17506` faults, and therefore had `17505` extra drops. This is exactly the kind of signal needed for later fault ordering strategies.

This instrumentation enables ordering candidates such as `easy_first`, `stem_first`, `high_observability_first`, `hard_controllability_first`, and `history_aware`.

### Fault Ordering Repeated-Trial Comparison

The first two white-box fault-ordering strategies are implemented through the new `-O` option:

- `-O easy`: prioritize faults with high observability and low controllability difficulty. In the current implementation, low `dpo` and low required controllability are treated as easier.
- `-O stem`: prioritize fanout/stem-related faults. In the current implementation, faults on gates or sites with higher fanout are moved earlier.

Because `testgen()` scans `g_pFaultList` from the end toward the beginning, the implementation sorts the array so higher-priority faults appear later in the array and are selected first. The gate-local fault linked lists are left unchanged.

The built-in candidate set is `fault_ordering`:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set fault_ordering \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --output results/candidates/fault_ordering_results.csv
```

The experiment was compared against both the repeated default baseline and the current `adaptive_c1` baseline:

```bash
PYTHONPATH="$(pwd)" python3 -m llm_optimizer.compare \
  --baseline results/baseline/default_repeated_baseline.csv \
  --candidates results/candidates/fault_ordering_results.csv \
  --output-dir results/comparisons/fault_ordering_vs_default_full_metrics

PYTHONPATH="$(pwd)" python3 -m llm_optimizer.compare \
  --baseline results/baseline/adaptive_c1_repeated_baseline.csv \
  --candidates results/candidates/fault_ordering_results.csv \
  --output-dir results/comparisons/fault_ordering_vs_adaptive_c1_full_metrics
```

The comparison now covers fault coverage, aborted faults, redundant faults, total backtrackings, runtime, patterns before/after compaction, and trace-derived pattern reuse metrics.

Against the repeated default baseline, `stem_first` is the strongest candidate:

| Candidate | Runtime wins | Stable wins | Wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean | Aborted delta | Backtracking delta | Drops / generated pattern |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stem_first` | 3 | 3 | 3 | +0.420 | -6.237 | +20.556 | -1.667 | +55.667 | 208.518 |
| `adaptive_c1_stem_first` | 3 | 3 | 3 | +0.340 | -2.331 | -10.444 | -1.667 | +55.667 | 208.518 |
| `easy_first` | 3 | 2 | 2 | +0.090 | -5.742 | +48.556 | -1.333 | +31.667 | 206.275 |

Against the current `adaptive_c1` baseline, `stem_first` still wins overall:

| Candidate | Runtime wins | Stable wins | Wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean | Aborted delta | Backtracking delta | Drops / generated pattern |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `stem_first` | 3 | 2 | 3 | +0.197 | -3.794 | +18.444 | -1.667 | +55.667 | 208.518 |
| `adaptive_c1_stem_first` | 1 | 2 | 2 | +0.117 | +0.111 | -12.556 | -1.667 | +55.667 | 208.518 |
| `easy_first` | 3 | 2 | 2 | -0.133 | -3.300 | +46.444 | -1.333 | +31.667 | 206.275 |

The main result is that `stem_first` is a real ordering signal. It preserves coverage, reduces aborted faults on average, improves runtime on all three benchmarks, and remains positive even when compared against `adaptive_c1`. The trade-off is that the pure `stem_first` candidate can increase final pattern count, while `adaptive_c1_stem_first` reduces pattern count versus `adaptive_c1` but loses some runtime advantage. This suggests the next ordering step should combine stem priority with a pattern-count guard or a hybrid score that balances stem influence and easy detectability.

### Fault-to-Fault History Policy

The next fault-ordering step is now implemented as an offline history policy. This keeps the LLM/agent role clean: it can adjust the scoring weights, while execution and signoff still happen through deterministic scripts and Atalanta runs.

The profile builder reads `faulttrace.csv` and `patterntrace.csv`, aggregates both per-fault and per-FFR/group historical value/cost, and writes `results/profiles/<benchmark>_fault_profile.json`:

```bash
python3 -m llm_optimizer.fault_profile \
  --fault-trace results/runs/<run_id>/<benchmark>.test.faulttrace.csv \
  --pattern-trace results/runs/<run_id>/<benchmark>.test.patterntrace.csv \
  --benchmark pcitc \
  --output results/profiles/pcitc_fault_profile.json
```

Each profile row includes:

- `stem_index` / FFR-style `fault_group_id`
- group size, based on the number of collapsed faults mapped to that group
- `target_fault -> dropped_group_distribution`
- `target_group -> dropped_group_distribution`
- `group_pair_reuse_count`, captured through `droptrace.csv`
- average extra drops per generated pattern
- average backtracks
- abort and redundant rates
- compaction retained rate
- group-level reuse probability
- group-level wait score, measuring whether a group is often dropped by other groups' patterns
- group-level history score
- group-level budget and representative fault score
- stem/fanout bonus
- final history score
- suggested per-fault backtrack budget

The fault score now combines fault-local value with group-level reuse value:

```text
score =
  + alpha   * historical_extra_drops
  + beta    * compaction_retained_rate
  - gamma   * historical_backtracks
  - delta   * historical_abort_rate
  + epsilon * stem_bonus
  + zeta    * group_score
```

The group score is computed from the same traces, but aggregated by `fault_group_id`:

```text
group_score =
  + group_alpha * group_avg_extra_drops
  + group_beta  * group_compaction_retained_rate
  + group_eta   * group_reuse_probability
  - group_gamma * group_avg_backtracks
  - group_delta * group_abort_rate
  - group_wait_penalty * group_wait_score
```

Atalanta can then use the profile with `-O history -F <profile.json>`. The new `-F` option passes the profile to the core. `run_candidates.py` can also attach benchmark-specific profiles automatically:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set fault_to_fault_learning \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --profile-dir results/profiles \
  --output results/candidates/fault_to_fault_learning_results.csv
```

Internally, `-O history` sorts faults by a high-reuse frontier: group score first, representative fault score second, fault score third, and wait score as a penalty. It then uses the profile's `backtrack_budget` field as a per-fault override for the global `g_iMaxBackTrack1` during phase-1 FAN search. This implements group-aware ordering, per-fault/per-group budget control, and adaptive backtrack policy:

- high-value stem / extra-drop faults can receive a larger budget
- high-value FFR groups are selected before low-value groups
- faults in groups that historically produce reusable, retained patterns are prioritized
- faults in groups that are often dropped by other patterns receive lower priority
- group-local duplicate / low-value faults receive low budgets
- historically aborted and low-value faults receive a very small budget
- ordinary faults keep the default budget

This is also the first simulation-aware reuse layer. The implementation does not rewrite FSIM's internal fault dropping logic; instead, FSIM writes `droptrace.csv` while preserving its original behavior. The offline profile then uses `faulttrace.csv`, `patterntrace.csv`, and `droptrace.csv` to learn which target faults and FFR groups tend to generate patterns that drop many other groups and survive compaction. In other words, simulation remains the signoff mechanism, while the next run's ordering is biased toward groups whose previous patterns had high reuse value and away from groups that are better left to be dropped by someone else's pattern.

The original history-ordering 3-trial experiment was run with:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set fault_to_fault_learning \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --profile-dir results/profiles \
  --output results/candidates/fault_to_fault_learning_results.csv
```

The comparison outputs are:

- `results/comparisons/fault_to_fault_learning_vs_default/`
- `results/comparisons/fault_to_fault_learning_vs_adaptive_c1/`

All 36 candidate runs succeeded, with no timeouts and no coverage regressions.

After adding `droptrace.csv`, wait-score penalties, representative-fault scoring, and group/fault two-level budgets, the reuse-aware 3-trial experiment was run with:

```bash
python3 llm_optimizer/experiments/run_candidates.py \
  --candidate-set fault_to_fault_learning \
  --benchmarks pcitc destc DMAtc \
  --trials 3 \
  --timeout-seconds 75 \
  --profile-dir results/profiles \
  --output results/candidates/reuse_history_3trial_results.csv
```

The reuse-aware comparison outputs are:

- `results/comparisons/reuse_history_vs_default/`
- `results/comparisons/reuse_history_vs_adaptive_c1/`

All 36 reuse-aware candidate runs succeeded, with no timeouts and no coverage regressions.

### Representative Results At A Glance

The three most representative results are `adaptive_c1`, `stem_first`, and the latest reuse-aware `history_ordering`. They show the progression from compaction policy, to structural fault ordering, to history-aware fault-to-fault learning. The table below uses the same repeated default baseline for all three.

| Result | Agent/LLM Capability Represented | Coverage regressions | Wins | Stable wins | Runtime wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean | Backtracking delta mean |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `adaptive_c1` | Finds a runtime bottleneck in test compaction and turns it into an adaptive compaction policy. | 0 | 3 | 2 | 3 | +0.223 | -2.442 | +2.111 | n/a |
| `stem_first` | Converts ATPG structure knowledge into a static, testable fault-ordering heuristic. | 0 | 3 | 3 | 3 | +0.426 | -6.059 | +18.222 | +55.667 |
| `history_ordering` | Reuses fault, group, and pattern-drop traces for next-run ordering and per-fault/per-group backtrack budgets. | 0 | 3 | 3 | 3 | +0.716 | -9.231 | +20.667 | -6649.000 |

`history_ordering` is the strongest runtime/backtracking result so far. Against repeated default, the latest reuse-aware policy improves runtime by `9.231s` on average and reduces total backtrackings by `6649.000` on average, while preserving coverage on every benchmark. Compared with `stem_first`, it shows why history-aware learning is more than a static structural heuristic: it learns which faults, FFR groups, and pattern-drop relationships were historically valuable or expensive, then changes both ordering and backtrack budget in the next run.

### Reported vs Effective Coverage

Atalanta's reported fault coverage counts only detected faults. For ATPG analysis, redundant faults can also be treated as explained faults because they are proven untestable rather than missed by the generated tests. Therefore, this README also uses an effective coverage view when interpreting low-coverage benchmarks:

```text
effective_coverage = (detected + redundant) / collapsed_faults
                   = 1 - aborted / collapsed_faults
```

This distinction is important for `DMAtc`. Its reported coverage remains around `94.562%`, but a large part of the remaining faults are redundant rather than truly unresolved.

| Metric | Default | Reuse-aware `history_ordering` | Interpretation |
|---|---:|---:|---|
| Reported coverage | 94.562 | 94.562 | Detected-only Atalanta metric. |
| Effective coverage | 97.225 | 97.118 | Counts detected + redundant as explained. |
| Aborted faults | 2159 | 2242 | Truly unresolved faults under this interpretation. |
| Redundant faults | 2071 | 1988 | Proven untestable / explained faults. |
| Backtrackings | 24460 | 4596 | Reuse-aware history sharply reduces FAN search. |
| Runtime (s) | 37.411 | 24.039 | Runtime is reduced while reported coverage is preserved. |

Increasing the backtrack limit on `DMAtc` mostly converts aborted faults into redundant faults rather than detected faults. For example, `-b 50` keeps reported coverage at `94.562%`, while reducing aborted faults from `2159` to `983` and increasing redundant faults from `2071` to `3247`, at the cost of much higher backtracking and runtime. This means the main optimization target for `DMAtc` should be runtime/backtracking and the aborted/redundant explanation balance, not simply chasing higher detected-only coverage.

### Reuse-Aware History Improvement

The table below isolates the effect of the latest pattern-reuse-aware policy against the previous history-aware policy, using the repeated default baseline.

| Result | Coverage regressions | Wins | Stable wins | Runtime wins | Avg score delta | Runtime delta mean (s) | Pattern delta mean | Backtracking delta mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Previous `history_ordering` | 0 | 3 | 3 | 3 | +0.689 | -9.615 | +27.222 | -5822.667 |
| Reuse-aware `history_ordering` | 0 | 3 | 3 | 3 | +0.716 | -9.231 | +20.667 | -6649.000 |
| Previous `history_ordering_c1` | 0 | 3 | 3 | 3 | +0.520 | -6.557 | +13.556 | -5822.667 |
| Reuse-aware `history_ordering_c1` | 0 | 3 | 3 | 3 | +0.608 | -6.750 | +6.667 | -6649.000 |

The reuse-aware policy improves the central trade-off: it keeps the stable runtime wins, improves the score, reduces the pattern penalty, and further reduces backtracking. `history_ordering_c1` is especially useful when pattern count matters: the pattern delta drops from `+13.556` to `+6.667` while runtime also improves slightly. The next agent step should tune `group_wait_penalty`, `zeta`, and the `group_*` weights to keep the backtracking/runtime gain while pushing pattern growth closer to zero.

## Notes

- `atalanta-core/` should stay close to the original Atalanta source until the evaluation loop is reliable.
- `benchmarks/` was extracted from the original `Atalanta/data/` directory.
- Generated `.test`, `.vec`, `.log`, and temporary run outputs should be written under `results/` rather than mixed into the core source tree.
