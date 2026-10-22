"""When a student graduated or dropped out.

Existing graduates get the time of their last passed exam in their current program, existing
dropouts the time of their last enrollment or exam, so the constraint holds for old rows too.

Revision ID: 007
Revises: 006
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE students
            ADD COLUMN graduated_at TIMESTAMPTZ,
            ADD COLUMN dropped_out_at TIMESTAMPTZ;

        UPDATE students AS student
        SET graduated_at = last_pass.attempted_at
        FROM (
            SELECT enrollment.student_id, MAX(attempt.attempted_at) AS attempted_at
            FROM exam_attempts AS attempt
            JOIN enrollments AS enrollment ON enrollment.enrollment_id = attempt.enrollment_id
            JOIN course_offerings AS offering ON offering.offering_id = enrollment.offering_id
            JOIN courses AS course ON course.course_id = offering.course_id
            JOIN student_programs AS period
                ON period.student_id = enrollment.student_id
                AND period.program_id = course.program_id
                AND period.valid_to IS NULL
            WHERE attempt.grade >= 6
            GROUP BY enrollment.student_id
        ) AS last_pass
        WHERE student.student_id = last_pass.student_id
          AND student.status = 'graduated';

        UPDATE students AS student
        SET dropped_out_at = COALESCE(
            (
                SELECT MAX(GREATEST(enrollment.enrolled_at, attempt.attempted_at))
                FROM enrollments AS enrollment
                LEFT JOIN exam_attempts AS attempt
                    ON attempt.enrollment_id = enrollment.enrollment_id
                WHERE enrollment.student_id = student.student_id
            ),
            student.updated_at
        )
        WHERE student.status = 'dropped_out';

        UPDATE students
        SET graduated_at = updated_at
        WHERE status = 'graduated' AND graduated_at IS NULL;

        ALTER TABLE students
            ADD CONSTRAINT ck_students_exit_date_matches_status CHECK (
                (graduated_at IS NOT NULL) = (status = 'graduated')
                AND (dropped_out_at IS NOT NULL) = (status = 'dropped_out')
            );
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE students
            DROP CONSTRAINT ck_students_exit_date_matches_status,
            DROP COLUMN dropped_out_at,
            DROP COLUMN graduated_at;
    """)
