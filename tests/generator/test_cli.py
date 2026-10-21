import pytest

from generator.cli import parse_args


def test_defaults_describe_a_full_history() -> None:
    args = parse_args([])

    assert (args.mode, args.seed, args.students, args.years) == ("full", 42, 15_000, 8)


def test_arguments_are_parsed() -> None:
    args = parse_args(["--seed", "7", "--students", "500", "--years", "3"])

    assert (args.seed, args.students, args.years) == (7, 500, 3)


@pytest.mark.parametrize("argument", ["--students", "--years"])
def test_non_positive_counts_are_rejected(argument: str) -> None:
    with pytest.raises(SystemExit):
        parse_args([argument, "0"])


def test_daily_mode_is_rejected_until_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--mode", "daily"])

    assert "daily mode is not implemented yet" in capsys.readouterr().err
