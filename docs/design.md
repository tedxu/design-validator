# design-validator: design

## Goal

Design documents often carry wrong beliefs about the existing system,
unproven inferences, missing failure handling and unsupported
performance claims. design-validator cross-checks one design against
the code, project documents, prior knowledge packs and history, and
reports:

1. problems: what does not hold, is incomplete or is unjustified;
2. checks performed, including those that passed;
3. coverage: what was not checked, and why.

Principles:

- Problems only, never fixes. The author revises the design.
- Non-interactive: an unclear design is a finding, not a question.
- No separate API calls: all model work runs as subagents inside the
  Claude Code session.
- Evidence is tiered and every verdict is traceable to a citation.
- Not checked is never reported as passed.
- Projects can add validators and prior packs.
- Determinism where it matters: citation checks, grading and gating are
  done by a script, everything else by the model.

## Architecture

```text
/design-validate <design.md>
  0. init               verify.py writes run.json, starts the scope guard
  1. extract            subagent -> assumptions.json   -> verify.py
  2. stages 1..3        parallel subagents / commands  -> verify.py (gate)
  3. audit              subagent re-reads BLOCKER/MAJOR evidence
  4. report             main session drafts            -> verify.py
                        .dv/runs/<run-id>/ (JSON + Markdown only)
```

The skill orchestrates; `scripts/verify.py` (standard library only) is
the only deterministic tool. State is the files in the run directory.

Plugin layout: `skills/` (flows), `validators/<name>/` (`validator.yaml`
+ `prompt.md`), `rules/evidence.md` (shared validator rules), `priors/`
(knowledge packs), `schemas/` (output contracts), `scripts/`
(`verify.py`, `eval.py`), `hooks/` (scope guard), `examples/`, `tests/`.

Project layout, all optional:

```text
<repo>/.dv/
  config.yaml
  validators/<name>/     project validators (same name replaces a built-in)
  priors/*.md            project prior packs
  runs/                  run output and the scope-guard marker
```

## Evidence tiers

| tier | sources |
|---|---|
| T1 | `code` at the baseline, `prior`, `sandbox`, `external` with a version matched in the dependency manifest |
| T2 | `docs`, `history`, `external` without a matched version |
| T3 | `reasoning` (a lead, never proof) |

`design` citations (lines of the design itself) count as T1 only for
`ambiguous`, `unspecified` and `inconsistent` findings.

- `verify.py` sets the tier from `source`, re-reads every excerpt at the
  cited location and discards evidence that does not match; a check
  left without valid evidence becomes `INCONCLUSIVE`.
- A finding backed only by T3 is capped at `MINOR`.
- A `BLOCKER` needs T1 evidence; `conformance` may also use documents
  under a path marked `authoritative`.
- Each validator declares a maximum severity.
- A `BLOCKER` that survives grading in a stage skips later stages.

## Validators

| stage | name | scope |
|---|---|---|
| 0 | extract | assumptions (`current-fact`, `inference`, `compatibility`, `invariant`, `performance`, `design-choice`); internal consistency |
| 1 | fact-check | current facts and compatibility claims against code |
| 1 | conformance | the project's documented rules and prior packs |
| 2 | inference | conclusions against their premises |
| 2 | claims | performance claims against `performance-evidence.md` |
| 2 | impact | consumers of what changes (`deep` only) |
| 3 | completeness | failure, concurrency and recovery scenarios |
| 3 | simplicity | mechanisms without a requirement; duplicated facilities |
| 3 | alternatives | simpler existing routes not discussed (`MINOR` only) |

`--depth` selects by cost: `quick` (low), `standard` (+ medium), `deep`
(+ high).

### Project validators

`validator.yaml`:

| field | meaning |
|---|---|
| `name` | equals the directory name |
| `kind` | `agent` (prompt run by a subagent) or `command` (executable) |
| `stage` | 1 or higher; one stage runs in parallel |
| `scope` | `assumption` (kinds in `targets`) or `design` |
| `truth_tiers` | tiers that may decide a check |
| `can_block`, `max_severity`, `blocker_evidence` | severity limits |
| `cost` | `low`, `medium` or `high` |
| `entry` | `prompt.md`, or the executable |

An agent prompt follows `rules/evidence.md`, states scope and tiers,
gives a method ending in checks and findings, and defines severity.

A command validator receives the output of `verify.py input <run_dir>
--validator <name>` on stdin (`repo_root`, `repo_commit`,
`worktree_matches_baseline`, filtered `assumptions`, `context`,
`id_prefix`) and prints a result file on stdout; it runs from the
repository root with a 10-minute timeout, reads files with `git show`
at `repo_commit` unless that is null, and may cite `sandbox` evidence.
See `examples/validators/path-check`.

## Configuration (`.dv/config.yaml`)

```yaml
docs:
  - path: docs/rules
    authority: authoritative
  - path: docs/design
    authority: informative
priors: [.dv/priors]
validators:
  disable: [alternatives]
  override:
    claims: {stage: 3}
history:
  pr_comments: false     # true: read PR/issue comments through gh
eval:
  design_globs: ["docs/design/**/*.md"]
```

## Scope guard

While a run is active (`.dv/runs/active.json`, at most 2 hours), a
PreToolUse hook refuses tool calls that name paths outside the
repository, the plugin and the prior directories, and `verify.py`
rejects output text that names such paths. Free text must be in the
design's language.

## Evaluation (`/design-validate-eval`)

Measures the validator on a repository's own history.

1. `eval.py prepare`: picks designs matching `eval.design_globs` with
   the most later revisions and related fix commits. The baseline is the
   first commit if it also changed code (`as-built`), else its parent
   (`pre-implementation`). It writes the evolution material (first
   version, later revisions, related fixes) and a `git archive` snapshot
   of the baseline without `.git`, under
   `${XDG_CACHE_HOME:-~/.cache}/design-validator/eval/`, outside the
   repository so the snapshot cannot load the repository's current
   `CLAUDE.md`.
2. A subagent derives ground truth from the evolution material: problems
   of the first version that a revision corrected (T2) or a fix commit
   repaired (T1). Humans may review it (`reviewed: true`).
3. `eval.py run`: headless `/design-validate` in each snapshot, with git
   unable to see the outer repository.
4. A subagent matches each finding to the truth: `match`, `refuted` or
   `unrelated`.
5. `eval.py score`: recall by tier, strict precision (match / all),
   lenient precision (match / (match + refuted)), refuted BLOCKERs,
   citation failure rate, coverage gaps, time and cost.

## Non-goals

Fix suggestions, comparing rounds, interactive confirmation, a
standalone CLI, built-in static analysis or model checking, confidence
scores.
