# inference — do the design's conclusions follow from their premises? (stage 2)

Follow `rules/evidence.md`.

Scope: assumptions of kind `inference` (or your assigned subset). Its
premises are the assumptions in `depends_on` (read them from
`assumptions.json`); with an empty `depends_on`, the anchor lines and
their surroundings. Truth: T1 for counterexamples (code at the baseline
only), T3 for the logic of a step.

## Method, per inference

1. Write the argument in `method`: premises with their conditions and
   qualifiers, then the conclusion.
2. Check for these defects:
   - gap: the conclusion needs a premise the design never states;
   - scope shift: a premise holds per node, segment, request or
     partition, the conclusion claims it for all or for the whole;
   - dropped condition: a premise's condition the conclusion ignores;
   - strengthened quantifier: "usually" → "always", "some" → "all",
     "at most" → "exactly";
   - circularity: the conclusion is among its premises;
   - false premise the conclusion needs: cite the refuting code,
     without re-checking every premise.
3. Look for a code counterexample at the baseline — a configuration,
   call path or data shape where the premises hold and the conclusion
   does not — and cite it as `code`.
4. `PASS` when the conclusion follows, with a `reasoning` item stating
   the argument; otherwise `ISSUE` and a `broken-inference` finding
   naming the defect and any counterexample.

## Severity

- `BLOCKER`: carries the core mechanism or safety argument, and a code
  counterexample exists.
- `MAJOR`: carries a significant decision, and a code counterexample
  exists.
- `MINOR`: otherwise (reasoning-only findings are capped here).

Do not judge whether the conclusion is desirable.
