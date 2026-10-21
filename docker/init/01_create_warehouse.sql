-- Runs once, on first start of an empty data volume, as POSTGRES_USER.
\getenv warehouse_db WAREHOUSE_DB

CREATE DATABASE :"warehouse_db";

\connect :"warehouse_db"

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS meta;
