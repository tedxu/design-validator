# impact — what else does the change reach? (stage 2)

Follow `rules/evidence.md`.

Scope: the whole design. Truth: code at the baseline (T1), project
documents and history (T2). Knowledge: `compatibility-rules.md` and any
project prior pack.

## Method

1. List every existing thing the design changes, removes, renames or
   redefines: functions, types, fields, RPCs and messages, persisted
   formats (files, object keys, tables, log records), configuration keys
   and defaults, metrics, flags, environment variables, documented
   behaviour. Cite the design lines.
2. Find each one's consumers at the baseline across the whole
   repository: callers, format readers, deserialisers, tools and
   scripts, tests pinning the behaviour, docs and dashboards. Record
   the queries in `search_scope`.
3. For each consumer, does the design say what happens to it (changed
   together, kept compatible, migrated, or broken on purpose with a
   plan)?
   - Covered: `PASS`, citing the consumer and the design lines.
   - Not mentioned, and it breaks or silently changes behaviour:
     `ISSUE` and an `impact` finding citing the consumer (`code`) and
     the design lines (`design`).
4. For anything persisted or exchanged between processes, apply the
   relevant `compatibility-rules.md` sections: mixed versions in a
   rolling upgrade, rollback after new data is written, defaults for
   missing fields. An unaddressed section is an `unspecified` finding
   citing the section, the design lines and the format's code.
5. Leftovers: dead branches, unused flags and keys, shims, metrics,
   documents of the old behaviour. An `unspecified` finding when the
   design is silent on leftovers that stay reachable or misleading.

## Severity

- `BLOCKER`: a required consumer or compatibility path breaks (data
  unreadable, mixed-version cluster fails) and the design does not
  mention it.
- `MAJOR`: a consumer breaks or silently changes behaviour, unmentioned.
- `MINOR`: leftovers and documentation drift.

Do not report consumers the design already covers.
