"""Copy selected legacy SQLite tables into an empty PostgreSQL schema.

UNSAFE for authenticated tenant data: this script does not copy tenants or
memberships and does not map record ownership. Do not apply it to such data
until tenant/membership migration and explicit ownership mapping are implemented.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import SQLAlchemyError

from api.database import (
    assessments,
    business_profiles,
    create_engine_for_url,
    documents,
)
from config import DATABASE_URL


TABLES = (business_profiles, documents, assessments)
BATCH_SIZE = 250


def _arguments():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Do not use --apply for authenticated tenant data until tenant and "
            "membership migration plus explicit ownership mapping are implemented."
        ),
    )
    parser.add_argument(
        "--sqlite-path",
        required=True,
        type=Path,
        help="Path to the source SQLite file (opened read-only).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy rows. Without this flag, only validate and report counts.",
    )
    return parser.parse_args()


def _open_source(path):
    if not path.is_file():
        raise FileNotFoundError("The source SQLite database file does not exist.")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    missing = {table.name for table in TABLES} - names
    if missing:
        connection.close()
        raise RuntimeError(
            "The SQLite source is missing required tables: "
            + ", ".join(sorted(missing))
        )
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        connection.close()
        raise RuntimeError("The SQLite source has foreign-key violations.")
    return connection


def _source_counts(connection):
    return {
        table.name: connection.execute(
            f'SELECT COUNT(*) FROM "{table.name}"'
        ).fetchone()[0]
        for table in TABLES
    }


def _destination_counts(connection):
    return {
        table.name: connection.execute(
            select(func.count()).select_from(table)
        ).scalar_one()
        for table in TABLES
    }


def _copy_rows(source, destination):
    for table in TABLES:
        cursor = source.execute(
            f'SELECT * FROM "{table.name}" ORDER BY id'
        )
        while True:
            batch = cursor.fetchmany(BATCH_SIZE)
            if not batch:
                break
            destination.execute(
                insert(table),
                [dict(row) for row in batch],
            )


def _reset_sequences(connection):
    for table in TABLES:
        connection.execute(
            text(
                "SELECT setval("
                "pg_get_serial_sequence(:table_name, 'id'), "
                f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) "
                f'FROM "{table.name}"'
            ),
            {"table_name": table.name},
        )


def migrate(sqlite_path, database_url, apply):
    source = _open_source(sqlite_path)
    try:
        expected = _source_counts(source)
        engine = create_engine_for_url(database_url)
        try:
            with engine.begin() as destination:
                actual = _destination_counts(destination)
                if any(actual.values()):
                    raise RuntimeError(
                        "The PostgreSQL destination is not empty; migration requires "
                        "an empty target and no rows were copied."
                    )

                if apply:
                    _copy_rows(source, destination)
                    _reset_sequences(destination)
                    copied = _destination_counts(destination)
                    if copied != expected:
                        raise RuntimeError(
                            "Post-copy row counts did not match; the transaction was rolled back."
                        )
        finally:
            engine.dispose()
    finally:
        source.close()

    for table in TABLES:
        print(f"{table.name}: {expected[table.name]} rows")
    if apply:
        print("Migration completed and row counts verified.")
    else:
        print("Dry run only. No PostgreSQL rows were changed.")


def main():
    args = _arguments()
    if not DATABASE_URL:
        print("Set DATABASE_URL to the PostgreSQL destination.", file=sys.stderr)
        return 2
    try:
        migrate(args.sqlite_path, DATABASE_URL, args.apply)
    except SQLAlchemyError as error:
        print(
            f"PostgreSQL operation failed ({type(error).__name__}); "
            "no migration was confirmed.",
            file=sys.stderr,
        )
        return 2
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
