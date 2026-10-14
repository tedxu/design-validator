# Ground truth for one evaluation case

List the problems of a design's first version that its later history
corrected or confirmed. Do not judge the design yourself or propose
fixes. Read only `case.json` and `evolution/` in the case directory —
never `snapshot/`, `run-result.json`, `claude.log` or any `.dv/runs`
output.

## Inputs

- `case.json`: design path, first commit, baseline and its kind,
  revision commits (`revisions`) and fix commits (`fixes`).
- `evolution/design-v1.md`: the design as first committed.
- `evolution/revisions.patch`: later changes to the design, oldest
  first.
- `evolution/fixes.patch`: later commits whose subject starts with
  "fix" and that touched code the design changed or cites, oldest
  first.

## What counts

A problem of the first version, in its terms, that a revision corrected
(a claim, mechanism, invariant or scope changed because it was wrong,
incomplete or unsafe) or a fix commit repaired (a defect in behaviour
the first version specified, or should have specified).

Not: scope or features added later; wording, formatting, status or link
updates; fixes unrelated to what the first version says or should have
said; problems you notice that the history does not show.

## Output: `<case_dir>/truth.json`

```json
{"items": [
  {"id": "G1", "statement": "…", "source": "fix", "commits": ["<sha>"], "tier": "T1", "reviewed": false}
]}
```

- `id`: `G1`, `G2`, …
- `statement`: one sentence, in the design's language, naming what the
  first version got wrong or left out and where.
- `source`: `fix` when a fix commit shows it, else `revision`.
- `commits`: from the `case.json` list for that source (at least 7 hex
  characters).
- `tier`: `T1` for `fix`, `T2` for `revision`.
- `reviewed`: always `false`; a human may change it.

An empty `items` list is valid when the history shows no such problem.
