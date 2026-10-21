# OLTP design

The operational database `university` records what a student information system records day to day: who studies what, which courses run in which semester, who enrolled, and how each exam went. It is optimized for correct, concurrent writes, not for analysis. Analytical modelling happens later, in the warehouse.

The diagram is in [erd_oltp.md](erd_oltp.md).

## Database responsibilities

One PostgreSQL server hosts two databases, each with a single owner of its structure.

| Database | Structure created by | Data written by |
|---|---|---|
| `university` | Alembic migrations in `db/migrations` | The data generator, as the operational application |
| `warehouse` | `docker/init` on the first start of the server: the database and its `raw`, `staging`, `intermediate`, `marts` and `meta` schemas | Ingestion (`raw`, `meta`) and dbt (`staging`, `intermediate`, `marts`) |

Alembic manages only `university`. The warehouse schemas are containers whose tables belong to the tools that fill them, so versioning them in a second migration history would duplicate work done by ingestion and dbt.

The init script reads the warehouse name from the `WAREHOUSE_DB` environment variable with psql's `\getenv` meta-command, which requires psql 16 or newer. The `postgres:16` image ships a matching psql. Anywhere else, for example in CI, the script must be run with a psql 16+ client.

## Tables

### Reference data

| Table | Purpose | Business key |
|---|---|---|
| `faculties` | Organizational units that own programs and employ professors. | `code`; `name` |
| `programs` | Study programs (for example Computer Science, bachelor). Degree level, length in semesters and the ECTS required to graduate. | (`name`, `degree_level`) |
| `professors` | Teaching staff, each employed by one faculty. | `email` |
| `courses` | Courses in a program's curriculum, with ECTS, the recommended semester and whether the course is mandatory. | `code` |
| `course_prerequisites` | Directed "course A requires course B" pairs. A course can have many prerequisites and be a prerequisite for many courses. | (`course_id`, `prerequisite_course_id`) |
| `semesters` | Calendar of teaching periods: academic year, winter or summer term, start and end dates. | (`academic_year`, `term`) |

### Students

| Table | Purpose | Business key |
|---|---|---|
| `students` | One row per person who ever enrolled: identity, contact data, cohort (`enrollment_year`) and current study status. | `index_number`; `email` |
| `student_programs` | History of which program a student belonged to and when. A transfer closes the open row and opens a new one. | (`student_id`, `valid_from`) |

### Teaching and examination

| Table | Purpose | Business key |
|---|---|---|
| `course_offerings` | A course taught in a specific semester by a specific professor, with a capacity. The curriculum (`courses`) is separate from its delivery. | (`course_id`, `semester_id`) |
| `enrollments` | A student registered for one course offering, and the state of that registration. | (`student_id`, `offering_id`) |
| `exam_terms` | Scheduled exam dates for an offering (for example the January and the September term). | (`offering_id`, `term_type`) |
| `exam_attempts` | One student sitting one exam term: points and grade. Failing creates the need for another attempt in a later term. | (`enrollment_id`, `exam_term_id`) |

Grades use the 5–10 scale: 5 is a fail, 6 to 10 are passing grades.

## Normalization

A useful way to explain the model is to start from the flat record a registrar might keep in a spreadsheet, one row per exam:

```
index_number, student_name, student_email, program, faculty, course_code, course_name,
ects, prerequisites, professor, professor_email, semester, exam_date, points, grade
```

**First normal form: atomic values, no repeating groups.**
`prerequisites` holds a list such as `MAT101, PRG101`, and attempts would end up as repeating columns (`attempt_1_grade`, `attempt_2_grade`). Lists become rows: prerequisites move to `course_prerequisites`, one row per pair, and attempts move to `exam_attempts`, one row per attempt. `student_name` is split into `first_name` and `last_name`, so each column holds one value.

**Second normal form: no partial dependency on a composite key.**
The natural key of the flat row is (`index_number`, `course_code`, `semester`, `exam_date`). Many columns depend on only part of it: `course_name` and `ects` depend only on `course_code`, and `student_email` only on `index_number`. Each of these groups becomes its own table (`courses`, `students`, `semesters`) with its own key, and the remaining facts link to them.

