# conformance — does the design break the project's own rules? (stage 1)

Follow `rules/evidence.md`.

Scope: the whole design. Sources, most authoritative first: project
documents marked `authoritative` in your task; those marked
`informative`; prior packs (especially `compatibility-rules.md` and
`consistency-patterns.md`) and any project pack. Truth: T1 (code,
priors), T2 (project documents).

## Method

1. Collect applicable rules: the hard requirements of the
   authoritative documents first (must, never, always, only, required,
   forbidden, stated invariants), then informative documents and prior
   packs. Skip areas the design does not touch. Name the documents read
   in `search_scope`.
2. For each applicable rule, state the premise: which design lines
   touch its area.
3. Check the design against it:
   - follows it, or states an approved exception: `PASS`, citing the
     rule and the design lines;
   - breaks it: `ISSUE` and a `nonconformance` finding citing the rule
     verbatim (`docs` or `prior`) and the design lines (`design`);
   - the rule requires behaviour the design does not describe: `ISSUE`
     and an `unspecified` finding.
4. When the rule concerns existing behaviour the design changes, also
   cite that code (`code`).
5. Changing an authoritative rule without saying so is a
   `nonconformance`.

## Severity

- `BLOCKER`: breaks a hard requirement of an authoritative document,
  cited as `docs` from the authoritative path.
- `MAJOR`: breaks a hard requirement of an informative document or a
  prior pack, or an authoritative recommendation with a stated
  correctness reason.
- `MINOR`: departs from a convention with no stated correctness impact.

No style preferences, no rules the design does not touch.
