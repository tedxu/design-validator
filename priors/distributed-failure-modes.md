# Distributed failure modes

Prior knowledge pack for the `completeness` validator. Each section
names when it applies and what a design must say about it.

## Partial failure between dependent writes

Applies when an operation writes to two or more places (object storage
then metadata, local file then RPC, two tables) and later steps depend
on earlier ones.

- Which intermediate states can be observed or persisted if the
  operation stops after any step?
- Is there a single commit point after which the operation counts as
  done, and is everything before it safe to discard?
- Who finds and removes orphans left before the commit point, and how
  are they told apart from in-flight work?

## Response lost after a successful remote call

Applies when a caller retries an RPC, HTTP request or queue publish
after a timeout or connection error.

- Can the callee have applied the request even though the caller saw a
  failure?
- Is the request idempotent, or does it carry an identity (idempotency
  key, request id, deterministic name) that lets the callee detect a
  duplicate?
- What does the caller do when it cannot tell whether the first attempt
  succeeded?

## Crash and restart mid-operation

Applies when a process holds work in memory, or performs multi-step
work that must finish or roll back after a restart.

- What state survives a crash, and where is it read from on restart?
- Is the work resumed, redone or abandoned, and is redoing it safe?
- Can a restarted process act on stale in-memory assumptions loaded
  before the crash?

## Concurrent writers to the same state

Applies when two actors (threads, replicas, nodes, jobs) can modify the
same record, file, key or object.

- What prevents lost updates: locking, compare-and-swap, versions,
  single-writer ownership?
- What happens when two writers both believe they succeeded?
- Is the conflict detected, and by whom?

## Ownership change and stale owners

Applies when responsibility for a resource moves between actors
(leader election, shard reassignment, lease expiry, failover).

- Can the previous owner still act after losing ownership (GC pause,
  network partition, slow request in flight)?
- Is there fencing (epoch, term, lease token) that the storage or the
  callee checks on every write?
- What does the new owner do with work the old owner left half done?

## Readers racing writers and stale caches

Applies when data is read while it is being changed, or served from a
cache, replica or snapshot.

- Which version can a reader observe during and after an update?
- Can a reader see a reference to data that does not exist yet or no
  longer exists?
- How and when are caches invalidated, and what happens if an
  invalidation is lost or arrives out of order?

## Cleanup racing recovery or in-flight work

Applies when garbage collection, compaction, TTL expiry or deletion runs
concurrently with writers, readers or recovery.

- How does cleanup decide that something is unreferenced, and is that
  decision still valid when the deletion happens?
- Can cleanup remove data that an in-flight operation or a recovering
  node is about to reference?
- Is there a grace period or reference protocol, and what bounds it?

## Mixed versions during rolling upgrade or rollback

Applies when the design changes a wire format, persisted format, schema,
protocol step or default value.

- Can old and new versions run at the same time, and what does each do
  with the other's data or messages?
- Is persisted data written by the new version readable after a
  rollback?
- Are new fields optional with safe defaults, and is an unknown field
  ignored or rejected?

## Timeouts, cancellation and retries amplifying load

Applies when the design adds retries, fan-out, timeouts or cancellation
on paths under load.

- Are retries bounded and backed off, and do several layers retry the
  same failure?
- Does cancellation stop downstream work, or leave it running and
  holding resources?
- What happens under overload: queueing, shedding or collapse?

## Ordering and duplication in messages or logs

Applies when the design consumes or produces messages, events, WAL
entries or change streams.

- Can a message be delivered twice, out of order, or after a later
  message from the same source?
- Is processing idempotent per message, and what identifies a
  duplicate?
- What position or checkpoint is persisted, and is it persisted before
  or after the side effect?
