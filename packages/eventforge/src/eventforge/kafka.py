from __future__ import annotations

import json
import random
import time
from dataclasses import replace
from datetime import datetime, timedelta

from .generator import GeneratorConfig, generate_events
from .model import iso_utc


def _shift_back(ts: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return iso_utc(parsed - timedelta(seconds=seconds))


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

    events = list(generate_events(cfg))
    if shuffle:
        random.Random(cfg.seed).shuffle(events)

    late_rng = random.Random(f"{cfg.seed}:late")
    interval = 1.0 / rate if rate > 0 else 0.0
    started = time.monotonic()
    sent = 0

    for event in events:
        if duration is not None and time.monotonic() - started >= duration:
            break

        if late_pct and late_rng.random() < late_pct:
            event = replace(event, event_ts=_shift_back(event.event_ts, late_seconds))

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
