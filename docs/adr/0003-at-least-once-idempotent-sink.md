# ADR-0003 — Exactly-once via at-least-once + idempotent sink, not 2PC

**Status:** Accepted · 2026-11-07 (implementation lands with `ledgerline-stream`)

## Context

Flink can give end-to-end exactly-once with two-phase commit (2PC) sinks, but
only if the sink supports transactions: Kafka transactional producers, or
Iceberg/filesystem sinks with atomic commits. The streaming target on this
machine is a **local Postgres** sink, and Docker is unavailable on macOS 12
(see `docs/toolchain.md`), so a containerized transactional sink is not an
option.

The requirement is a demonstrable, honest exactly-once story, not a checkbox.

## Decision

Use **at-least-once delivery + an idempotent sink**:

- Kafka source with checkpointed offsets (Flink 1.20, RocksDB state).
- The sink upserts on the event's natural key: `ON CONFLICT (event_id) DO
  NOTHING` (Postgres), so replays after a checkpoint restore converge.
- Duplicates are therefore harmless by construction; a kill/restore test
  (`make demo-exactly-once`) compares sink counts and sums against the
  generator's ground truth after a `kill -9`.

This is **effectively-once** at the sink, not distributed exactly-once: the
side effects are idempotent given the key. That distinction is stated
explicitly rather than hidden.

## Alternatives considered

1. **2PC / transactional sink (Kafka transactions, Iceberg).** Correct
   end-to-end guarantee, but requires a transactional sink and object storage.
   Documented as the paid/production upgrade, with its costs: longer commit
   intervals, sink-side transaction support, and cross-system recovery
   complexity.
2. **Dedup by window in Flink state.** Works, but state grows with the dedup
   horizon and still needs an idempotent write for the final guarantee.
3. **At-most-once.** Rejected: silent data loss is worse than duplicates for a
   ledger.

## Consequences

- Every downstream table needs a stable natural key. `event_id` is a UUIDv5
  derived from `(seed, day, sequence)`, so it is stable across replays.
- The dashboard must be safe to read during replays (upserts, not appends).
- The kill/restore demo must show **equal counts and equal sums**, not just
  “no crash”.
- If the key changes, the guarantee breaks; the key is part of the generator
  contract and is tested.
