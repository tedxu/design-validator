# alternatives — did the design leave out a simpler existing route? (stage 3)

Follow `rules/evidence.md`.

Scope: the whole design. Truth: T1 (code), T2 (project documents,
history) and T3.

## Method

1. State the problem the design solves in one sentence, citing its goal
   or motivation lines.
2. Climb the ladder from the bottom, stopping at the design's own
   route:
   1. do nothing: is the problem real at the baseline, or already
      handled?
   2. delete something, or change an existing flag, parameter or
      switch;
   3. reuse a facility already in the repository;
   4. the platform or standard library (official documentation only);
   5. a dependency already in the manifest (cite its manifest version);
   6. a new dependency;
   7. a minimal mechanism of the project's own.
3. For each rung below the design's route, search the repository for a
   concrete candidate (similar names, packages, flags, helpers) and
   record it in `search_scope`. One check per rung. A rung without a
   candidate gets a `reasoning` item stating what was searched and
   where you stopped, and its check is `PASS`, not `INCONCLUSIVE`.
4. A candidate counts only if it exists (cited as `code`, `docs`,
   `history` or `external`) and could solve the problem under the
   design's constraints. If the design discusses it and gives a reason
   against it, `PASS`.
5. An existing candidate the design does not discuss: `ISSUE` and an
   `unconsidered-alternative` finding naming it and the undiscussed
   trade-off.

## Severity

- `MINOR` always (capped by `verify.py`).

Do not say which route is better, and do not invent candidates absent
from the repository, its dependency manifest or official documentation.
Never read dependency source or package caches outside the repository.
