from datetime import date

import pytest

from generator.cli import parse_args


def test_defaults_describe_a_full_history() -> None:
    args = parse_args([])

    assert (args.mode, args.seed, args.students, args.years) == ("full", None, 15_000, 8)


def test_arguments_are_parsed() -> None:
    args = parse_args(["--seed", "7", "--students", "500", "--years", "3"])

    assert (args.seed, args.students, args.years) == (7, 500, 3)


def test_daily_mode_accepts_days_or_a_date() -> None:
    assert parse_args(["--mode", "daily", "--days", "30"]).days == 30
    assert parse_args(["--mode", "daily", "--date", "2026-10-05"]).date == date(2026, 10, 5)


@pytest.mark.parametrize("argument", ["--students", "--years", "--days"])
def test_non_positive_counts_are_rejected(argument: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--mode", "daily", argument, "0"])


def test_days_and_date_cannot_be_combined() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--mode", "daily", "--days", "2", "--date", "2026-10-05"])


def test_days_are_rejected_in_full_mode(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--days", "2"])

    assert "apply to daily mode only" in capsys.readouterr().err
