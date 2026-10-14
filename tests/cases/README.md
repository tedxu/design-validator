# Fixture cases

Each case builds a small repository and a design with known problems.
Run one by hand:

    CASE=stale-fact
    WORK=$(mktemp -d) && cd "$WORK" && bash ~/Source/design-validator/tests/cases/$CASE/fixture.sh
    claude --plugin-dir ~/Source/design-validator
    > /design-validate docs/design.md
    python3 ~/Source/design-validator/tests/check_case.py \
        ~/Source/design-validator/tests/cases/$CASE "$WORK"/.dv/runs/<run-id>

`expected.json` keys: `must_find` and `must_not_find` (lists of filters
with optional `validator`, `category` (string or list) and
`min_severity`), and `coverage` (validator name → expected status).

`args` (optional) is appended to `/design-validate docs/design.md`, for
example `"--depth deep"` for cases that need the `high`-cost `impact`
validator.

Run every case headless (about 5 minutes each, in parallel):

    python3 tests/run_cases.py --workdir /tmp/dv-cases --jobs 3

It prints PASS/FAIL per case, and writes `summary.json` and
`validation-runs.md` (every run's design and report) into the workdir.
