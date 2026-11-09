from __future__ import annotations

import json
import random
import time
from collections.abc import Iterable, Iterator
from dataclasses import replace
from datetime import datetime, timedelta

from .generator import GeneratorConfig, generate_events
from .model import Event, iso_utc


def _shift_back(ts: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return iso_utc(parsed - timedelta(seconds=seconds))


def ordered_events(cfg: GeneratorConfig, *, shuffle: bool = True, sort: bool = False) -> list:
    """Return the events in the order they should be produced.

    ``sort`` wins over ``shuffle``. A stable timestamp order is what a replay
    needs: the generator appends returns after the orders they belong to, so
    refunds can carry timestamps days earlier than the preceding record. Fed to
    a watermark assigner that looks like real lateness, which is a lie.
    """
    events = list(generate_events(cfg))
    if sort:
        events.sort(key=lambda event: (event.event_ts, event.event_id))
    elif shuffle:
        random.Random(cfg.seed).shuffle(events)
    return events


def apply_lateness(
    events: Iterable[Event],
    *,
    late_pct: float,
    late_seconds: int,
    seed: int,
) -> Iterator[Event]:
    """Re-stamp a deterministic subset of events behind the newest event.

    ``events`` must already be in the order they will be produced. A selected
    record is stamped ``late_seconds`` behind the newest timestamp produced so
    far, not behind its own timestamp. That distinction matters: the stream is
    sparse, so an event that is 300 s older than *itself* can still be newer
    than the previous record and therefore not late at all. Anchoring to the
    newest event makes every selected record unambiguously late for a bounded
    out-of-orderness watermark, so the classification does not depend on how
    dense the surrounding events happen to be.

    Membership and amounts are unchanged: only ``event_ts`` moves. The
    generator's ground-truth totals therefore still apply.
    """
    rng = random.Random(f"{seed}:late")
    newest: str | None = None
    for event in events:
        selected = late_pct > 0 and rng.random() < late_pct
        # The first event has no predecessor to be behind; it stays on time.
        if selected and newest is not None:
            yield replace(event, event_ts=_shift_back(newest, late_seconds))
            continue
        newest = event.event_ts if newest is None else max(newest, event.event_ts)
        yield event


def produce(
    cfg: GeneratorConfig,
    *,
    bootstrap: str,
    topic: str,
    rate: float = 50.0,
    duration: float | None = None,
    late_pct: float = 0.0,
    late_seconds: int = 300,
    shuffle: bool = True,
    sort: bool = False,
) -> int:
    """Produce events to Kafka. Returns the number of messages sent."""
    try:
        from confluent_kafka import Producer
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit("Kafka mode needs optional dependencies: uv sync --extra kafka") from exc

    producer = Producer(
        {
            "bootstrap.servers": bootstrap,
            "enable.idempotence": True,
            "acks": "all",
        }
    )

    events = apply_lateness(
        ordered_events(cfg, shuffle=shuffle, sort=sort),
        late_pct=late_pct,
        late_seconds=late_seconds,
        seed=cfg.seed,
    )

    interval = 1.0 / rate if rate > 0 else 0.0
    started = time.monotonic()
    sent = 0

    for event in events:
        if duration is not None and time.monotonic() - started >= duration:
            break

        producer.produce(
            topic,
            key=event.customer_id.encode("utf-8"),
            value=json.dumps(event.to_dict(), separators=(",", ":")).encode("utf-8"),
        )
        sent += 1
        producer.poll(0)
        if interval:
            time.sleep(interval)

    producer.flush(10)
    return sent
