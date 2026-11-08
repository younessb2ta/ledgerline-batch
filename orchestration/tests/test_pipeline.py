from __future__ import annotations

import json
from pathlib import Path

from orchestration import run_pipeline


def test_classify_routes_operational_tests_to_their_runbook():
    assert run_pipeline.classify_dbt_failure("... assert_pipeline_freshness ...") == "freshness"
    assert run_pipeline.classify_dbt_failure("... assert_daily_volume_within_band ...") == "volume"
    assert run_pipeline.classify_dbt_failure("unique_fct_orders_order_id FAIL") == "dbt"


def test_tail_keeps_the_last_lines():
    output = "\n".join(f"line {i}" for i in range(100))
    tail = run_pipeline._tail(output, lines=3)
    assert tail.splitlines() == ["line 97", "line 98", "line 99"]


def test_batch_id_comes_from_the_manifest(tmp_path: Path):
    day = tmp_path / "2026-11-01"
    day.mkdir()
    (day / "manifest.json").write_text(json.dumps({"batch_id": "20261101-42"}))
    assert run_pipeline._batch_id(day) == "20261101-42"
