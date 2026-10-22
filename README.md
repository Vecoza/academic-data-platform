# Academic Data Platform

An end-to-end data engineering project that models a university's operational system and turns it into an analytical data warehouse.

> **Status:** In development. The platform is being built in phases; see the roadmap below.

## Background

The idea for this project comes from my university studies. Several courses each covered one piece of the same puzzle:

- **Databases**: relational modelling, normalization, constraints, SQL
- **Programming in Python**: writing structured, testable programs
- **Data Warehousing and Business Intelligence**: dimensional modelling, ETL, reporting
- **Software Engineering**: version control, testing, project organization
- **Operating Systems and Computer Networks**: processes, containers, client–server communication

In the courses these topics were taught separately, each with its own small exercises. I wanted to see how they fit together in a single, realistic system, so I decided to combine them into one project and build it in my free time as a hobby. I chose a university as the domain because it is a system I know well from the inside.

## The problem

A university's operational database records students, programs, courses, enrollments and exam results. It is designed for day-to-day transactions: registering a student, enrolling them in a course, recording a grade. It is not designed for analysis.

Faculty and administration ask questions such as:

- Which courses have the highest failure rates, and is it the course or the semester?
- How does a student's average grade develop over their studies?
- How long does it take students to graduate in each program?
- Which students show early signs of dropping out?

Answering these directly against the operational database is slow, complicated and risky, since heavy analytical queries compete with daily operations. The standard solution is to move the data into a separate analytical warehouse, modelled specifically for reporting.

## What the project builds

The platform covers the full path from the operational system to a reporting layer.

**1. Operational database (OLTP)**
A normalized PostgreSQL schema (3NF) covering faculties, programs, students, professors, courses, prerequisites, semesters, course offerings, enrollments and exam attempts. Business rules are enforced in the database itself through foreign keys, check constraints and triggers, for example a student cannot enroll in a course without having passed its prerequisites. Schema changes are versioned with migrations.

**2. Synthetic data generator**
Real student data is private, so a Python generator simulates several years of university life: student cohorts, realistic grade distributions, failed exams and re-attempts, program transfers and dropouts. It can also run in a daily mode, producing new activity and updates to existing records, which gives the pipeline real incremental work to do.

**3. Ingestion pipeline**
A Python pipeline extracts new and changed records from the operational database and loads them into the warehouse's raw layer. Loads are incremental (based on change timestamps) and idempotent, so re-running a load never creates duplicates. Every batch is tracked with metadata.

**4. Data warehouse**
Transformations written in SQL with dbt turn raw data into a dimensional model:
- a **star schema** with fact tables for enrollments and exam attempts, and dimensions for students, courses, professors, semesters and dates;
- a **Slowly Changing Dimension (Type 2)** for students, so the history of program changes is preserved rather than overwritten;
- reporting marts for pass rates, grade trends, time to graduation and dropout risk.

**5. Data quality and orchestration**
Automated tests check uniqueness, completeness, referential integrity and business rules at every layer. The whole pipeline runs as a scheduled workflow: generate data, ingest, transform, test.

**6. Dashboard**
A small dashboard presents the key academic metrics to the people who need them.

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────┐
│  Generator   │──▶ │ OLTP (3NF)   │──▶ │  Ingestion   │──▶ │  Warehouse   │──▶ │ Dashboard  │
│  (Python)    │    │ PostgreSQL   │    │  raw layer   │    │  dbt / star  │    │            │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └────────────┘
                         ▲ orchestrated and tested end to end ▲
```

## Key design decisions

- **3NF for the operational side, star schema for the analytical side.** Each model is optimized for its workload: normalization protects data integrity during writes, while a dimensional model makes analytical queries simple and fast.
- **Business rules in the database, not only in code.** Constraints and triggers guarantee consistency no matter which application writes the data.
- **Incremental, idempotent loading.** Production pipelines fail and get re-run, so every load must be safe to repeat.
- **History is preserved.** SCD Type 2 makes it possible to answer questions about the past correctly, for example which program a student belonged to when they took an exam.
- **Everything is reproducible.** The whole platform runs in containers, and generated data is deterministic for a given seed.

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.11+ |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Transformations | dbt |
| Orchestration | Apache Airflow |
| Dashboard | Streamlit |
| Infrastructure | Docker, Docker Compose |
| Quality | pytest, ruff, GitHub Actions |

## Repository structure

```
academic-data-platform/
├── src/academic_platform/   Shared Python package (configuration, database access)
├── db/migrations/           Operational schema migrations
├── docker/init/             Database server initialization (warehouse database and schemas)
├── generator/               Synthetic data generator
├── ingestion/               Operational database to raw layer pipeline
├── dbt/                     Warehouse models and tests
├── orchestration/           Pipeline scheduling
├── dashboard/               Reporting layer
├── docs/                    ERDs and design notes
└── tests/                   Python tests
```

## Roadmap

- [x] Project foundation, containerized database, continuous integration
- [x] Operational schema design (3NF) and migrations
- [x] Synthetic data generator
- [x] Incremental ingestion pipeline
- [x] Warehouse: staging layer, star schema, SCD Type 2
- [ ] Data quality tests
- [ ] Orchestration
- [ ] Dashboard
- [ ] Documentation: ERDs and design notes

## License

MIT
