# Performance evidence

Prior knowledge pack for the `claims` validator. Each section names when
it applies and what supports a performance or benefit claim.

## Baseline

Applies when a claim of improvement is made ("faster", "cheaper", "N times",
"reduces").

- Is the claim compared against the current behaviour, measured the same
  way and under the same conditions?
- Is the baseline itself stated (numbers, method), or only the new
  result?

## Critical path

Applies when a claim says an end-to-end metric improves because one step
improves.

- Is the improved step on the path that dominates the metric for the
  stated workload?
- Is the step's share of the total known, so that the end-to-end gain
  can be bounded?
- Does the changed code actually run on the path the metric measures?

## Tail latency

Applies when a latency claim is made for user-facing or synchronous
operations.

- Does the claim address tail percentiles (p99, p999), not only mean or
  median?
- Can the change add rare slow cases (GC, cache misses, lock
  contention, retries) that the average hides?

## Cost shift

Applies when the gain comes from moving work, memory or I/O.

- Where does the work go: another component, the write path, background
  jobs, memory, storage, network?
- Is the added cost measured or bounded, and is it acceptable for the
  workloads the design targets?

## Measurement conditions

Applies when a claim is backed by benchmarks or experiments.

- Do data size, concurrency, hardware, build flags and configuration
  match the conditions the claim is made for?
- Are results repeated, with variance or significance stated?
- Are runs compared within one sitting, or across runs that drift?

## Scalability claims

Applies when a claim concerns behaviour as data, traffic or cluster size
grow.

- Is the growth rate of the cost stated or derived (per row, per
  segment, per node)?
- Is a limit reached first elsewhere (memory, connections, fan-out,
  coordination)?

## Benefit versus added cost

Applies when a claimed benefit justifies added complexity, resources or
risk.

- Is the benefit quantified for the workloads the design targets?
- Is the added cost (code, operations, failure modes, resources) stated
  alongside it?
