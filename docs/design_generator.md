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
- **Points:** `65 + 12 × ability − 8 × difficulty + 4 × min(previous attempts, 2)`, plus normal noise with a standard deviation of 10, clipped to 0–100. Previous attempts count every earlier attempt at the course, also in earlier years. The bonus stops growing after the second retake, so a student who repeats a course does not keep getting easier exams.
- **Grades:** 0–54 → 5, 55–64 → 6, 65–74 → 7, 75–84 → 8, 85–94 → 9, 95–100 → 10.
- **Terms:** winter courses have January and February terms, summer courses have June and July terms, and both have a September retake term.
- **Attendance and retakes:**
  - 3% of enrollments never sit the exam at all (no-shows).
  - The others attend the first term with probability 0.95 and later terms with probability 0.85, and stop after a pass.
  - After two failed attempts in a year, half of the students give up on the course for that year and skip the September term.
  - No-shows and students who gave up end the year `failed`, not `withdrawn`: they took the course and did not pass it, and the pass rate must count them.
- **Failing a course:** the database sets no limit on attempts. An enrollment not passed after the September term is `failed`, and a mandatory course is taken again in the next academic year.
- **Withdrawals:** 3% of elective enrollments are `withdrawn` before any exam.

**Outcomes after the September term,** checked in this order:
1. **Graduation:** every mandatory course passed and the program's ECTS reached. `graduated_at` is the time of the last passed exam of the program.
2. **Maximum study length:** a student still enrolled three years after the nominal length is `dropped_out`.
3. **Dropout:** `dropped_out_at` is noon on 30 September, the end of the academic year in which the student left; this also applies to rule 2. The probability is `0.01 + 0.20 × (1 − ECTS this year / 60)²`, so a year with no ECTS gives 21% and a full year 1%.
4. **Transfer:** students in a program that has a sibling program (same faculty and degree level) transfer with probability 6% after their first year and 4% after their second, at most once. The old period is closed on 1 October, the new one opens the same day, and the student starts the new program from its first semester. Transfers are not scheduled after the last simulated year.

At the end of the history, 2% of the students who are still active are marked `suspended`.

### Calibration

The constants were tuned against the default run (seed 42, 15,000 students, 8 years) to hit the target rates.

**First calibration.** The first version used a base of 62 points and a retake bonus of 3. That produced an 18% dropout rate, a third of it from students stuck past the maximum study length, so the base and the retake bonus were raised.

**Pass-rate realism.** The warehouse's plausibility test then showed that 10.5% of course offerings with at least 30 decided enrollments passed more than 99% of their students. Over three exam terms, almost every student eventually passed an easy course, which real exam results do not show. Each change was measured on its own:

| Change | Offerings above 99% |
|---|---|
| None | 10.5% |
| Bonus capped after the second retake | 10.2% |
| Plus giving up after two failures (probability 0.5) | 7.3% |
| Plus giving up (probability 0.8) | 7.2% |
| Plus 3% no-shows, giving up at 0.5 (chosen) | 0.8% |
| Plus 5% no-shows, giving up at 0.5 | 0.3% |

Capping the bonus and giving up barely affect easy courses, because hardly anyone fails them twice. What the near-perfect offerings lacked were students who enrol and never sit the exam. A no-show rate of 3% was chosen as the smallest rate that meets the target of under 2%.

| Measure | Before | After |
|---|---|---|
| Offerings above 99% pass rate (≥ 30 decided) | 10.5% | 0.8% |
| Exam attempts passed | 61.9% | 64.6% |
| Enrollments passed (withdrawals excluded) | 87.5% | 83.7% |
| Students dropped out | 11.5% | 12.4% |
| Students transferred | 4.5% | 4.3% |
| Students graduated (all cohorts) | 53.2% | 50.4% |
| Students graduated (cohorts with at least two years beyond the nominal length) | 78.1% | 77.0% |

The overall graduation rate is lower than for older cohorts because the last cohorts are still studying when the history ends.

### Load time

Default run (15,000 students, 8 years) on a laptop with PostgreSQL in Docker:

| Step | Rows | Time |
|---|---|---|
| Simulation in memory | — | 7.5 s |
| Reference tables, students, program periods, offerings, exam terms | 42,000 | 1.9 s |
| Enrollments | 406,000 | 78 s |
| Exam attempts | 570,000 | 88 s |
| **Total load** | 1,019,000 | 168 s |

Almost all of the time goes to the two trigger-checked tables. Each enrollment runs the prerequisite query, and each attempt locks its enrollment row and checks for an earlier pass. Both queries are served by existing indexes: the unique keys on `enrollments (student_id, offering_id)` and `exam_attempts (enrollment_id, exam_term_id)`.

### Load time investigation

The same full load took 168 s in one run and 321–324 s in later runs on the same laptop, which is over the five-minute budget. The investigation below found where the time goes and showed that none of the obvious tunings help. None of them was kept.

**Where the time goes.** These measurements used 5,000 students (347,000 rows), each load inside a transaction that was rolled back:

| Variant | Time |
|---|---|
| Everything enabled | 79–170 s across runs |
| Business-rule triggers disabled, foreign keys still checked | 155 s |
| All triggers disabled, foreign-key checks included (`session_replication_role = replica`) | 3.1 s |

About 96% of the load time is spent in per-row checks: the foreign-key checks PostgreSQL runs for every inserted row, plus the two business-rule triggers. `auto_explain` showed no slow statement among them. Each check is an index lookup costing roughly 0.1–0.3 ms when PostgreSQL runs inside Docker Desktop on this machine, and there are several per row. Identical runs differed by up to ±30%, so only large effects can be measured on this setup.

