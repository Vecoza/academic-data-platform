FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Only the dashboard's own dependencies; the pipeline's (dbt, Faker, Alembic) are not needed.
RUN pip install "streamlit~=1.66.0" "SQLAlchemy>=2.0" "psycopg[binary]>=3.1" "python-dotenv>=1.0"

COPY pyproject.toml README.md ./
COPY src src
COPY dashboard dashboard
COPY .streamlit .streamlit
RUN pip install --no-deps . \
    && useradd --create-home dashboard

USER dashboard
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
