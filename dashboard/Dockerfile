FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src src
COPY dashboard dashboard
COPY .streamlit .streamlit

# The dashboard extra adds Streamlit to the core; the pipeline's dbt, Faker and Alembic stay out.
RUN pip install ".[dashboard]" \
    && useradd --create-home dashboard

USER dashboard
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
