"""Shared colors, number formats and chart helpers, so every page looks the same."""

from __future__ import annotations

from collections.abc import Sequence

import altair as alt
import pandas as pd
import streamlit as st

PRIMARY = "#2F5D8C"
MUTED = "#9AA5B1"
GREEN = "#4C9A6A"
AMBER = "#E0B04A"
RED = "#C0504D"
RISK_COLORS = {"low": GREEN, "medium": AMBER, "high": RED}
GROUP_COLORS = {"Active": PRIMARY, "Admitted": MUTED, "Graduated": GREEN, "Dropped out": RED}
RATE_FORMAT = ".1%"
GPA_FORMAT = ".2f"
COUNT_FORMAT = ",d"
GPA_RANGE = (6, 10)
LABEL_LIMIT = 320
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def percent(value: float | None) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.1%}"


def gpa(value: float | None) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.2f}"


def count(value: int | None) -> str:
    return "–" if value is None or pd.isna(value) else f"{int(value):,}"


def empty_state(message: str) -> None:
    st.info(message)


def count_column(label: str) -> st.column_config.NumberColumn:
    return st.column_config.NumberColumn(label, format="localized")


def percent_column(label: str) -> st.column_config.NumberColumn:
    """For a share already multiplied by 100 with `as_percentages`."""
    return st.column_config.NumberColumn(label, format="%.1f%%")


def as_percentages(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Copy of the frame with the given 0–1 shares expressed as 0–100."""
    return frame.assign(**{column: frame[column] * 100 for column in columns})


def group_scale(groups: Sequence[str]) -> alt.Scale:
    """Active, admitted, graduated and dropped-out students always get the same color."""
    return alt.Scale(domain=list(groups), range=[GROUP_COLORS[group] for group in groups])


def line_chart(
    frame: pd.DataFrame,
    x: str,
    y: str,
    x_title: str,
    y_title: str,
    y_format: str,
    color: str | None = None,
    color_scale: alt.Scale | None = None,
    y_range: tuple[float, float] | None = None,
) -> alt.Chart:
    scale = alt.Scale(domain=list(y_range)) if y_range else alt.Undefined
    encoding = {
        "x": alt.X(x, title=x_title, sort=None),
        "y": alt.Y(y, title=y_title, axis=alt.Axis(format=y_format), scale=scale),
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


def grouped_bar_chart(
    frame: pd.DataFrame,
    category: str,
    group: str,
    value: str,
    value_title: str,
    value_format: str,
) -> alt.Chart:
    """Horizontal bars per category, one bar per group within it."""
    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            y=alt.Y(category, title=None, axis=alt.Axis(labelLimit=LABEL_LIMIT)),
            yOffset=alt.YOffset(f"{group}:N"),
            x=alt.X(value, title=value_title, axis=alt.Axis(format=value_format)),
            color=alt.Color(f"{group}:N", title="Cohort", scale=alt.Scale(scheme="blues")),
            tooltip=[category, f"{group}:N", alt.Tooltip(value, format=value_format)],
        )
        .properties(height=alt.Step(12))
    )


def risk_scale() -> alt.Scale:
    return alt.Scale(domain=list(RISK_COLORS), range=list(RISK_COLORS.values()))
