"""Airflow wrapper for the Ledgerline batch pipeline.

Airflow is not installed on the zero-cost path (it needs Docker). This DAG is
the deployment artifact for an environment that has it: Airflow owns
scheduling, retries, and observability; `orchestration.run_pipeline` owns the
stage order, gates, and Slack alerts.

The `generate_demo_batch` task exists only because this platform uses a
synthetic source. In a real deployment, replace it with a sensor on the
upstream drop (or keep it for demos).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "{{ var.value.gcp_project }}"
DAY_DIR = "data/raw/{{ ds }}"

default_args = {
    "owner": "younessb2ta",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id="ledgerline_batch",
    description="GX gate -> BigQuery load -> dbt build, with Slack alerts",
    schedule="0 6 * * *",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["ledgerline", "batch"],
) as dag:
    generate_demo_batch = BashOperator(
        task_id="generate_demo_batch",
        bash_command=(
            'cd "$LEDGERLINE_HOME" && '
            "uv run eventforge batch --seed 42 --start {{ ds }} --days 1 --out data/raw"
        ),
    )

    run_pipeline = BashOperator(
        task_id="run_pipeline",
        bash_command=(
            'cd "$LEDGERLINE_HOME" && '
            "uv run python -m orchestration.run_pipeline "
            f"--day-dir {DAY_DIR} --project {PROJECT}"
        ),
        env={"SLACK_WEBHOOK_URL": "{{ var.value.slack_webhook_url }}"},
    )

    generate_demo_batch >> run_pipeline
