"""Manual catch-up: simulate every day up to a target date, then run the warehouse chain once.

Days that were already simulated are skipped by the generator, so the run is safe to repeat.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG, Param
from pipeline_tasks import DEFAULT_ARGS, PROJECT_PYTHON, ingest_transform_check, project_task

with DAG(
    dag_id="academic_backfill",
    description="Simulate up to a target date, then ingest, build and check once",
    schedule=None,
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={
        "target_date": Param(
            "2026-12-31",
            type="string",
            format="date",
            description="Last simulated date to reach (YYYY-MM-DD)",
        ),
    },
    tags=["academic"],
) as dag:
    generate_until = project_task(
        "generate_until",
        f"{PROJECT_PYTHON} -m generator --mode daily --date {{{{ params.target_date }}}}",
        timedelta(hours=2),
    )
    ingest, _, _ = ingest_transform_check()
    generate_until >> ingest
