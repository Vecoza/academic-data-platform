ARG AIRFLOW_VERSION=3.3.2
ARG PYTHON_VERSION=3.11

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
ARG CONSTRAINTS_URL=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt

# Airflow's own environment only changes through the official constraints file.
RUN pip install --no-cache-dir \
        "apache-airflow==${AIRFLOW_VERSION}" \
        apache-airflow-providers-standard \
        --constraint "${CONSTRAINTS_URL}"

# The project and dbt get their own virtualenv, so their pins never meet Airflow's.
ENV PROJECT_VENV=/opt/academic/venv
COPY --chown=airflow:0 pyproject.toml README.md /opt/academic/project/
COPY --chown=airflow:0 src /opt/academic/project/src
COPY --chown=airflow:0 generator /opt/academic/project/generator
COPY --chown=airflow:0 ingestion /opt/academic/project/ingestion
COPY --chown=airflow:0 quality /opt/academic/project/quality
COPY --chown=airflow:0 dbt /opt/academic/dbt

RUN python -m venv "${PROJECT_VENV}" \
    && PIP_USER=false "${PROJECT_VENV}/bin/pip" install --no-cache-dir /opt/academic/project \
    && rm -rf /opt/academic/project/build
