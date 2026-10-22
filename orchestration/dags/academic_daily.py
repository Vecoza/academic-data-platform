"""Daily pipeline: simulate the next day(s), ingest them, rebuild the warehouse, check quality.

The simulation clock moves one day per simulated day and must never be advanced by two runs at
once, so only one run of this DAG may be active.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG, Param
from pipeline_tasks import DEFAULT_ARGS, PROJECT_PYTHON, ingest_transform_check, project_task

with DAG(
    dag_id="academic_daily",
    description="Simulate university activity, load it into the warehouse and test it",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={
        "days": Param(1, type="integer", minimum=1, maximum=31, description="Simulated days"),
    },
    tags=["academic"],
) as dag:
    generate_daily = project_task(
        "generate_daily",
        f"{PROJECT_PYTHON} -m generator --mode daily --days {{{{ params.days }}}}",
        timedelta(minutes=30),
    )
    ingest, _, _ = ingest_transform_check()
    generate_daily >> ingest
