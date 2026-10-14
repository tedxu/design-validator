---
name: design-validate-eval
description: Use when the user asks to evaluate the design validator on a repository's own design history (recall and precision against later revisions and fixes). Usage - /design-validate-eval [--limit N] [--designs a.md,b.md] [--depth quick|standard|deep] [--stop-after prepare]
---

# Design validator evaluation

Evaluate `/design-validate` on historical designs of the current
repository. Do not change the repository, and do not propose fixes to
designs or to the validator.

- `PLUGIN` = the directory two levels above this skill's base directory.
- `EVAL` = `python3 "$PLUGIN/scripts/eval.py"`, run from the repository
  root. It prints one JSON object. Exit 0 = ok; 1 = the named files
  have errors you can fix; 2 = stop and show the errors.
- Everything lives in `<eval_dir>/<case>/` (`eval_dir` is printed by
  `prepare`; by default under `$XDG_CACHE_HOME` or `~/.cache`
  `/design-validator/eval/`, outside the repository, so snapshots do
  not pick up its current `CLAUDE.md`). Each case has `case.json`,
  `evolution/` (`design-v1.md`, `revisions.patch`, `fixes.patch`),
  `snapshot/`, and later `truth.json`, `run-result.json`,
  `matches.json`.

## 1. Prepare

Run `$EVAL prepare [--limit N] [--designs <comma list>]`. If `cases` is
empty, tell the user why (the `skipped` reasons, or that
`eval.design_globs` in `.dv/config.yaml` matches nothing) and stop.

Keep the `case_id`s as `CASES` (comma list) and pass `--cases CASES` to
every later command, so cases from earlier evaluations in the same
eval dir are left alone.

## 2. Ground truth

Run `$EVAL check-truth --cases CASES`. For every entry in `missing`
(`case_id`, `case_dir`), dispatch a subagent (all in one message,
subagent_type `general-purpose`):

```
You extract ground truth for one evaluation case.
Read <PLUGIN>/skills/design-validate-eval/truth.md and follow it.
Case directory: <case_dir>
Write <case_dir>/truth.json. Reply with one line: the path and the number of items.
```

Run `$EVAL check-truth --cases CASES` again. For each case in `errors`,
dispatch a fresh subagent with the same template plus "Fix these
errors:" and its errors, at most 2 retries per case; if it still fails,
delete its `truth.json` and report the case as excluded. Exception: if
the erroring `truth.json` has any item with `reviewed: true`, a human
edited it — show the errors, stop for that case, and neither regenerate
nor delete the file.

With `--stop-after prepare`: show each case (design, `baseline_kind`,
number of truth items, path of `truth.json`), say the user may edit
`truth.json` (set `reviewed: true`, add or remove items) and run
`/design-validate-eval` again to continue (edits must still pass
`check-truth`), and stop.

## 3. Run

If `valid` from the last `check-truth` is empty, report that no case has
valid truth and stop. Never pass an empty `--cases`: it runs every case.

Run `$EVAL run --depth <depth, default standard> --cases <cases with
valid truth>` in the background with a generous time limit, and wait:
each case runs a full headless `/design-validate` (5–30 minutes). Cases
whose previous result has a report and no error are skipped; failed or
timed-out cases run again. Report every result with an `error`.

## 4. Match

Run `$EVAL check-matches --cases CASES`. For every entry in `missing`,
dispatch a subagent (all in one message):

```
You match a validation report against ground truth for one evaluation case.
Read <PLUGIN>/skills/design-validate-eval/match.md and follow it.
Case directory: <case_dir>
Report: <report>
Write <case_dir>/matches.json. Reply with one line: the path and the count per verdict.
```

Run `$EVAL check-matches --cases CASES` again. For each case in
`errors`, dispatch a fresh subagent with the template plus "Fix these
errors:" and its errors, at most 2 retries; if it still fails, delete
its `matches.json` and report the case as excluded. List the cases in
`no_report` as not scorable.

## 5. Score and present

Run `$EVAL score --cases CASES`. Show only: the `report_md` path;
recall and strict and lenient precision (`recall`, `precision`);
excluded cases with reasons; and whether the truth was reviewed (the
boolean `truth_reviewed` in the file at `report_json`) — if not, say
the numbers rest on unreviewed weak truth and are not a conclusion.
