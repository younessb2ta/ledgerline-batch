# Demo video — 3 minutes

A recording guide for `ledgerline-batch`. The goal is not to tour every file; it
is to prove four claims: the data is deterministic, a bad load is stopped, the
warehouse is tested, and the cost is measured.

## Before recording

```bash
uv sync
gcloud auth application-default login      # sandbox project, no billing
make gen                                   # seed 42, 2026-11-01
make load                                  # gate 1 passes, rows land in raw_*
make dbt-build                             # 72 nodes, 57 tests
```

Keep these windows open and ready:

| Window | Content |
|---|---|
| Terminal A (large font) | commands below |
| Terminal B | `open bench/report.md` or preview it |
| Browser | BigQuery console, `raw_orders` and `marts.fct_orders` row counts |
| Editor | `docs/adr/0006-dual-quality-gate.md`, `docs/runbooks/gx-gate-failure.md` |

Recording setup: 1080p or 1440p, terminal at ≥ 16 pt, notifications off,
`data/raw/2026-11-01/manifest.json` pre-generated so no waiting is recorded.

## Scenes

| Time | On screen | Voiceover |
|---|---|---|
| 0:00–0:20 | Title card: **Ledgerline — batch path**. Then `data/raw/2026-11-01/` file list. | "This is the authoritative path of a small commerce platform. One deterministic generator produces a day of orders, payments, and returns; this repo loads it into BigQuery, models it with dbt, and proves the numbers." |
| 0:20–0:40 | `README.md` architecture fence; scroll the four stages. | "Generation, a Great Expectations gate, BigQuery sandbox, then dbt staging to marts. Every stage is a command, and every claim has a committed artifact." |
| 0:40–1:05 | `make gen` (already run), then `uv run python -m json.tool data/raw/2026-11-01/manifest.json \| head -30`. | "Same seed, same bytes: 800 orders, 2,050 line items, 2,870 events, and a manifest with sha256 per file. The event IDs are UUIDv5, so a replay is provably identical." |
| 1:05–1:30 | `make validate`, clean day. Show the last PASS lines. | "Gate one checks the contract before anything is loaded: column sets, key uniqueness, accepted values, non-negative money, and volume against ground truth." |
| 1:30–1:55 | `uv run eventforge batch --seed 42 --start 2026-11-05 --days 1 --out data/raw --incident truncated --truncate-pct 0.6`, then `ingest.validate` on that day. Show the four failing volume rows. | "Now the same pipeline with a truncated extract. The manifest agrees with the files, so schema checks pass — only the comparison with ground truth catches it. No rows are loaded." |
| 1:55–2:10 | `docs/runbooks/gx-gate-failure.md`; scroll the alert payload. | "The alert names the runbook, and the runbook says how to confirm the source, rerun the day, and prove recovery. That path is tested locally with Slack unset." |
| 2:10–2:35 | `make dbt-build` output, then `dbt docs serve` lineage graph. | "Gate two runs after the transform: 57 tests on grains, relationships, financial invariants, freshness, and a volume band. A fan-out drill in the repo shows the grain test stopping publication." |
| 2:35–2:52 | `bench/report.md`; highlight 0.72 GiB billed, 35 s, $0.00441, monthly $0.30. | "Cost is measured from BigQuery job metadata, not estimated. A full build bills under a gigabyte; the monthly projection is thirty cents, and the sandbox uses about two percent of its free query allowance." |
| 2:52–3:00 | `docs/adr/` list, then title card with repo URL. | "Seven ADRs record the tradeoffs, including why this path is authoritative and the streaming path is provisional. The next step is the seam: reconciling both against the same seed." |

## Numbers to say correctly

- 500 customers, 200 products, 800 orders, 2,050 order items, 773 payments.
- 2,870 events; the manifest's sha256 for `events.jsonl` starts `8a5041ed…`,
  and the event-ID hash used by the stream reconciliation is
  `1a63685fd48c1932…`.
- 72 dbt nodes: 13 models and 57 tests.
- One build: 0.72 GiB billed, ~35 s, $0.00441; monthly projection $0.30.
- Truncated incident: 480/800 orders, 1,189/1,965 items, 462/774 payments,
  14/27 returns; four failed expectations.

## If you only have 90 seconds

Cut scenes 1:55–2:10 and 2:10–2:35 to one sentence each, keep the failed gate
and the cost table. Never cut the clean determinism claim or the failure proof.
