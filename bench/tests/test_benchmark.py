from __future__ import annotations

from bench import benchmark


def test_minimum_billed_bytes_applies_floor():
    assert benchmark.billed_bytes(1_000) == benchmark.MIN_BILLED_BYTES
    assert benchmark.billed_bytes(50 * benchmark.MIB) == 50 * benchmark.MIB


def test_cost_uses_tib_rate():
    assert benchmark.cost_usd(benchmark.TIB) == benchmark.USD_PER_TIB
    assert benchmark.cost_usd(benchmark.MIN_BILLED_BYTES) < 0.001


def test_monthly_projection_multiplies_runs_and_days():
    per_run = benchmark.TIB  # $6.25
    assert (
        benchmark.monthly_cost_usd(per_run, runs_per_day=1, days=30) == 30 * benchmark.USD_PER_TIB
    )
    assert (
        benchmark.monthly_cost_usd(per_run, runs_per_day=2, days=10) == 20 * benchmark.USD_PER_TIB
    )


def test_read_run_results_sums_adapter_responses(tmp_path):
    import json

    payload = {
        "metadata": {"generated_at": "2026-11-08T00:00:00Z"},
        "elapsed_time": 1.5,
        "results": [
            {
                "unique_id": "model.pkg.fct_orders",
                "status": "success",
                "adapter_response": {"bytes_processed": 100, "bytes_billed": 200},
            },
            {
                "unique_id": "test.pkg.unique_x",
                "status": "pass",
                "adapter_response": {"bytes_processed": 300, "bytes_billed": 400},
            },
        ],
    }
    path = tmp_path / "run_results.json"
    path.write_text(json.dumps(payload))
    run = benchmark.read_run_results(path)
    assert run.nodes == 2
    assert run.models == 1
    assert run.tests == 1
    assert run.bytes_processed == 400
    assert run.bytes_billed == 600
