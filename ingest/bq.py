"""Thin BigQuery helper: create tables and run load jobs (no DML — sandbox compatible).

The BigQuery sandbox does not allow DML, so every write is a load job:
- raw data: CSV load from a local file
- audit / quality results: newline-delimited JSON load

This is a constraint, not a workaround: load jobs are idempotent when paired with
an audit check, and they keep the write path identical to a real GCS-batch setup.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from .schemas import Column, TableSpec


def _schema(columns: tuple[Column, ...]) -> list[bigquery.SchemaField]:
    return [bigquery.SchemaField(c.name, c.type, mode=c.mode) for c in columns]


class Warehouse:
    def __init__(self, project: str, location: str = "US") -> None:
        self.project = project
        self.location = location
        self.client = bigquery.Client(project=project, location=location)

    def table_id(self, dataset: str, table: str) -> str:
        return f"{self.project}.{dataset}.{table}"

    def ensure_table(self, dataset: str, spec: TableSpec) -> bool:
        """Create the table if missing. Returns True when it was created."""
        table_id = self.table_id(dataset, spec.name)
        try:
            self.client.get_table(table_id)
            return False
        except NotFound:
            pass

        table = bigquery.Table(table_id, schema=_schema(spec.columns))
        if spec.partition_field:
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field=spec.partition_field,
            )
        if spec.clustering:
            table.clustering_fields = list(spec.clustering)
        self.client.create_table(table)
        return True

    def load_csv(self, dataset: str, spec: TableSpec, path: Path) -> int:
        if spec.source is None:
            raise ValueError(f"{spec.name} has no CSV source")
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=_schema(spec.columns),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            max_bad_records=0,
            allow_jagged_rows=False,
        )
        with path.open("rb") as handle:
            job = self.client.load_table_from_file(
                handle, self.table_id(dataset, spec.name), job_config=config
            )
        job.result()
        return int(job.output_rows or 0)

    def append_rows(self, dataset: str, spec: TableSpec, rows: list[dict]) -> int:
        if not rows:
            return 0

        with tempfile.NamedTemporaryFile(
            "w", suffix=".ndjson", delete=False, encoding="utf-8"
        ) as handle:
            for row in rows:
                handle.write(json.dumps(row, default=str) + "\n")
            path = Path(handle.name)

        try:
            config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                schema=_schema(spec.columns),
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            )
            with path.open("rb") as stream:
                job = self.client.load_table_from_file(
                    stream, self.table_id(dataset, spec.name), job_config=config
                )
            job.result()
            return int(job.output_rows or 0)
        finally:
            path.unlink(missing_ok=True)

    def query(self, sql: str, params: dict | None = None) -> list[bigquery.Row]:
        config = bigquery.QueryJobConfig()
        if params:
            config.query_parameters = [
                bigquery.ScalarQueryParameter(name, _param_type(value), value)
                for name, value in params.items()
            ]
        return list(self.client.query(sql, job_config=config).result())


def _param_type(value: object) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    return "STRING"
