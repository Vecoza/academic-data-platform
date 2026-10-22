import pytest

from ingestion.catalog import Column, SourceTable, column_type, select_tables

STUDENTS = SourceTable("students", "student_id", (Column("student_id", "bigint"),))
COURSES = SourceTable("courses", "course_id", (Column("course_id", "bigint"),))


@pytest.mark.parametrize(
    ("type_parts", "expected"),
    [
        (("bigint", "int8", None, 64, 0), "bigint"),
        (("character varying", "varchar", 80, None, None), "character varying(80)"),
        (("numeric", "numeric", None, 5, 2), "numeric(5,2)"),
        (("timestamp with time zone", "timestamptz", None, None, None), "timestamp with time zone"),
        (("USER-DEFINED", "degree_level", None, None, None), "degree_level"),
        (("ARRAY", "_text", None, None, None), "text[]"),
    ],
)
def test_column_type_is_rebuilt_from_information_schema(type_parts: tuple, expected: str) -> None:
    assert column_type(*type_parts) == expected


def test_all_tables_are_selected_by_default() -> None:
    assert select_tables([STUDENTS, COURSES], None) == [STUDENTS, COURSES]


def test_requested_tables_keep_their_order() -> None:
    assert select_tables([STUDENTS, COURSES], ["courses", "students"]) == [COURSES, STUDENTS]


@pytest.mark.parametrize("name", ["clock", "sim.clock", "alembic_version"])
def test_tables_outside_the_ingestible_set_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="Not ingestible"):
        select_tables([STUDENTS, COURSES], [name])
