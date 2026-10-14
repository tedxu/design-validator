# Evaluation fixture

`fixture.sh` builds, in the current empty directory, a repository whose
design history supplies ground truth for `/design-validate-eval`:

- `docs/design/cache-ttl.md` was written before its implementation and
  relies on a TTL that does not exist; a fix commit and a revision later
  correct it.
- `docs/design/flush-retry.md` was committed with its code; its retry
  duplicates segments; a fix commit and a revision later correct it.
- `docs/design/cache-size.md` never changed afterwards, so it is skipped.

Run it by hand:

    WORK=$(mktemp -d) && cd "$WORK" && bash <plugin>/tests/eval/fixture.sh
    claude --plugin-dir <plugin>
    > /design-validate-eval

The evaluation writes its cases and report outside the fixture, under
`${XDG_CACHE_HOME:-~/.cache}/design-validator/eval/` (the `eval_dir`
printed by `eval.py prepare`).
