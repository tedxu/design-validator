# claims — are performance and benefit claims supported? (stage 2)

Follow `rules/evidence.md`.

Scope: assumptions of kind `performance` (or your assigned subset).
Truth: T1 — code at the baseline and the prior pack
`performance-evidence.md`. The design's numbers are what you examine,
not evidence: check whether they support the claim, not whether they
are true.

## Method, per claim

1. Classify the metric (latency, throughput, memory, CPU, storage, cost,
   scalability) and the support: measured (numbers with a method),
   derived (computed from known costs) or asserted (no basis).
2. Apply each matching `performance-evidence.md` section:
   - baseline: compared with current behaviour, measured the same way;
   - critical path: the improved step dominates the metric for the
     stated workload — read the code path (`code`);
   - tail latency, for latency claims;
   - cost shift: where work, memory or I/O moves;
   - measurement conditions: data size, concurrency, hardware, build
     flags and configuration match the claim's conditions.
3. `PASS` when the support meets the requirements, citing the section
   (`prior`, `supports`) and, when the path matters, the code;
   otherwise `ISSUE` and an `unsupported-claim` finding naming the
   missing requirement, citing the section (`prior`) and, when the
   path matters, the code.

## Severity

- `MAJOR`: a claim that motivates the design or decides between
  options has no baseline, measures a step off the critical path, or
  ignores a cost shift to a path the design does not discuss.
- `MINOR`: secondary claims, or missing tail or condition details.

A finding without a `prior` or `code` citation is capped at `MINOR`;
design lines alone do not count. Do not run benchmarks, estimate
numbers or propose experiments.
