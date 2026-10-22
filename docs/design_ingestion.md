# Ingestion design

The ingestion pipeline copies the operational database `university` into the raw layer of the analytical database `warehouse`. It is the extract-and-load step between two systems. The source is only ever read; all transformation happens later, in dbt.

```
university.public.<table>  ──COPY──▶  temporary _stage  ──INSERT … ON CONFLICT DO NOTHING──▶  warehouse.raw.<table>
                           ──COPY──▶  temporary _source_keys  ──flag missing keys──▶  raw.<table>._is_deleted
```

## What is ingested

Every base table in the source schema `public` that has a single-column primary key and an `updated_at` column. That is the twelve operational tables. Other tables are never read:
- `alembic_version` has neither column.
- The simulation clock lives in the `sim` schema, which is not scanned at all.

`--tables` can narrow a run to a subset. A name outside this set, such as `clock`, is rejected before anything runs.

## Raw tables

`raw.<table>` is created on first use from the source column metadata in `information_schema.columns`, so the raw layer never needs a hand-written migration.

| Column | Meaning |
|---|---|
| `_raw_id` | Surrogate key of the raw row |
| every source column | Same name and type, always nullable |
| `_batch_id` | The `meta.load_batches` row that inserted this version |
| `_loaded_at` | When the version was loaded |
| `_source_updated_at` | The source `updated_at` of this version |
| `_is_deleted`, `_deleted_at` | Set when the source row has disappeared |

**Raw is append-only.** Every version of a source row is kept: a student who changed city three times has four rows, one per `updated_at`. That history is what dbt later uses to build the Type 2 dimensions. The only in-place change is the delete flag described below.

**Source columns are nullable in raw**, even where the source declares `NOT NULL`. A column that is later dropped from the source then simply stays empty in new versions, instead of breaking the load.

## Meta tables

The pipeline creates both meta tables idempotently at the start of every run.

**`meta.load_batches`** has one row per table per run:
- the table name, the mode and the status (`running`, `succeeded` or `failed`);
- start and end times, and the watermark before and after;
- rows extracted, inserted, skipped as duplicates, and keys flagged as deleted;
- the error message of a failed run.

**`meta.watermarks`** holds one row per table: the highest source `updated_at` loaded so far.

## Incremental extraction and the overlap window

An incremental run reads the rows whose `updated_at` is newer than the table's watermark minus an overlap window (10 minutes by default, `--overlap-minutes`). The new watermark is the highest `updated_at` among the rows read, so it reflects source time, not the clock of the machine running the pipeline.

**Why the overlap is needed.** `updated_at` is set by a trigger to `now()`, which is the start time of the writing transaction, not its commit time. Consider this sequence:
1. A transaction starts at 10:00:00 and updates a row, stamping it `10:00:00`.
2. Before it commits, ingestion runs at 10:00:05. It cannot see the uncommitted row, and it advances the watermark to rows stamped 10:00:04 by other transactions.
3. The long transaction commits at 10:00:30.

The row is now visible, but its `updated_at` is older than the watermark, so a plain `updated_at > watermark` query would skip it forever. Re-reading a window before the watermark catches any transaction shorter than the window. A transaction that stays open longer than the window can still be missed; a periodic full run is the safety net (see Limits).

**Why re-reading is harmless.** Raw has a unique constraint on (source key, `_source_updated_at`), and new rows are inserted with `ON CONFLICT DO NOTHING`. A version that is read twice is skipped and counted as a duplicate. The same holds when a whole run is repeated, or when a failed run is retried. Re-running any window never creates duplicates.

## Full mode

Full mode reads every source row without a watermark filter. It is used for the initial load and for recovery, for example after a missed window or a restored raw table.

Full mode does not truncate raw: versions that were already loaded are skipped, missing ones are added, and the history of older versions is preserved. The watermark is then moved to the newest `updated_at` in the source.

## Deletes

Deletes cannot be seen through `updated_at`: a deleted row simply stops existing. Every run, incremental or full, therefore also compares keys:
1. All primary keys of the source table are copied into a temporary table.
2. Raw rows whose key is missing from the source, and that are not yet flagged, get `_is_deleted = true` and `_deleted_at = now()`. All versions of the key are flagged.

