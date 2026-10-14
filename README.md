# design-validator

A Claude Code plugin that cross-checks a design document against the
codebase, project documentation, prior knowledge packs and git history.
It reports problems, the checks it performed and what it did not cover.
It never proposes fixes.

Every finding cites evidence (code, docs, priors, history), and a
deterministic script (`scripts/verify.py`) re-reads each citation,
grades its evidence tier and caps severities. Findings backed only by
the model's reasoning cannot rise above `MINOR`.

## Install

In a Claude Code session:

    /plugin marketplace add tedxu/design-validator
    /plugin install design-validator@design-validator

Then restart Claude Code. To update later:

    /plugin marketplace update design-validator
    /plugin update design-validator@design-validator

Requirements: `python3` (3.9+) and `git` on `PATH`. No Python packages.

## Use

    /design-validate docs/design/my-feature.md [--depth quick|standard|deep]

For a design that describes an existing implementation (for example a
PR branch), check it against that implementation's commit:

    /design-validate docs/design/my-feature.md --baseline pr-branch

The report is written to `.dv/runs/<run-id>/report.md` in the
repository. The plugin does not touch your `.gitignore`; add `.dv/runs/`
to it if you do not want run output in `git status`. `.dv/config.yaml`,
project validators and prior packs next to it are meant to be
committed.

While a run is active, a PreToolUse hook keeps tool calls inside the
repository, the plugin and the prior directories.

Depth selects validators by cost: `quick` runs extraction plus the
low-cost validators; `standard` adds the medium-cost ones; `deep` also
runs `impact`. A standard run on a small design costs a few US dollars
of model usage, more on large designs.

## Validators

| stage | validator | checks |
|---|---|---|
| 0 | extract | turns the design into assumptions; internal consistency |
| 1 | fact-check | claims about the existing system against code |
| 1 | conformance | the project's own documented rules |
| 2 | inference | whether conclusions follow from their premises |
| 2 | claims | performance and benefit claims |
| 2 | impact | consumers and compatibility of what the design changes (`deep`) |
| 3 | completeness | failure, concurrency and recovery cases |
| 3 | simplicity | mechanisms without a stated requirement, duplicated facilities |
| 3 | alternatives | simpler existing routes the design does not discuss |

Projects can add or replace validators and prior packs under `.dv/`;
see [docs/design.md](docs/design.md#project-validators) and
`examples/validators/path-check`.

## Evaluation

`/design-validate-eval` measures recall and precision on a repository's
own design history: it validates first versions of designs and
compares the findings with what later revisions and fix commits
corrected. Set `eval.design_globs` in `.dv/config.yaml`, then:

    /design-validate-eval --limit 5

Results go to `${XDG_CACHE_HOME:-~/.cache}/design-validator/eval/`,
outside the repository. Each evaluated design costs one full
validation run.

## Development

    python3 -m unittest discover -s tests/unit -v
    claude --plugin-dir .    # disable an installed copy first

Design: [docs/design.md](docs/design.md)

## License

MIT
