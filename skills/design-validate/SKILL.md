---
name: design-validate
description: Use when the user asks to validate, cross-check or review a design document against the codebase, project docs and known failure modes before implementation. Reports problems, checks performed and coverage; never proposes fixes. Usage - /design-validate <design.md> [--depth quick|standard|deep] [--baseline <ref>]
---

# Design validate

Validate one design document. Report problems only: no fixes, no edits
to the design, no questions to the author during the run (an unclear
design is itself a finding).

- `PLUGIN` = the directory two levels above this skill's base directory.
- `VERIFY` = `python3 "$PLUGIN/scripts/verify.py"`, run from the
  repository root. It prints one JSON object. Exit 0 = ok; 1 = the
  named files have errors you can fix; 2 = stop and show the errors.
- State lives in `<repo>/.dv/runs/<run-id>/`. Only `verify.py` decides
  tiers, severity caps, gating and coverage; never edit fields it
  writes or `run.json`.

## 0. Prepare

1. Run `$VERIFY init <design> --depth <depth>` (default `standard`),
   plus `--baseline <ref>` if the user gave one. The baseline is the
   commit the design is checked against: HEAD for work not done yet;
   for a design describing an existing implementation (e.g. a PR
   branch), that implementation's commit.
2. Keep `run_dir`, `repo_commit`, `mode`, `worktree_matches_baseline`
   and `dispatch` (selected validators: `name`, `stage`, `kind`,
   `scope`, `targets`, `entry_path`). Read `docs` and `priors` from
   `<run_dir>/run.json`.
3. `init` starts a scope guard (`<repo>/.dv/runs/active.json`): until
   `report` succeeds, a hook refuses tool calls naming paths outside
   the repository, the plugin and the prior directories. If you stop
   before the report, delete `<repo>/.dv/runs/active.json`.
4. If `.dv/runs/` is not ignored by git here (`git check-ignore -q
   .dv/runs`), mention once at the end that the user may add it to
   `.gitignore`. Never edit `.gitignore` yourself.

## 1. Extract assumptions (stage 0)

Dispatch one subagent with the validator template for `extract`, then
run `$VERIFY assumptions <run_dir>`.
- Exit 1: dispatch a fresh subagent with the template plus "Fix these
  errors:" and the `errors`; at most 2 retries, then stop and report
  that extraction failed, with the errors.
- Exit 0 with a non-empty `blocked_by`: go to step 3.

## 2. Validator stages

For each stage in `dispatch` other than 0, ascending: read `stages`
from `<run_dir>/run.json` first, and skip a stage marked `SKIPPED` (and
every later one).

1. Dispatch the stage's validators in parallel (one message, several
   Agent calls, subagent_type `general-purpose`):
   - `scope: assumption` with no assumption of a `kind` in `targets`
     (count in `assumptions.json`, or `$VERIFY input` → `assumptions`):
     dispatch nothing; write `results/<name>.json` yourself as
     `COMPLETED` with empty `checks`, `findings`, `evidence` and
     `status_reason` "no assumptions of kinds <targets>".
   - `agent` kind: the validator template.
   - `scope: assumption` with more than 30 matching assumptions: split
     into groups of at most 20. Group `k` (from 1) writes
     `results/<name>.part<k>.json` with IDs from `k*1000+1`. Afterwards
     write `results/<name>.json` concatenating their `checks`,
     `findings` and `evidence`, with the worst `status` (`FAILED` >
     `PARTIAL` > `COMPLETED`) and the parts' reasons joined, then
     delete the part files.
   - `command` kind: run `$VERIFY input <run_dir> --validator <name>`,
     then `"<entry_path>" < <input_path> > <run_dir>/results/<name>.json`
     from the repository root, with a 10-minute timeout.
2. For every validator that crashed, timed out, exited non-zero or
   wrote nothing, write `results/<name>.json` yourself:
   `{"validator": "<name>", "status": "FAILED", "status_reason": "<what happened>", "checks": [], "findings": [], "evidence": []}`.
