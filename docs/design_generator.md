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
2. Load each table with `COPY`, in dependency order, using the ids assigned in memory.
3. Move each identity sequence past the highest loaded id with `setval`.

If any step fails, the transaction rolls back and the previous data stays untouched. Running full mode again with the same seed produces the same database, so the job is idempotent.

Triggers and constraints stay enabled during the load. A successful load is therefore proof that the generated data obeys every rule of the schema. Load times per table are logged so their cost can be measured as the data grows.

## Rules for the simulated history

These rules apply to the student simulation, which builds on the reference data:
- **Grades from points:** 0–54 → 5, 55–64 → 6, 65–74 → 7, 75–84 → 8, 85–94 → 9, 95–100 → 10.
- **Exam terms:** winter courses have January and February terms, summer courses have June and July terms, and both have a September retake term.
- **Failing a course:** the database sets no limit on attempts. An enrollment that has not passed after the September term is marked `failed`, and the student enrolls again in the next academic year.
