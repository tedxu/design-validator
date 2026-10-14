# simplicity — does every new mechanism earn its place? (stage 3)

Follow `rules/evidence.md`.

Scope: the whole design. Truth: T1 (code at the baseline) and T3.

## Method

1. List the mechanisms the design adds — components, layers,
   abstractions, options, caches, queues, background jobs, protocols,
   dependencies — citing the design lines. One check per mechanism.
2. Find the goal, invariant or constraint in the design that needs it.
   - Found: `PASS`, citing both places, with a `reasoning` item naming
     the requirement.
   - None: `ISSUE` and an `unnecessary-complexity` finding, with a
     `reasoning` item saying no requirement is stated.
3. Search the repository for a facility with the same responsibility
   (retry and backoff, caching, pooling, scheduling, serialisation,
   configuration loading, metrics, locking); record the search in
   `search_scope`. An existing equivalent the design duplicates without
   a reason: `ISSUE` and an `unnecessary-complexity` finding citing it
   (`code`).
4. Generality beyond the stated need — options, extension points or
   abstractions with one use and no stated future requirement — is an
   `unnecessary-complexity` finding.

## Severity

- `MAJOR`: a second implementation of a facility the repository already
  has (cited as `code`), so two paths must stay consistent.
- `MINOR`: otherwise; also every finding without `code` evidence.

No taste or theoretical purity; never ask for more abstraction.
