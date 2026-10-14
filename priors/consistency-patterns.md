# Consistency patterns

Prior knowledge pack for the `completeness` and `conformance` validators.
Each section names when it applies and what a design must say about it.

## Idempotency keys

Applies when a request, message or task can be delivered or executed
more than once: retries, redelivery, replay after restart.

- What identity lets the receiver recognise a repeat (request id,
  deterministic name, sequence number)?
- Where is that identity stored, and for how long?
- Is the second execution a no-op, or does it repeat side effects?

## Fencing tokens and epochs

Applies when ownership of a resource can move between processes: leader
election, lease handover, shard or channel reassignment.

- Can an old owner keep acting after a new owner takes over?
- Does every write carry a token or epoch that the storage or receiver
  checks against the current owner?
- What happens to work the old owner started but did not finish?

## Commit points

Applies when an operation has several steps and readers must see either
all of it or none of it.

- Which single step makes the operation visible or durable?
- What do readers see before that step, and what happens to the earlier
  steps if the operation stops before it?
- Is the commit step itself atomic in the storage it uses?

## Cache invalidation

Applies when the design keeps a copy of data (cache, index, replica,
in-memory view) that can change at its source.

- What event invalidates or refreshes the copy, and who emits it?
- How stale can a reader's view be, and does the design state that
  bound?
- What happens when an invalidation is lost or arrives out of order?

## Read-your-writes and visibility

Applies when a client writes and then reads, possibly through a
different node, replica or path.

- When does a completed write become visible to the same client and to
  others?
- Does any read path bypass the place where the write is applied?
- Is the guarantee stated per client, per session or globally?

## Ordering guarantees

Applies when the design relies on events, messages or writes being
processed in a particular order.

- Which component guarantees the order, and within what scope
  (per key, per partition, global)?
- What happens on retry, redelivery or failover: can order change?
- Does any consumer process the same stream in parallel?

## Leases and timeouts

Applies when correctness depends on a lease, heartbeat or timeout
expiring.

- What does the holder do when it cannot renew in time: stop acting, or
  keep going?
- Are clocks of different processes compared, and how much may they
  drift?
- Can a paused process (GC, stalled disk) resume after its lease has
  expired and act on stale assumptions?
