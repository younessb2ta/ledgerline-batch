"""The quality gate must fail for each incident it claims to catch.

These are end-to-end: they generate a small day, run the real Great
Expectations suite over the CSVs, and assert the exit code. A gate that only
passes on clean data is a report, not a gate.
"""

from __future__ import annotations

from datetime import date

import pytest
from ingest.validate import main

from eventforge import GeneratorConfig, generate_day
from eventforge.writers import write_day

DAY = date(2026, 11, 3)


@pytest.fixture(scope="module")
def day_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("gate")

    def build(name: str, *, incident: str = "none", backdate: int = 0):
        cfg = GeneratorConfig(
            seed=7,
            start_date=DAY,
            orders_per_day=200,
            n_customers=40,
            n_products=25,
            backdate_days=backdate,
        )
        data = generate_day(cfg, DAY)
        return write_day(data, root / name, incident=incident, truncate_pct=0.4)

    return {
        "clean": build("clean"),
        "duplicate_pk": build("duplicate_pk", incident="duplicate_pk"),
        "truncated": build("truncated", incident="truncated"),
        "schema_drift": build("schema_drift", incident="schema_drift"),
        "stale": build("stale", incident="stale", backdate=3),
    }


def _run(day_dir, capsys) -> tuple[int, str]:
    code = main(["--day-dir", str(day_dir), "--project", "test-project", "--no-write"])
    return code, capsys.readouterr().err


def test_clean_batch_passes(day_dirs, capsys):
    code, _ = _run(day_dirs["clean"], capsys)
    assert code == 0


@pytest.mark.parametrize(
    ("incident", "expected_fragment"),
    [
        ("duplicate_pk", "expect_column_values_to_be_unique"),
        ("truncated", "volume.row_count_vs_baseline"),
        ("schema_drift", "column.exists"),
        ("stale", "freshness.order_ts_within_batch_day"),
    ],
)
def test_incidents_fail_the_gate(day_dirs, capsys, incident, expected_fragment):
    code, stderr = _run(day_dirs[incident], capsys)
    assert code == 1
    assert expected_fragment in stderr
