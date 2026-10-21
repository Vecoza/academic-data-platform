"""Indexes on foreign keys not covered by a unique constraint, and on updated_at.

Revision ID: 005
Revises: 004
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

FOREIGN_KEY_COLUMNS = (
    ("programs", "faculty_id"),
    ("professors", "faculty_id"),
    ("courses", "program_id"),
    ("course_prerequisites", "prerequisite_course_id"),
    ("student_programs", "program_id"),
    ("course_offerings", "semester_id"),
    ("course_offerings", "professor_id"),
    ("enrollments", "offering_id"),
    ("exam_attempts", "exam_term_id"),
)

TABLES = (
    "faculties",
    "programs",
    "professors",
    "semesters",
    "courses",
    "course_prerequisites",
    "students",
    "student_programs",
    "course_offerings",
    "enrollments",
    "exam_terms",
    "exam_attempts",
)


def upgrade() -> None:
    for table, column in FOREIGN_KEY_COLUMNS:
        op.execute(f"CREATE INDEX ix_{table}_{column} ON {table} ({column});")

    for table in TABLES:
        op.execute(f"CREATE INDEX ix_{table}_updated_at ON {table} (updated_at);")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP INDEX ix_{table}_updated_at;")

    for table, column in FOREIGN_KEY_COLUMNS:
        op.execute(f"DROP INDEX ix_{table}_{column};")
