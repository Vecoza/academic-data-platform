"""Cached access to the queries for the pages. The connection uses the read-only role."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, create_engine

from academic_platform.config import DatabaseSettings
from dashboard import queries

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300


@st.cache_resource
def engine() -> Engine:
    return create_engine(DatabaseSettings.for_dashboard().url, pool_pre_ping=True)


def run(query: Callable[..., pd.DataFrame], *args: object) -> pd.DataFrame:
    """Run a query with a connection of the reader role and log how long it took."""
    started = time.perf_counter()
    with engine().connect() as connection:
        result = query(connection, *args)
    logger.info(
        "query=%s rows=%d seconds=%.3f", query.__name__, len(result), time.perf_counter() - started
    )
    return result


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def overview_kpis() -> pd.DataFrame:
    return run(queries.overview_kpis)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def yearly_trends() -> pd.DataFrame:
    return run(queries.yearly_trends)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def cohort_outcomes() -> pd.DataFrame:
    return run(queries.cohort_outcomes)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def pass_rate_filter_options() -> pd.DataFrame:
    return run(queries.pass_rate_filter_options)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def course_pass_rates(
    faculties: tuple[str, ...],
    programs: tuple[str, ...],
    academic_years: tuple[str, ...],
    terms: tuple[str, ...],
) -> pd.DataFrame:
    return run(queries.course_pass_rates, faculties, programs, academic_years, terms)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def professor_pass_rates(
    faculties: tuple[str, ...],
    programs: tuple[str, ...],
    academic_years: tuple[str, ...],
    terms: tuple[str, ...],
) -> pd.DataFrame:
    return run(queries.professor_pass_rates, faculties, programs, academic_years, terms)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def student_choices() -> pd.DataFrame:
    return run(queries.student_choices)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def student_gpa_trend(student_id: int) -> pd.DataFrame:
    return run(queries.student_gpa_trend, student_id)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def cohort_gpa_averages(program_label: str, cohort_year: int) -> pd.DataFrame:
    return run(queries.cohort_gpa_averages, program_label, cohort_year)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def dropout_risk_by_program() -> pd.DataFrame:
    return run(queries.dropout_risk_by_program)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def at_risk_students(programs: tuple[str, ...], risk_levels: tuple[str, ...]) -> pd.DataFrame:
    return run(queries.at_risk_students, programs, risk_levels)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def time_to_graduation() -> pd.DataFrame:
    return run(queries.time_to_graduation)
