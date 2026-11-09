from __future__ import annotations

import argparse
from datetime import date, timedelta

from .generator import GeneratorConfig, generate_day
from .writers import write_day

INCIDENTS = ("none", "truncated", "schema_drift", "duplicate_pk", "stale")


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date (expected YYYY-MM-DD): {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eventforge",
        description="Deterministic e-commerce data generator for the Ledgerline platform.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    batch = sub.add_parser("batch", help="write deterministic daily CSV batches")
    batch.add_argument("--seed", type=int, default=42)
    batch.add_argument("--start", type=_iso_date, default=date(2026, 11, 1))
    batch.add_argument("--days", type=int, default=1)
    batch.add_argument("--customers", type=int, default=500)
    batch.add_argument("--products", type=int, default=200)
    batch.add_argument("--orders-per-day", type=int, default=800)
    batch.add_argument("--out", default="data/raw")
    batch.add_argument("--incident", choices=INCIDENTS, default="none")
    batch.add_argument(
        "--truncate-pct",
        type=float,
        default=0.6,
        help="fraction of orders dropped by the truncated incident (0.6 = 60%% lost)",
    )
    batch.add_argument(
        "--backdate-days",
        type=int,
        default=3,
        help="how far to shift event time backwards for the stale incident",
    )

    kafka = sub.add_parser("kafka", help="stream generated events to a Kafka topic")
    kafka.add_argument("--seed", type=int, default=42)
    kafka.add_argument("--start", type=_iso_date, default=date(2026, 11, 1))
    kafka.add_argument("--days", type=int, default=1)
    kafka.add_argument("--customers", type=int, default=500)
    kafka.add_argument("--products", type=int, default=200)
    kafka.add_argument("--orders-per-day", type=int, default=800)
    kafka.add_argument("--bootstrap", default="localhost:9092")
    kafka.add_argument("--topic", default="ledger.events")
    kafka.add_argument("--rate", type=float, default=50.0, help="events per second")
    kafka.add_argument("--duration", type=float, default=None, help="seconds to produce for")
    kafka.add_argument("--late-pct", type=float, default=0.0)
    kafka.add_argument("--late-seconds", type=int, default=300)
    kafka.add_argument("--no-shuffle", action="store_true")
    kafka.add_argument(
        "--sort",
        action="store_true",
        help="produce in event_ts order (deterministic replay; implies --no-shuffle)",
    )

    return parser


def _run_batch(args: argparse.Namespace) -> int:
    backdate_days = args.backdate_days if args.incident == "stale" else 0
    cfg = GeneratorConfig(
        seed=args.seed,
        start_date=args.start,
        days=args.days,
        n_customers=args.customers,
        n_products=args.products,
        orders_per_day=args.orders_per_day,
        backdate_days=backdate_days,
    )

    header = f"{'day':<12}{'orders':>8}{'items':>8}{'events':>8}{'revenue_cents':>16}  output"
    print(header)
    print("-" * len(header))

    for offset in range(cfg.days):
        day = cfg.start_date + timedelta(days=offset)
        data = generate_day(cfg, day)
        out = write_day(
            data,
            args.out,
            incident=args.incident,
            truncate_pct=args.truncate_pct,
        )
        truth = data.ground_truth
        print(
            f"{day.isoformat():<12}"
            f"{truth['orders']:>8}"
            f"{truth['order_items']:>8}"
            f"{truth['total_events']:>8}"
            f"{truth['total_revenue_cents']:>16}"
            f"  {out}"
        )

    if args.incident != "none":
        print(f"\nincident injected: {args.incident}")
        if args.incident == "truncated":
            print(
                f"dropped ~{args.truncate_pct:.0%} of orders (whole orders, referentially intact)"
            )
        if args.incident == "stale":
            print(f"event time shifted back by {args.backdate_days} days")
        print("counts above are ground truth; manifest.json reflects what was actually written")
    return 0


def _run_kafka(args: argparse.Namespace) -> int:
    from .kafka import produce

    cfg = GeneratorConfig(
        seed=args.seed,
        start_date=args.start,
        days=args.days,
        n_customers=args.customers,
        n_products=args.products,
        orders_per_day=args.orders_per_day,
    )
    sent = produce(
        cfg,
        bootstrap=args.bootstrap,
        topic=args.topic,
        rate=args.rate,
        duration=args.duration,
        late_pct=args.late_pct,
        late_seconds=args.late_seconds,
        shuffle=not args.no_shuffle,
        sort=args.sort,
    )
    print(f"sent {sent} events to {args.bootstrap}/{args.topic}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "batch":
        return _run_batch(args)
    return _run_kafka(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
