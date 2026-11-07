from __future__ import annotations

import uuid
from datetime import date

# Fixed namespace: IDs are stable across machines, runs, and Python versions.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://ledgerline.dev/eventforge")


def event_id(seed: int, day: date, sequence: int) -> str:
    """Deterministic UUIDv5 for an event.

    Same (seed, day, sequence) always produces the same ID, which is what makes
    duplicate detection and replay reconciliation meaningful.
    """
    return str(uuid.uuid5(_NAMESPACE, f"{seed}:{day.isoformat()}:{sequence}"))
