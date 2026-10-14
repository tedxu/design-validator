# completeness — are failure, concurrency and recovery cases covered? (stage 3)

Follow `rules/evidence.md`.

Scope: the whole design. Knowledge: every prior pack in your prior
directories, starting with `distributed-failure-modes.md`.

## Method

1. List the design's side effects and coordination points: persistent
   and object-storage writes, RPC and network calls, messages produced
   or consumed, ownership or leadership changes, cache or state
   publication, deletion and cleanup, format or protocol changes. Cite
   the design lines (and the code, when the design builds on it).
2. For each prior section, decide whether it applies by stating the
   concrete premise: which step, under which condition. No concrete
   premise, no applicability.
3. For each applicable section, does the design specify the behaviour
   it asks about?
   - Specified: `PASS`, citing the design lines and the section.
   - Not specified: `ISSUE` and an `unspecified` finding.
   - Specified but failing under the scenario (shown by code or the
     section): `ISSUE` and a `missing-scenario` finding.
4. Record one "applicability screening" check (`PASS`) with one
   `reasoning` item listing each section judged not applicable and why.

Finding evidence: the section (`prior`), the design lines (`design`),
and code showing the step is real when it exists (`code`), e.g. a
non-idempotent RPC handler.

## Severity

- `MAJOR`: the unspecified case can lose or corrupt data, duplicate a
  side effect, expose a reference to missing data, or leave the system
  unrecoverable, and the step is real (cited in design or code).
- `MINOR`: otherwise.

Report risks backed by evidence and unstated premises, never
unsupported fears. Do not propose mechanisms or judge whether the
design is the best approach.
