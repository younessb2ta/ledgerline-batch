# ADR-0007 — Volume anomaly detection: trailing average band now, median/MAD later

**Status:** Accepted · 2026-11-08 · revisit when 30+ days of history exist

## Context

Volume is the only signal that catches a **self-consistent truncation**: the
extract writes a manifest over the smaller files, so hashes, row counts, and
timestamp spans all agree. INC-001 is exactly that failure.

The original plan called for a median/MAD test. That is statistically the
right choice for a metric with outliers, but it needs history. The demo has
three days; a median over a three-point window is just the middle value, and a
MAD of zero makes every deviation infinitely significant.

## Decision

Two checks at different layers:

1. **Gate 1 (per batch, exact):** compare each transactional table with the
   generator's ground-truth count for that day
   (`volume.row_count_vs_baseline`). This is exact, not statistical — the
   generator is deterministic, so the expected count is known.
2. **Gate 2 (trend, statistical):** `assert_daily_volume_within_band` compares
   each day's order count with the trailing 7-day average and fails when the
   deviation exceeds `volume_tolerance_pct` (30%).

The band uses a **trailing mean**, not median/MAD, because it is defined for
the first days of history and is easy to explain during an incident. The
trade-off is documented rather than hidden: a single outlier in the window
moves the baseline, and a uniform multiplicative corruption keeps every day
inside the band.

## Alternatives considered

1. **Median/MAD (plan §7).** Better outlier resistance, but undefined/zero
   with three days. Upgrade path: switch when there are 30+ days, or backfill
   synthetic history from `eventforge`.
2. **Fixed threshold.** Rejected: legitimate campaigns and seasonality change
   volume; a fixed number would either page constantly or never.
3. **No trend test, rely on gate 1 only.** Rejected: gate 1 only catches
   per-batch truncation. A mart that loses a partition after the load would
   pass gate 1 and be caught only by the band.

## Consequences

- The tolerance is a project var (`volume_tolerance_pct`), not hardcoded.
- A band failure pages the `volume-anomaly` runbook; a gate-1 failure pages
  `gx-gate-failure`. Different diagnosis, different owner.
- DR-001 confirmed the known limitation: a fan-out that scales all days
  equally **passes** the band and is caught by grain uniqueness instead. The
  two tests are complementary.
- Revisit trigger: 30 days of real history, or a false positive from a
  legitimate campaign.
