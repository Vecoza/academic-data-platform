#!/usr/bin/env bash
# Prepares the platform on start: applies migrations and, on an empty operational database,
# generates a history, loads it into the warehouse and builds the models.
set -euo pipefail

PROJECT=/opt/academic
PYTHON="$PROJECT/venv/bin/python"
DBT_ARGS=(--project-dir "$PROJECT/dbt" --profiles-dir "$PROJECT/dbt")
export DBT_TARGET_PATH=/tmp/dbt/target DBT_LOG_PATH=/tmp/dbt/logs

"$PROJECT/venv/bin/alembic" -c "$PROJECT/project/alembic.ini" upgrade head

students=$("$PYTHON" -c '
from sqlalchemy import text
from academic_platform.db import get_engine
with get_engine().connect() as connection:
    print(connection.execute(text("SELECT count(*) FROM students")).scalar_one())
')

if [ "$students" -gt 0 ]; then
    echo "The operational database already holds $students students; nothing to generate."
    exit 0
fi

"$PYTHON" -m generator --mode full --students "${PLATFORM_STUDENTS:-15000}"
"$PYTHON" -m ingestion --mode full
"$PROJECT/venv/bin/dbt" build "${DBT_ARGS[@]}"
