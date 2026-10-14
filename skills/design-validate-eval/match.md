# Matching findings to ground truth

For one evaluation case, decide for every finding in the report whether
it names a ground-truth problem. Read only the case directory and the
given report.

## Inputs

- `<case_dir>/truth.json`: the truth items.
- The report (`report.json`): `findings`, each with `id`, `severity`,
  `category`, `statement` and `validators`.
- `<case_dir>/evolution/`: `design-v1.md`, `revisions.patch`,
  `fixes.patch`.

Do not change `truth.json`. A finding the history confirms but no truth
item covers is `unrelated`.

## Verdicts

One `verdict` per finding:
- `match`: the same underlying problem as one or more truth items —
  same claim or mechanism of the first version, same defect — so acting
  on it leads toward the later correction. Wording and severity need
  not agree. Be strict: same file, different defect is `unrelated`.
- `refuted`: the history shows the point was examined and stood — what
  it criticises survives every revision and later code relies on it
  without a fix, or a revision argues against it. Say what shows it.
- `unrelated`: anything else, including possibly right findings the
  history neither confirms nor refutes.

## Output: `<case_dir>/matches.json`

```json
{"matches": [
  {"finding_id": "R1", "verdict": "match", "truth_ids": ["G1"], "reason": "…"}
]}
```

Every report finding appears exactly once (`finding_id`); `truth_ids` is non-empty for
`match` and empty otherwise; `reason` is one sentence.
