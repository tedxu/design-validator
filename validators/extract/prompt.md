# extract — assumption extraction (stage 0)

Follow `rules/evidence.md` for `results/extract.json`.

Turn the design (`<run_dir>/design.md`; line numbers refer to it) into
testable assumptions, without judging whether they are true, and check
the design's internal consistency.

## Output 1: `<run_dir>/assumptions.json`

```json
{"assumptions": [
  {"id": "A1",
   "anchor": {"line_start": 12, "line_end": 13, "quote": "verbatim text from those lines"},
   "statement": "one normalized claim",
   "kind": "current-fact",
   "conditions": ["only when compaction is enabled"],
   "depends_on": [],
   "origin": "explicit"}
]}
```

- Every testable claim, in document order: `A1`, `A2`, …; one claim
  each, splitting compound sentences.
- `kind`:
  - `current-fact`: how the existing system behaves or is built (paths,
    symbols, fields, call flows, configuration, data formats);
  - `inference`: a conclusion drawn from other claims, listed in
    `depends_on`;
  - `compatibility`: a promise that something existing keeps working
    (APIs, formats, upgrades, consumers);
  - `invariant`: a property the design says always holds;
  - `performance`: speed, cost or resource use;
  - `design-choice`: a decision (mechanism, component, ordering) later
    validators may question.
- Keep qualifiers ("all", "only", "always", "after retry", "per
  segment") verbatim in `conditions`.
- An unstated premise the design relies on is `origin: inferred`,
  anchored to the sentence relying on it.
- `quote` is verbatim text within, or up to 3 lines around, the anchor.

## Output 2: `<run_dir>/results/extract.json`

A validator result reviewing whether the design's statements are
consistent with each other. Build its global picture and compare parts,
not sentences:

- goals and invariants against the mechanism meant to deliver them,
  including its exclusions and fallbacks;
- non-goals and exclusions against what the mechanism touches;
- the scope of a claim ("all", "only", "never", "exactly once") against
  every place that narrows or widens it;
- one mechanism, ownership, ordering, lifetime, failure handling or
  routing rule as described in different sections;
- compatibility and verification claims against the described
  behaviour (does the stated test or guarantee cover it?);
- deciding numbers, limits and conditions that appear more than once.

One check per comparison (`assumption_ids`: those compared; `design`
evidence quoting both sides), `PASS` when they agree.

Report:
- `inconsistent`: two statements that cannot both hold, where the
  conflict changes what an implementer would build, what a reviewer
  would conclude or what the design guarantees. Cite each side as its
  own `design` item (at least two, at different lines) and say what
  each claims.
- `ambiguous`: a core mechanism whose meaning cannot be determined, so
  later validators cannot check it, or an unresolved placeholder (TODO,
  TBD, ???) in a core part.

Do not report: term drift, naming variants, typos, grammar or
formatting unless they cause conflicting statements about behaviour;
miscounts and slips that do not change the design; missing detail in
history, changelog, review-log or "defects fixed" sections; undefined
labels in measurement write-ups unless a decision rests on them; vague
adjectives ("fast", "robust") alone.

## Severity

- `MAJOR`: the conflict or ambiguity concerns a goal, invariant, core
  mechanism or compatibility promise.
- `MINOR`: it still changes a secondary decision. Anything smaller is
  not reported.
- `BLOCKER`: only when the design has no testable core claim at all —
  one `ambiguous` finding quoting the title line as `design` evidence;
  still write `assumptions.json` (possibly empty).

Do not judge correctness, completeness or quality here.