The source is never changed by ingestion. The rows and the keys are read in the same `REPEATABLE READ` snapshot, so a row inserted between the two reads cannot be mistaken for a delete.

Comparing keys costs one key scan per table per run. For `enrollments`, about 450,000 keys, that is a few seconds, which is acceptable here. At larger scale, or with tighter latency targets, this would be replaced by change data capture: PostgreSQL logical replication, or Debezium reading the write-ahead log. CDC delivers inserts, updates and deletes as events, as they happen, without scanning.

## Transactions and failure handling

Each table is loaded in its own warehouse transaction:
1. A `running` batch row is written in a separate, immediately committed transaction, so that a failure can always be recorded against it.
2. In one warehouse transaction: create or align the raw table, stream the changed rows into a temporary staging table with `COPY`, insert new versions into raw, flag deletes, save the watermark and mark the batch `succeeded`. Everything commits together or not at all.
3. If anything fails, that transaction rolls back. Raw and the watermark are untouched, the batch is marked `failed` with the error message, and the next run starts again from the old watermark. One failing table does not stop the others, and the command exits with status 1.

**Transient connection errors** (`psycopg.OperationalError`) are retried up to three times with exponential backoff: 1 s, then 2 s. Other errors, such as schema drift, fail the batch at once, because retrying would not help.

**Data never passes through Python objects.** It is streamed block by block from `COPY ... TO STDOUT` on the source into `COPY ... FROM STDIN` on the warehouse, so memory use does not grow with table size.

## Schema drift

Before each load, the source columns are compared with the raw table:

| Source change | Effect on raw |
|---|---|
| New column | Added to raw automatically with the same type. Older versions have `NULL` in it. |
| Dropped column | Kept in raw; new versions have `NULL`. |
| Changed type | The batch fails with an error naming the column and both types. A type change needs a decision, for example to cast, to keep both columns or to rebuild raw, so it is not applied silently. |

## Logging

Each table produces one structured log line:

```
table=enrollments mode=incremental status=succeeded batch=16 extracted=29297 inserted=0 duplicates=29297 deleted=0 watermark=2026-10-22T12:41:47+00:00 attempts=1 seconds=10.54
```

A summary line follows for the whole run. The same numbers are stored in `meta.load_batches`.

## Measured load times

Measured on a laptop with PostgreSQL in Docker Desktop, with the default history (15,000 students, 8 years) plus 30 simulated days:

| Run | Rows read | Rows inserted | Keys flagged deleted | Time |
|---|---|---|---|---|
| Full, all 12 tables | 1,053,275 | 1,053,275 | 0 | 66 s |
| Incremental after 30 more simulated days | 34,916 | 109 | 10 | 27 s |

In the incremental run, almost all of the time goes to the key comparison for deletes: 10 s for `enrollments` and 14 s for `exam_attempts`. Reading the changed rows takes well under a second. The 34,916 rows read are mostly rows already loaded, re-read inside the overlap window (see Limits).

## Limits

- **Long transactions.** A source transaction that stays open longer than the overlap window can commit rows behind the watermark. A periodic full run, which is idempotent, picks them up.
- **Deletes need a key scan of every table** on every run (see Deletes).
- **Source row versions between two runs are not visible.** A row updated twice between runs arrives as one version in raw. Only CDC would capture every intermediate state.
- **Quiet tables are re-read.** The watermark only moves when a table changes. A table that has not changed since its watermark was set keeps its newest rows inside the overlap window, so every incremental run reads them again and skips them as duplicates. This is cheap for small tables and bounded by the window for large ones.
- **Concurrent runs.** Concurrent runs of the pipeline are not coordinated. Orchestration is expected to run one ingestion at a time.
- **Hard deletes with key reuse.** A key that is deleted and later reused would be flagged as deleted and then appear again as a new version. Identity keys are never reused by the source, so this does not happen here.

## Possible improvements

- **Run delete detection less often, or only for tables that allow deletes.** In the operational model only `enrollments` can lose rows: every other table is protected by `ON DELETE RESTRICT` or never has rows removed. Scanning keys for `enrollments` only, or for all tables once a day instead of every run, would remove most of the incremental run time.
- **Change data capture.** Logical replication or Debezium would replace both the watermark query and the key scan, and would also capture every intermediate version of a row.
