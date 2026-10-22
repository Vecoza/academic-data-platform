# Orchestration design

Apache Airflow 3.3 runs the pipeline on a schedule: simulate the next day of university life, load it into the warehouse, rebuild the models and check the result. Airflow runs in Docker Compose next to the existing PostgreSQL server.

## Components

| Service | Role |
|---|---|
| `airflow-database` | One-off: creates the `airflow` metadata database on the existing PostgreSQL server if it is missing |
| `airflow-init` | One-off: migrates the metadata database and creates the `academic_pipeline` pool |
| `airflow-apiserver` | REST API, web UI and the execution API that running tasks report to (port 8080) |
| `airflow-scheduler` | Schedules DAG runs and, with the LocalExecutor, runs the tasks itself |
| `airflow-dag-processor` | Parses the DAG files in `orchestration/dags` |

All Airflow services sit behind the Compose profile `airflow`:
- `make up` still starts only PostgreSQL.
- `make airflow-up` builds the image and starts Airflow, waiting until every service is healthy.
- `make airflow-down` removes the Airflow containers and leaves PostgreSQL running.

**Metadata database.** Airflow's metadata lives in its own `airflow` database on the same server, separate from `university` and `warehouse`. An init script under `docker/init` would only run on an empty data volume, so a one-off container creates the database idempotently instead.

## Why the LocalExecutor

The pipeline is one sequential chain of four tasks, and only one chain may run at a time (see below). The LocalExecutor runs tasks as processes of the scheduler, which is all this workload needs.

The CeleryExecutor would add a message broker (Redis), a result backend and worker containers. That is three more moving parts to operate, for parallelism the pipeline cannot use. If the platform later needed tasks on several machines, the DAGs would not have to change, only the executor configuration.

## The image

The image is built from the official `apache/airflow:3.3.2-python3.11` image and keeps two Python environments apart:

| Environment | Contents | How it is installed |
|---|---|---|
| Airflow's own (`~/.local` of the `airflow` user) | Airflow and its providers | `pip install ... --constraint` with the official constraints file for Airflow 3.3.2 and Python 3.11 |
| `/opt/academic/venv` | The project packages (`generator`, `ingestion`, `quality`, `academic_platform`) and dbt | A separate virtualenv, installed from `pyproject.toml` |

**Why the separate virtualenv.** Airflow pins hundreds of packages through its constraints file, and dbt pins its own dependencies. Installed together, one side would have to give way, or the install would fail. In this image they already disagree: Airflow's environment uses SQLAlchemy 2.0, the project's uses SQLAlchemy 2.1. Keeping them apart means:
- Airflow is upgraded only through the constraints file;
- the project and dbt can be upgraded without touching Airflow;
- tasks call the project's commands from the virtualenv (`/opt/academic/venv/bin/python -m ingestion`), exactly as they are run by hand.

The build context is filtered by an allowlist in `.dockerignore`, so only the files the image needs are sent to Docker.

## Configuration

Everything is configured through environment variables set in `docker-compose.yml` from `.env`. There is no `airflow.cfg` and nothing is set in the UI:
- **Airflow settings** use `AIRFLOW__SECTION__KEY` variables: executor, metadata database, execution API URL, JWT secret.
- **Connections** use `AIRFLOW_CONN_UNIVERSITY_DB` and `AIRFLOW_CONN_WAREHOUSE_DB`, as connection URIs.

Tasks receive the database settings from those connections through templates (`{{ conn.university_db.host }}`), passed to the project as the same environment variables it reads everywhere else.

**Local login.** The web UI uses Airflow's simple auth manager with every user treated as an administrator, so no login is needed locally. This is a local development setting and would be replaced by a real auth manager in any shared deployment.

## DAGs

### `academic_daily`

```
generate_daily  ──▶  ingest  ──▶  dbt_build  ──▶  quality_checks
```

| Task | Command | Timeout |
|---|---|---|
| `generate_daily` | `python -m generator --mode daily --days {{ params.days }}` | 30 min |
| `ingest` | `python -m ingestion --mode incremental` | 30 min |
| `dbt_build` | `dbt build` | 60 min |
| `quality_checks` | `python -m quality` and `dbt source freshness` | 15 min |

