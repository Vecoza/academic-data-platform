# Data generator design

Real student records are private, so the operational database is filled by a seeded generator. It runs in two modes:
- **Full mode** replaces all data with a complete history.
- **Daily mode** adds one day of new activity on top of it.

## Determinism

The same seed and the same dependency versions always produce the same database.
- **Separate random streams.** Each part of the generator uses its own `random.Random` instance, seeded with the seed plus a fixed label (for example `"42:reference"`). Adding a new part therefore does not change the output of existing parts.
- **Seeded Faker.** Personal names come from Faker with the Croatian locale `hr_HR`, seeded the same way.
- **No wall clock.** The history ends with a fixed academic year (2025/26) instead of "this year". `--years` controls how far back it starts.

## Reference data

The faculties, programs and their subjects are described statically in `generator/catalog.py`:
- 4 faculties and 8 programs;
- 6 bachelor programs of 6 semesters and 180 ECTS;
- 2 master programs of 4 semesters and 120 ECTS.

The randomness is in the curriculum and the staff.

**Curriculum.**
- Every semester of a program has four mandatory courses worth 24 ECTS in total. The ECTS split varies, for example 8 + 6 + 5 + 5. Students complete the remaining 6 ECTS of each semester with one elective worth 6 ECTS.
- Each program has 40 to 60 courses in total. Electives fill the difference and are spread over semesters 2 and later.
- Course codes combine the program code, the semester and a sequence number, for example `CSB203`.

**Prerequisites.** Every prerequisite is a mandatory course of the same program in an earlier semester. That keeps the graph acyclic and every course reachable in the normal order of study.
- A subject that continues in a later semester ("Programming II") requires the previous part ("Programming I").
- A quarter of the mandatory courses also require a random course from the previous semester.
- Half of the electives require one earlier mandatory course.

**Professors.** Each faculty has at least 10 professors, or one per five courses, whichever is more. Titles are drawn from a fixed distribution. Emails are reduced to ASCII letters (`Đurđević` → `durdevic`) and made unique.

**Semesters.** Each academic year has a winter semester (1 October to 31 January) and a summer semester (1 March to 15 June).

## Loading

Full mode loads everything in one transaction:
1. `TRUNCATE` all operational tables, restarting their identity sequences.
2. Load the reference tables, then students, program periods, course offerings and exam terms, each with `COPY` and using the ids assigned in memory.
3. Load enrollments and exam attempts period by period, in chronological order (see below).
4. Move each identity sequence past the highest loaded id with `setval`.

If any step fails, the transaction rolls back and the previous data stays untouched. Running full mode again with the same seed produces the same database, so the job is idempotent.

Triggers and constraints stay enabled during the load. A successful load is therefore proof that the generated data obeys every rule of the schema. Load times per table are logged.

### Why enrollments are loaded in chronological batches

The prerequisite trigger checks, at the moment an enrollment is inserted, that the student already has a passing attempt for every prerequisite. Loading all enrollments first and all attempts afterwards would therefore reject every enrollment in a course with prerequisites.

The simulation groups its output into three periods per academic year: winter, summer and the September term. The loader copies each period's enrollments and then its attempts before moving to the next period. That is the order in which the data would have arrived in a live system. Every prerequisite an enrollment depends on was passed in an earlier period, so it is already in the database when the enrollment is inserted.

## Student history

The simulation walks through the academic years in order. Every decision uses only results known at that moment: a student enrolling in March sees the January and February results, but not the September ones.

**Cohorts.**
- Each academic year admits a new cohort. The requested number of students is split over the years, with sizes varying by up to ±10%.
- Bachelor programs are twice as likely to be chosen as master programs.
- Each student has a hidden ability, and each course a hidden difficulty, both drawn from a standard normal distribution.

**Enrollment.** At the start of each semester, an active student enrolls in:
- every mandatory course up to their current program semester, for that term, that is not yet passed and whose prerequisites were passed before the semester started. This covers first-time courses, retakes and courses that were blocked by a prerequisite.
- up to two electives, while they have passed fewer electives than the semesters they have reached. Each wanted elective is taken with probability 0.9. Failed electives are not retaken; another elective is chosen instead.

Offerings and their exam terms are created when the first student enrolls. 80% of offerings are taught by the course's regular professor. Capacity is set to about 120% of the enrollments.

**Exams.**
- **Points:** `65 + 12 × ability − 8 × difficulty + 4 × previous attempts`, plus normal noise with a standard deviation of 10, clipped to 0–100.
- **Grades:** 0–54 → 5, 55–64 → 6, 65–74 → 7, 75–84 → 8, 85–94 → 9, 95–100 → 10.
- **Terms:** winter courses have January and February terms, summer courses have June and July terms, and both have a September retake term.
- **Attendance and retakes:** students attend the first term with probability 0.95 and later terms with probability 0.85. They stop after a pass.
- **Failing a course:** the database sets no limit on attempts. An enrollment not passed after the September term is `failed`, and a mandatory course is taken again in the next academic year.
- **Withdrawals:** 3% of elective enrollments are `withdrawn` before any exam.

**Outcomes after the September term,** checked in this order:
1. **Graduation:** every mandatory course passed and the program's ECTS reached.
2. **Maximum study length:** a student still enrolled three years after the nominal length is `dropped_out`.
3. **Dropout:** the probability is `0.01 + 0.20 × (1 − ECTS this year / 60)²`, so a year with no ECTS gives 21% and a full year 1%.
4. **Transfer:** students in a program that has a sibling program (same faculty and degree level) transfer with probability 6% after their first year and 4% after their second, at most once. The old period is closed on 1 October, the new one opens the same day, and the student starts the new program from its first semester. Transfers are not scheduled after the last simulated year.

At the end of the history, 2% of the students who are still active are marked `suspended`.

### Calibration

The constants were tuned against the default run (seed 42, 15,000 students, 8 years) to hit the target rates. The first version used a base of 62 points and a retake bonus of 3. That produced an 18% dropout rate, a third of it from students stuck past the maximum study length, so the base and the retake bonus were raised.

| Measure | Result |
|---|---|
| Exam attempts passed | 61.9% |
| Enrollments passed (withdrawals excluded) | 87.5% |
| Students dropped out | 11.5% |
| Students transferred | 4.5% |
| Students graduated (all cohorts) | 53.2% |
| Students graduated (cohorts with at least two years beyond the nominal length) | 78.1% |

The overall graduation rate is lower because the last cohorts are still studying when the history ends.

### Load time

Default run (15,000 students, 8 years) on a laptop with PostgreSQL in Docker:

| Step | Rows | Time |
|---|---|---|
| Simulation in memory | — | 7.5 s |
| Reference tables, students, program periods, offerings, exam terms | 42,000 | 1.9 s |
| Enrollments | 406,000 | 78 s |
| Exam attempts | 570,000 | 88 s |
| **Total load** | 1,019,000 | 168 s |

The full run stays under the five-minute budget with all triggers enabled, so the trigger queries and indexes were left unchanged. Almost all of the time goes to the two trigger-checked tables, at about 0.2 ms per row. Each enrollment runs the prerequisite query, and each attempt locks its enrollment row and checks for an earlier pass. Both queries are served by existing indexes: the unique keys on `enrollments (student_id, offering_id)` and `exam_attempts (enrollment_id, exam_term_id)`.
