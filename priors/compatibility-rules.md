# Compatibility rules

Prior knowledge pack for the `impact` and `conformance` validators. Each
section names when it applies and what a design must say about it.

## Wire and API field changes

Applies when the design adds, removes, renames or retypes a field, enum
value, RPC or endpoint that another process or a client reads or writes.

- Do old readers ignore an added field, or do they reject it?
- Does a removed or renamed field still have readers or writers at the
  baseline, inside or outside the repository (clients, SDKs, tools)?
- Is a retyped field read by code that assumes the old type?
- Are new enum values handled by every switch that consumes the enum?

## Persisted format evolution

Applies when the design changes data that outlives the process: files,
object keys, table schemas, WAL or log records, snapshots, checkpoints,
metadata entries.

- Can the new code read everything the old code wrote, including data
  written long ago?
- Is there a version marker that tells readers which format they hold?
- Who converts old data, when, and what happens to data not yet
  converted?

## Mixed versions during rolling upgrade

Applies when processes that exchange data or share state are upgraded
one at a time.

- What happens when an old process receives data or a request produced
  by a new one, and the reverse?
- Is the new behaviour enabled only after every process can handle it?
- Can a new process act on shared state in a way an old process
  misreads?

## Rollback after new data is written

Applies when new code writes data in a new format or with new meaning,
and the release may be rolled back.

- Can the previous version read what the new version wrote?
- If not, is the new format gated so that it is written only after
  rollback is no longer expected?
- Does the design say what rollback means for data written in between?

## Default values and missing fields

Applies when the design adds a field, setting or parameter whose absence
must mean something.

- What does a reader do when the field is absent: old data, old
  writers, partial updates?
- Does the zero value of the type mean the same as "not set"?
- Does the default preserve the behaviour that existed before the
  change?

## Configuration and flag changes

Applies when the design adds, removes, renames or changes the default of
a configuration key, flag or environment variable.

- Do existing deployments keep their behaviour without editing their
  configuration?
- Are renamed or removed keys still read, rejected loudly, or silently
  ignored?
- Is a refreshable setting read once per operation, so that one
  operation never sees two values?

## Removal and deprecation

Applies when the design removes a code path, API, field, flag, metric
or document, or replaces one mechanism with another.

- Is every consumer of the removed thing changed or retired?
- What remains after the change: dead branches, unused flags, shims,
  metrics and docs that describe the old behaviour?
- Is there a period in which both mechanisms run, and what keeps them
  consistent during it?