**Schedule and parameters.**
- The DAG runs `@daily`, without catch-up.
- The parameter `days` (1–31, default 1) simulates several days in one run, for example to fast-forward to an exam period.

**Failure handling.**
- **Retries:** every task retries twice, with a delay that starts at 2 minutes and grows exponentially.
- **Callback:** a failure callback logs one summary line with the DAG, task, run, attempt and error.
- **Safe to retry:** a retried task is safe to run again. The generator does not repeat a day it already simulated, ingestion is idempotent, and dbt and the quality checks only read and rebuild.

### `academic_backfill`

The same chain, but manual only (no schedule). Its first task, `generate_until`, runs `python -m generator --mode daily --date {{ params.target_date }}`: it simulates every day up to the target date, then ingestion, dbt and the quality checks run once.

### Why only one active run

The simulation clock in `sim.clock` is sequential: each simulated day starts where the previous one ended. Two runs simulating at the same time would race for the same next day. The generator's row lock would serialize them, but the downstream tasks of both runs would then interleave. Each DAG therefore has `max_active_runs=1`.

Between the two DAGs, every task uses the `academic_pipeline` pool with a single slot. A backfill and a daily run can be queued at the same time, but only one task of either runs at any moment.

## How to backfill

1. Find the current simulated date: `SELECT simulated_date FROM sim.clock` in the `university` database.
2. Trigger `academic_backfill` from the UI or the CLI with the last date to reach:
   `airflow dags trigger academic_backfill --conf '{"target_date": "2026-12-31"}'`
3. The generator simulates each missing day in its own transaction. Ingestion then loads all changes at once, and dbt and the quality checks run once at the end.

**Repeating a backfill is safe.** A target date that has already been simulated makes the generator log "already simulated" and do nothing, and the rest of the chain finds nothing new.

Airflow's own `airflow backfill` command is not used. It would create one run per scheduled interval and replay `academic_daily` for past logical dates, but the simulation clock, not the logical date, decides which day is simulated next. A single run up to a target date matches how the clock works.

## Testing

The DAG tests in `orchestration/tests` check that:
- both DAGs import without errors, which includes Airflow's cycle check;
- tasks form exactly the expected chain;
- `max_active_runs` is 1;
- every task has retries, a timeout, the failure callback and the shared pool;
- the schedules and parameters are as described.

They need Airflow, and Airflow must not share an environment with the project, so they run separately:
- **In CI:** a dedicated job installs only Airflow 3.3.2 and pytest with the official constraints file. The main test job is unchanged.
- **Locally:** `make test-dags` runs them inside the Airflow image. A local install on an Intel Mac is not possible with these constraints: one pinned dependency (`libcst` 1.9.0) has no macOS wheel for that platform and would need a Rust toolchain to build.

## Measured runs

Locally, on the default history (15,000 students), starting at the beginning of the 2026/27 academic year. All runs succeeded and ran strictly one after another:

| Run | Simulated day | Duration | generate | ingest | dbt_build | quality |
|---|---|---|---|---|---|---|
| scheduled | 1 Oct (new cohort) | 105 s | | | | |
| manual 1 | 2 Oct | 97 s | 7 s | 22 s | 58 s | 7 s |
| manual 2 | 3 Oct | 90 s | 9 s | 8 s | 63 s | 7 s |
| manual 3 | 4 Oct | 169 s | 8 s | 8 s | 126 s | 23 s |
| backfill to 4 Oct | none, already simulated | 131 s | | | | |

`dbt_build` dominates every run. The spread between runs comes from the machine, not the data. The backfill run confirmed that a repeated target date is skipped by the generator and leaves the clock where it was.

**Log masking.** Airflow masks connection passwords wherever they appear in task logs. The first local password was the word "academic", so DAG names appeared as `***_daily`. The default password is now `adp_local_pw_2026`, a value that cannot occur inside a name, and task logs show `academic_daily` in full.

The image is 739 MB.