**Third normal form: no transitive dependency.**
After 2NF, some non-key columns still depend on other non-key columns:
- `faculty` depends on `program`, which depends on the course. Faculties get their own table, and programs reference them.
- `professor_email` depends on `professor`, not on the exam. Professors get their own table.
- The professor depends on the course *in a given semester*, not on the course itself. That is why `course_offerings` exists between `courses` and `semesters`.
- A student's program changes over time. It is a fact about a period, not about the student, so it lives in `student_programs` instead of a `program_id` column on `students`.

Each non-key column now describes the key of its own table, the whole key and nothing else.

Two columns look like candidates for redundancy but are kept on purpose:
- **`exam_attempts.grade` and `points`.** The grade is the official recorded result. Points are the written score. A professor can adjust the grade after an oral part, so the grade is not a function of the points, and storing both introduces no dependency.
- **`enrollments.status`.** Passing can be derived from `exam_attempts`, but `withdrawn`, and `failed` after the last allowed term, cannot. The status is a workflow state owned by the writing application. The source of truth for "passed" stays `exam_attempts`: the triggers below check attempts, not the status, so a stale status can never let invalid data in. Consistency between the two is checked by data quality tests in the warehouse.

## Key decisions

### Surrogate keys plus enforced business keys

Every table has a `bigint GENERATED BY DEFAULT AS IDENTITY` primary key, plus `created_at` and `updated_at`.
- **Stable references.** Business keys change: a course code is renamed, a student's email changes. Foreign keys on surrogate keys never have to be updated.
- **Uniform ingestion.** Every table has a single-column key, so the incremental pipeline can upsert all tables the same way.
- **Real duplicates are still rejected.** A surrogate key alone allows two rows that describe the same thing. Every table therefore also has a `UNIQUE` constraint on its business key (see the tables above), which the database enforces.

`course_prerequisites` is a pure association table and could use (`course_id`, `prerequisite_course_id`) as its primary key. It gets a surrogate key anyway, with the pair as a unique constraint, so it follows the same convention as every other table.

### `GENERATED BY DEFAULT` identity columns

Identity columns are `GENERATED BY DEFAULT`, not `GENERATED ALWAYS`.
- **Bulk loading.** The data generator loads full history with `COPY`, which cannot return generated keys. It therefore assigns ids in memory, so that parent and child rows can reference each other before anything is written.
- **Sequences are reset afterwards.** Once a bulk load finishes, the generator moves each sequence past the highest loaded id with `setval`, so later inserts cannot collide.
- **Applications are unaffected.** A normal insert that omits the id still gets one from the sequence.

The trade-off is that a client could supply an id explicitly and collide with the sequence later. Only the bulk loader does that, and it resets the sequences when it is done.

### Enumerations as `text` with `CHECK`

Status-like columns (`status`, `term`, `degree_level`, `title`, ...) are `text` columns limited by a `CHECK (... IN (...))` list.
- **Rejected: PostgreSQL `ENUM` types.** Values cannot be removed or renamed easily.
- **Rejected: lookup tables.** They would add a join for values that carry no attributes of their own.

A `CHECK` list is one statement to change in a migration.

### Program history in `student_programs`

Program membership changes when a student transfers. Overwriting a `program_id` on `students` would lose the past, and the warehouse needs that history for its Type 2 student dimension.

`student_programs` stores closed-open periods:
- `valid_from` is the date the student joined the program.
- `valid_to` is the date they left, and `NULL` while current.
- `reason` says why the period started (`enrollment` or `transfer`).

Rules:
- `CHECK (valid_to IS NULL OR valid_to > valid_from)`: a period cannot end before it starts.
- Partial unique index on `student_id WHERE valid_to IS NULL`: at most one current program per student.
- `EXCLUDE USING gist (student_id WITH =, daterange(valid_from, valid_to) WITH &&)`, using the `btree_gist` extension: no two periods of the same student overlap. This is a declarative alternative to a trigger.