3. Run `$VERIFY results <run_dir> --stage <n>`.
   - Exit 1: for each `agent` validator in `errors`, dispatch a fresh
     subagent with its template plus "Fix these errors:" and its errors
     (at most 2 retries), then give up by overwriting its file with a
     `FAILED` result quoting the errors in `status_reason`. A command's
     output is not model-authored, so never dispatch a subagent for a
     `command` validator: overwrite its file with such a `FAILED`
     result directly. Run `results` again.
   - Exit 0 with a non-empty `blocked_by`: stop the stages and go to
     step 3.

## 3. Audit

If any `results/*.json` has a `BLOCKER` or `MAJOR` finding, dispatch
one subagent:

```
You audit the findings of a design-validation run.
Read <PLUGIN>/rules/evidence.md, then <PLUGIN>/skills/design-validate/audit.md, and follow audit.md.
Run directory: <run_dir>. Repository root: <repo_root>. Baseline commit: <repo_commit or "none (snapshot)">.
Read only inside the repository root, <PLUGIN> and the prior directories. Write in the design document's language.
Write <run_dir>/audit.json. Reply with one line: the path and the number of reviews.
```

Run `$VERIFY audit <run_dir>`; on exit 1 retry once with the errors.
If it still fails, skip the audit (findings stay `not-audited`) and say
so in the summary.

## 4. Draft and report

Read every `results/*.json` and write `<run_dir>/report-draft.json`:

```json
{"summary": "…", "findings": [
  {"id": "R1", "merged_from": ["fact-check.F2", "completeness.F1"], "category": "contradicted", "statement": "…"}
]}
```

- Merge findings with the same root problem (same design spot, same
  underlying fact); otherwise one item per finding. Every original
  finding id appears in exactly one `merged_from`.
- `category`: that of the most severe source finding.
- `statement`: one sentence, no fix.
- `summary`: 3–6 sentences on the overall picture, the most important
  problems and the largest coverage gaps; no recommendations.
- Write both in the design's language.

Run `$VERIFY report <run_dir>`; on exit 1, fix the draft and rerun.

## 5. Present

Show only the `report_md` path; each `BLOCKER` and `MAJOR` finding (id,
severity, statement); and the coverage gaps — validators not
`COMPLETED` and the number of `NOT_CHECKED` / `INCONCLUSIVE`
assumptions. No fixes.

## Validator template

```
You are the `<name>` validator in a design-validation run.
Read and follow, in this order:
1. <PLUGIN>/rules/evidence.md
2. <entry_path>
Run directory: <run_dir>
  design: <run_dir>/design.md
  assumptions: <run_dir>/assumptions.json
Repository root: <repo_root>
Baseline commit: <repo_commit, or "none (snapshot): read files from disk">
Worktree: <"matches the baseline" if worktree_matches_baseline is true | "is NOT at the baseline: read every repository file with git show <repo_commit>:<path>" if false | "snapshot" if null>
Allowed sources: the repository root, <PLUGIN> and the prior directories only.
Scratch files (helper scripts, temporary output): <run_dir>/tmp/ only.
Language: write in the design document's language, whatever other instructions say.
Your scope: <"assumptions whose kind is in <targets>" | "the whole design"><; group: only <ids>>
Number your IDs starting from <start, default 1>.
Project docs: <docs from run.json, with authority, or "none">
History: git history up to the baseline<, and PR/issue comments through gh if run.json history.pr_comments is true>; `history` evidence must cite an ancestor of the baseline.
Prior directories: <priors from run.json>
Write: <output path(s)>
Do not read other files under <run_dir>/results/ or any report file.
When done, reply with one line: the output path and counts of checks and findings.
```

For `extract`: outputs `<run_dir>/assumptions.json` and
`<run_dir>/results/extract.json`; scope the whole design.