**What was tried and not kept:**
- **`ANALYZE` between batches,** in case the cached plans of the trigger queries had been made while the tables were empty. The plans were already index scans, and the extra `ANALYZE` statements made the load slower (282 s against 170 s).
- **An early exit in the prerequisite trigger** for courses without prerequisites. Alternating runs showed no difference: 47.8 and 60.8 s with it, against 41.8 and 62.8 s without.
- **Larger server settings** (`shared_buffers = 512MB`, `max_wal_size = 4GB`). The results (98 and 139 s) stayed within the noise of the default settings.

**Decision.** The load is kept as it is: every trigger and foreign key stays enabled. On this laptop the full load takes between about 3 and 5.5 minutes depending on the machine's state, and the same tests run three times faster in CI. The options that would make it faster are listed under possible improvements.

## Daily mode

Daily mode turns the finished history into a live system. Each run simulates one or more days after the history and writes them to the operational database with ordinary `INSERT`, `UPDATE` and `DELETE` statements, the same way an application would. This gives the ingestion pipeline real incremental work: new rows, changed rows and the occasional deleted row.

### Simulation clock

The clock is a single row in `sim.clock`, in a separate `sim` schema so that ingestion, which reads `public`, never sees it.

| Column | Meaning |
|---|---|
| `simulated_date` | The next day to simulate |
| `seed` | The seed of the full load; daily runs reuse it |
| `last_run_at` | Wall-clock time of the last daily run, `NULL` after a full load |

The column is called `simulated_date` rather than `current_date`, because `CURRENT_DATE` is a reserved SQL function and the name would have to be quoted everywhere.

Full mode sets the clock to 1 October after the last academic year of the history, the first day of the next academic year.

**One transaction per day.** A daily run reads the clock with `SELECT ... FOR UPDATE`, writes that day's activity, moves the clock one day forward and commits. If a day fails, its changes and the clock move are rolled back together, and the next run retries the same day.

**Choosing which days to run.**
- `--days N` simulates the next N days.
- `--date D` simulates every day up to and including D.
- If D has already been simulated, the run changes nothing and logs that the date was already done. This makes daily mode safe to repeat, for example when a scheduler retries a job.

**Determinism.** All random choices of a day come from a random generator and a Faker instance seeded with the full-load seed and the date (`"42:daily:2026-10-01"`). Every query that feeds a random choice has an `ORDER BY`. The same history and the same sequence of days therefore produce the same rows, including identity values, in any database.

### What happens on a day

| When | Activity |
|---|---|
| 1 October, 1 March | The winter or summer semester row is inserted. |
| 1 October | Students who completed their program become `graduated`, dated by their last passed exam. A new cohort is admitted, sized on the previous three cohorts ±10%, each student with an `enrollment` program period. |
| First 5 days of a semester | Active students enroll with status `enrolled`, a fifth of them each day (`student_id % 5`). They follow the same course selection rules as the history. Missing course offerings and their three exam terms are created on first enrollment, taught by the course's usual professor 80% of the time. |
| First 30 days of a semester | Up to 3 elective enrollments a day without attempts become `withdrawn`. |
| Exam days | Every enrollment still `enrolled` for an offering with an exam term that day, belonging to an active student, may sit the exam. Attendance, no-shows and giving up follow the history's rules. A no-show is decided per enrollment from the seed and the enrollment id, so it stays the same on every exam day. Expected points are the average of the student's and the course's past points, plus the capped retake bonus. A pass sets the enrollment to `passed`. After the September term, enrollments still `enrolled` become `failed`. |
| Every day | 0–2 email corrections and 0–2 city corrections. With probability 0.3, a grade correction on an attempt from the last year: the points move by up to 3 without crossing the pass mark, and the grade follows the scale. |
| Every day, rarely | A dropout (probability 0.15), dated that day, which also withdraws the student's enrollments that have no attempts; a suspension (0.05); a reinstatement of a suspended student (0.05); and a transfer to a sibling program (0.03), which closes the old period on that day and opens the new one. |
| Every day, rarely | With probability 0.3, one withdrawn enrollment without exam attempts is deleted. These are the only deletes the generator makes, so the ingestion pipeline has a small, well-defined set of deletes to detect. |

Daily mode never sets `updated_at` itself; the `set_updated_at()` triggers do. Because each day commits separately, every updated row gets that day's transaction time.

The hidden ability and difficulty values of the history are not stored in the database. Daily mode estimates them from the stored results instead: the student's and the course's average points so far.

## Possible improvements

- **Statement-level business-rule triggers.** Rewrite the prerequisite and exam-attempt rules as `AFTER INSERT ... FOR EACH STATEMENT` triggers with transition tables. Each `COPY` batch would then be checked with one set-based query instead of one query per row, which should cut most of the trigger cost of the bulk load. The trade-off: the rules would be checked after the batch rather than row by row, so a violation would report the first offending row of the batch instead of rejecting the exact insert, and the single-row semantics would have to be re-tested.
- **Optional bulk-load mode without checks.** Disable triggers during `COPY` and validate the loaded data afterwards with the same rules expressed as queries. It is faster, but a load would no longer prove by itself that the data obeys every rule.
- **A database host outside a desktop virtual machine.** Most of the per-row cost observed locally comes from running PostgreSQL inside Docker Desktop.
