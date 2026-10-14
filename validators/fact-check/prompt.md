# fact-check — does the design describe the existing system correctly? (stage 1)

Follow `rules/evidence.md`.

Scope: assumptions of kind `current-fact` or `compatibility` (or your
assigned subset). Truth: T1 only — code at the baseline, prior packs,
or version-matched official documentation of external dependencies.

## Method, per assumption

1. List every concrete referent: paths, packages, types, functions,
   fields, RPCs, messages, configuration keys, commands, metrics.
2. Verify each exists at the baseline with the shape the design says
   (signature, field type, default, call direction). A referent the
   design introduces as new is not missing; say so in `method`.
3. Verify the claimed behaviour, not just existence: read the code
   path, including branches, error handling and configuration switches.
4. Qualifiers are claims. For "all", "only", "never", "always", "every
   caller", grep for counterexamples (call sites, consumers, other
   paths) and record the searches.
5. Behaviour of an external dependency needs `external` evidence for
   the manifest's version; without it the check is `INCONCLUSIVE`.

At least one check per assumption. A contradicted assumption gets an
`ISSUE` check and a `contradicted` finding citing the refuting code.

## Severity

- `BLOCKER`: the motivation or core mechanism rests on the contradicted
  fact; name what rests on it.
- `MAJOR`: a significant part of the design rests on it.
- `MINOR`: a peripheral inaccuracy that does not change the design.

No style, naming or design-quality findings.
