"""Business rule triggers and automatic updated_at maintenance.

Revision ID: 004
Revises: 003
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

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
    op.execute("""
        CREATE FUNCTION check_enrollment_prerequisites() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            course_code           TEXT;
            missing_prerequisite  TEXT;
        BEGIN
            SELECT course.code, prerequisite.code
            INTO course_code, missing_prerequisite
            FROM course_offerings AS offering
            JOIN courses AS course
                ON course.course_id = offering.course_id
            JOIN course_prerequisites AS requirement
                ON requirement.course_id = offering.course_id
            JOIN courses AS prerequisite
                ON prerequisite.course_id = requirement.prerequisite_course_id
            WHERE offering.offering_id = NEW.offering_id
              AND NOT EXISTS (
                  SELECT 1
                  FROM enrollments AS passed_enrollment
                  JOIN course_offerings AS passed_offering
                      ON passed_offering.offering_id = passed_enrollment.offering_id
                  JOIN exam_attempts AS attempt
                      ON attempt.enrollment_id = passed_enrollment.enrollment_id
                  WHERE passed_enrollment.student_id = NEW.student_id
                    AND passed_offering.course_id = requirement.prerequisite_course_id
                    AND attempt.grade >= 6
              )
            ORDER BY prerequisite.code
            LIMIT 1;

            IF missing_prerequisite IS NOT NULL THEN
                RAISE EXCEPTION
                    'Student % cannot enroll in course %: prerequisite % has not been passed',
                    NEW.student_id, course_code, missing_prerequisite
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'rule_enrollments_prerequisites_passed';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_enrollments_check_prerequisites
            BEFORE INSERT OR UPDATE OF student_id, offering_id ON enrollments
            FOR EACH ROW EXECUTE FUNCTION check_enrollment_prerequisites();

        CREATE FUNCTION check_exam_attempt() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            enrollment_offering_id  BIGINT;
            term_offering_id        BIGINT;
        BEGIN
            SELECT offering_id
            INTO enrollment_offering_id
            FROM enrollments
            WHERE enrollment_id = NEW.enrollment_id
            FOR UPDATE;

            SELECT offering_id
            INTO term_offering_id
            FROM exam_terms
            WHERE exam_term_id = NEW.exam_term_id;

            -- A missing parent is reported by the foreign key check that follows.
            IF enrollment_offering_id IS NULL OR term_offering_id IS NULL THEN
                RETURN NEW;
            END IF;

            IF term_offering_id <> enrollment_offering_id THEN
                RAISE EXCEPTION
                    'Exam term % belongs to offering %, but enrollment % is for offering %',
                    NEW.exam_term_id, term_offering_id, NEW.enrollment_id, enrollment_offering_id
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'rule_exam_attempts_same_offering';
            END IF;

            IF (TG_OP = 'INSERT' OR NEW.enrollment_id <> OLD.enrollment_id OR NEW.grade >= 6)
               AND EXISTS (
                   SELECT 1
                   FROM exam_attempts
                   WHERE enrollment_id = NEW.enrollment_id
                     AND attempt_id <> NEW.attempt_id
                     AND grade >= 6
               ) THEN
                RAISE EXCEPTION
                    'Enrollment % already has a passing attempt',
                    NEW.enrollment_id
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'rule_exam_attempts_not_after_pass';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_exam_attempts_check_rules
            BEFORE INSERT OR UPDATE OF enrollment_id, exam_term_id, grade ON exam_attempts
            FOR EACH ROW EXECUTE FUNCTION check_exam_attempt();
    """)

    for table in TABLES:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_set_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_set_updated_at ON {table};")

    op.execute("""
        DROP TRIGGER trg_exam_attempts_check_rules ON exam_attempts;
        DROP FUNCTION check_exam_attempt();
        DROP TRIGGER trg_enrollments_check_prerequisites ON enrollments;
        DROP FUNCTION check_enrollment_prerequisites();
    """)
