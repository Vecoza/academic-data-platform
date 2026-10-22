"""DAG integrity tests. They need Airflow and run in their own environment and CI job."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("airflow")

from airflow.models import DagBag  # noqa: E402

DAG_FOLDER = Path(__file__).resolve().parent.parent / "dags"
DAILY_ORDER = ["generate_daily", "ingest", "dbt_build", "quality_checks"]
BACKFILL_ORDER = ["generate_until", "ingest", "dbt_build", "quality_checks"]


@pytest.fixture(scope="module")
def dag_bag() -> DagBag:
    """Load the DAG folder the way Airflow does: with the folder itself on sys.path."""
    sys.path.insert(0, str(DAG_FOLDER))
    return DagBag(dag_folder=str(DAG_FOLDER))


def task_chain(dag) -> list[str]:
    """Task ids from the single root to the single leaf, failing if the DAG is not a chain."""
    roots = [task for task in dag.tasks if not task.upstream_task_ids]
    assert len(roots) == 1
    chain, task = [], roots[0]
    while True:
        chain.append(task.task_id)
        downstream = list(task.downstream_list)
        if not downstream:
            return chain
        assert len(downstream) == 1
        task = downstream[0]


def test_dags_import_without_errors(dag_bag: DagBag) -> None:
    assert dag_bag.import_errors == {}
    assert set(dag_bag.dag_ids) == {"academic_daily", "academic_backfill"}


@pytest.mark.parametrize(
    ("dag_id", "order"),
    [("academic_daily", DAILY_ORDER), ("academic_backfill", BACKFILL_ORDER)],
)
def test_tasks_run_in_pipeline_order(dag_bag: DagBag, dag_id: str, order: list[str]) -> None:
    dag = dag_bag.dags[dag_id]

    assert task_chain(dag) == order
    assert len(dag.tasks) == len(order)


@pytest.mark.parametrize("dag_id", ["academic_daily", "academic_backfill"])
def test_only_one_run_can_be_active(dag_bag: DagBag, dag_id: str) -> None:
    assert dag_bag.dags[dag_id].max_active_runs == 1


@pytest.mark.parametrize("dag_id", ["academic_daily", "academic_backfill"])
def test_every_task_retries_and_has_a_timeout(dag_bag: DagBag, dag_id: str) -> None:
    for task in dag_bag.dags[dag_id].tasks:
        assert task.retries >= 1
        assert task.retry_delay.total_seconds() > 0
        assert task.execution_timeout is not None
        assert task.on_failure_callback
        assert task.pool == "academic_pipeline"


def test_daily_dag_is_scheduled_daily_without_catchup(dag_bag: DagBag) -> None:
    dag = dag_bag.dags["academic_daily"]

    assert dag.catchup is False
    assert dag.params["days"] == 1


def test_backfill_dag_is_manual_only(dag_bag: DagBag) -> None:
    dag = dag_bag.dags["academic_backfill"]

    assert dag.schedule is None
    assert "target_date" in dag.params


def test_simulated_days_are_passed_to_the_generator(dag_bag: DagBag) -> None:
    command = dag_bag.dags["academic_daily"].get_task("generate_daily").bash_command

    assert command.endswith("--mode daily --days {{ params.days }}")