Graduation and dropout are recorded in `students.status`. The last period stays open as "the program the student belongs, or last belonged, to".

### `ON DELETE` behaviour

The default is `ON DELETE RESTRICT` on every foreign key. Academic records are historical facts. Deleting a faculty, a course or a student that is still referenced is almost always a mistake, and the database should refuse it instead of silently removing transcripts. `RESTRICT` is used rather than the implicit `NO ACTION` to make that intent explicit and to check immediately, not at the end of the statement.

The one exception is `course_prerequisites`. Both of its foreign keys use `ON DELETE CASCADE`, because a prerequisite pair has no meaning without both courses. Since `courses` is itself protected by `RESTRICT` from offerings, this cascade only takes effect for a course that was never taught.

Keeping deletes rare also matters downstream. Incremental extraction is based on `updated_at` and cannot see a deleted row. A schema in which history is not deleted keeps that limitation small. The handling of deletes is described in the ingestion design.

### Which rules live where

A `CHECK` constraint can only see the row being written. Rules that need other rows or tables are implemented as triggers.

| Rule | Mechanism |
|---|---|
| Grade 5–10, points 0–100, ECTS 1–15, `end_date > start_date`, `valid_to > valid_from`, a course is not its own prerequisite, enumerations | `CHECK` |
| Business keys (see the tables above), one current program per student | `UNIQUE`, partial unique index |
| Non-overlapping program periods | `EXCLUDE` constraint |
| `updated_at` maintained on every update | `BEFORE UPDATE` trigger `set_updated_at()` on every table |
| A student can enroll in a course only after passing (grade ≥ 6) every prerequisite | `BEFORE INSERT` trigger on `enrollments` |
| An attempt must belong to an exam term of the same offering as its enrollment | `BEFORE INSERT OR UPDATE` trigger on `exam_attempts` |
| No new attempt for an enrollment that already has a passing attempt | same trigger on `exam_attempts` |

**Why in the database and not only in application code.** Several writers touch this database: the data generator, manual corrections, and any future application. A rule enforced only in one of them is a rule the others can break. In the database it holds for every writer. It also makes the generator's output trustworthy: if the generated history loads, it obeys the rules.

**Trade-offs.**
- **Per-row cost.** Triggers run for every row, which slows bulk loads. The generator has to insert in a valid order (prerequisite results before dependent enrollments), and that is part of what it demonstrates.
- **Concurrency.** Triggers that read other rows can race under `READ COMMITTED`: two simultaneous passing attempts for the same enrollment could both pass the check. The trigger locks the parent enrollment row (`SELECT ... FOR UPDATE`) before checking, which serializes writers per enrollment.

**Rules deliberately not enforced in the database:**
- **Course capacity.** Registrars routinely allow over-enrollment, so capacity is a soft limit respected by the generator.
- **`semester_number` within the program's `duration_semesters`.** A cross-table check with little value.
- **Every student having at least one program period.** This needs a deferred constraint trigger. It is guaranteed by the writer and verified by a warehouse data quality test.

### Timestamps and incremental extraction

- `created_at` and `updated_at` are `timestamptz` with `DEFAULT now()`. The trigger sets `updated_at = now()` on every update, so no writer can forget it.
- `now()` returns the start time of the transaction, not its commit time. A long transaction can therefore commit rows whose `updated_at` is older than rows already extracted. The ingestion pipeline compensates with a small overlap window on its watermark.
- `updated_at` is indexed on every table, so that extraction query stays an index range scan.

### Indexes

PostgreSQL indexes primary keys and unique constraints automatically, but not foreign key columns. Every foreign key column gets an index, unless it is the leading column of a unique constraint that already covers it. This keeps joins fast and keeps `RESTRICT` checks on parent deletes from scanning child tables.

### Known simplifications

- A course belongs to exactly one program. Real universities share courses between programs, which would need a `program_courses` association table.
- One professor per course offering. Team teaching would need an `offering_professors` table.
- No authentication, personal data protection or audit tables. Those are outside the scope of a data engineering project.
