"""Shared colors, number formats and chart helpers, so every page looks the same."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

PRIMARY = "#2F5D8C"
SECONDARY = "#E08E45"
MUTED = "#9AA5B1"
RISK_COLORS = {"low": "#4C9A6A", "medium": "#E0B04A", "high": "#C0504D"}
TERM_COLORS = {"winter": PRIMARY, "summer": SECONDARY}
RATE_FORMAT = ".1%"
GPA_FORMAT = ".2f"
LABEL_LIMIT = 320
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
COMPLETE_COHORT_SHARE = 0.05


def percent(value: float | None) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.1%}"


def gpa(value: float | None) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.2f}"


def count(value: int | None) -> str:
    return "–" if value is None or pd.isna(value) else f"{int(value):,}"


def empty_state(message: str) -> None:
    st.info(message, icon="ℹ️")


def line_chart(
    frame: pd.DataFrame,
    x: str,
    y: str,
    x_title: str,
    y_title: str,
    y_format: str,
    color: str | None = None,
    color_scale: alt.Scale | None = None,
) -> alt.Chart:
    encoding = {
        "x": alt.X(x, title=x_title, sort=None),
        "y": alt.Y(y, title=y_title, axis=alt.Axis(format=y_format)),
        "tooltip": [x, alt.Tooltip(y, format=y_format)],
    }
    chart = alt.Chart(frame).mark_line(point=True, color=PRIMARY)
    if color:
        encoding["color"] = alt.Color(
            color,
            title=None,
            scale=color_scale or alt.Undefined,
            legend=alt.Legend(labelLimit=LABEL_LIMIT),
        )
        encoding["tooltip"] = [color, *encoding["tooltip"]]
        chart = alt.Chart(frame).mark_line(point=True)
    return chart.encode(**encoding).properties(height=280)


def bar_chart(
    frame: pd.DataFrame,
    x: str,
    y: str,
    x_title: str,
    y_title: str,
    x_format: str,
    color: str = PRIMARY,
) -> alt.Chart:
    """Horizontal bars, one per category, sorted by value."""
    return (
        alt.Chart(frame)
        .mark_bar(color=color)
        .encode(
            x=alt.X(x, title=x_title, axis=alt.Axis(format=x_format)),
            y=alt.Y(y, title=y_title, sort="-x", axis=alt.Axis(labelLimit=LABEL_LIMIT)),
            tooltip=[y, alt.Tooltip(x, format=x_format)],
        )
        .properties(height=alt.Step(22))
    )


def risk_scale() -> alt.Scale:
    return alt.Scale(domain=list(RISK_COLORS), range=list(RISK_COLORS.values()))
