"""Tasks shared by the academic DAGs: simulate, ingest, transform, check.

Each task runs a project command from the project's own virtualenv in the image, so the
project and dbt never share dependencies with Airflow. Database settings come from the Airflow
connections `university_db` and `warehouse_db`, which are defined by environment variables.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from airflow.providers.standard.operators.bash import BashOperator

logger = logging.getLogger(__name__)

PROJECT_PYTHON = "/opt/academic/venv/bin/python"
DBT = "/opt/academic/venv/bin/dbt"
DBT_PROJECT = "--project-dir /opt/academic/dbt --profiles-dir /opt/academic/dbt"
PIPELINE_POOL = "academic_pipeline"

DATABASE_ENV = {
    "POSTGRES_HOST": "{{ conn.university_db.host }}",
    "POSTGRES_PORT": "{{ conn.university_db.port }}",
    "POSTGRES_USER": "{{ conn.university_db.login }}",
    "POSTGRES_PASSWORD": "{{ conn.university_db.password }}",
    "POSTGRES_DB": "{{ conn.university_db.schema }}",
    "WAREHOUSE_DB": "{{ conn.warehouse_db.schema }}",
    "DBT_TARGET_PATH": "/tmp/dbt/target",
    "DBT_LOG_PATH": "/tmp/dbt/logs",
}


def log_failure(context: dict) -> None:
    """Log one readable summary line per failed task attempt."""
    task_instance = context["task_instance"]
    logger.error(
        "Task failed: dag=%s task=%s run=%s attempt=%s of %s error=%s",
        task_instance.dag_id,
        task_instance.task_id,
        context.get("run_id"),
        task_instance.try_number,
        task_instance.max_tries + 1,
        context.get("exception"),
    )


DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "pool": PIPELINE_POOL,
    "on_failure_callback": log_failure,
}


def project_task(task_id: str, command: str, timeout: timedelta) -> BashOperator:
    return BashOperator(
        task_id=task_id,
        bash_command=command,
        env=DATABASE_ENV,
        append_env=True,
        execution_timeout=timeout,
    )


def ingest_transform_check() -> tuple[BashOperator, BashOperator, BashOperator]:
    """Ingest, dbt build and quality checks, chained in that order."""
    ingest = project_task(
        "ingest",
        f"{PROJECT_PYTHON} -m ingestion --mode incremental",
        timedelta(minutes=30),
    )
    dbt_build = project_task("dbt_build", f"{DBT} build {DBT_PROJECT}", timedelta(minutes=60))
    quality_checks = project_task(
        "quality_checks",
        f"{PROJECT_PYTHON} -m quality && {DBT} source freshness {DBT_PROJECT}",
        timedelta(minutes=15),
    )
    ingest >> dbt_build >> quality_checks
    return ingest, dbt_build, quality_checks
