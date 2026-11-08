# ADR-0002 — Process every event twice: provisional stream, authoritative batch

**Status:** Accepted · 2026-11-07

## Context

Commerce events arrive continuously. A dashboard that waits for the nightly
batch is too slow; a dashboard that trusts only the stream cannot restate an
order when a refund or a late payment arrives. Both views are legitimate, but
they answer different questions.

## Decision

Build **one event generator**, consumed by **two pipelines**:

| | `ledgerline-stream` | `ledgerline-batch` |
|---|---|---|
| Latency | seconds | hours |
| Guarantee | at-least-once + idempotent sink (ADR-0003) | idempotent batch load |
| Source of truth | provisional | **authoritative** |
| Recovery | checkpoint restore, replay | re-run the batch |
| Output | operational dashboard | finance close, reconciliation |

The batch layer is the source of truth. The stream is a provisional view that
may be late, duplicated, or missing events; it is never reconciled against
itself, only against batch.

`eventforge` is deterministic (seed + day → identical bytes), so both pipelines
can be reconciled on `event_id` and the same demo can be replayed from scratch.

## Alternatives considered

1. **Streaming only (Kappa).** Simpler on paper, but restatements and late data
   become the whole problem, and there is no authoritative layer to reconcile
   against. Also a weaker portfolio story: it hides the batch skills the role
   asks for.
2. **Batch only (Lambda without speed layer).** Loses the latency story and
   the Flink/checkpoint requirements.
3. **Two independent generators.** Rejected: the two paths could disagree
   because of the source, and reconciliation would be meaningless.

## Consequences

- Two repos, one shared contract (`event_id`, cents, event time).
- The dashboard must label every number **provisional** or **authoritative**.
- Reconciliation is a first-class job, not a debugging step.
- Extra work: the generator must be deterministic and versioned
  (`generator_version` in the manifest/ground truth).
