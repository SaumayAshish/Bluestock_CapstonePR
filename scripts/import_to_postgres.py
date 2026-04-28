from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import execute_values

SUPPORTED_EXTENSIONS = {".xls", ".xlsx", ".ods"}
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS import_files (
      id BIGSERIAL PRIMARY KEY,
      file_name VARCHAR(255) NOT NULL,
      file_path VARCHAR(768) NOT NULL,
      state_code VARCHAR(8) NULL,
      state_name VARCHAR(255) NULL,
      file_extension VARCHAR(16) NOT NULL,
      imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (file_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_rows (
      id BIGSERIAL PRIMARY KEY,
      import_file_id BIGINT NOT NULL REFERENCES import_files (id) ON DELETE CASCADE,
      sheet_name VARCHAR(255) NOT NULL,
      source_row_number INTEGER NOT NULL,
      row_hash CHAR(64) NOT NULL,
      row_data JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (import_file_id, sheet_name, source_row_number)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_import_rows_hash ON import_rows (row_hash)
    """,
]


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(path)


def postgres_config_from_env() -> PostgresConfig:
    return PostgresConfig(
        dsn=os.getenv(
            "DATABASE_URL",
            "postgresql://bluestock:bluestock@127.0.0.1:5432/bluestock",
        )
    )


def connect_postgres(config: PostgresConfig):
    return psycopg2.connect(config.dsn)


def ensure_database(config: PostgresConfig) -> None:
    return None


def ensure_schema(connection) -> None:
    with connection.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
    connection.commit()


def dataset_files(dataset_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in dataset_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def parse_state_from_filename(path: Path) -> tuple[str | None, str | None]:
    match = re.match(r"Rdir_2011_(\d+)_([^.]+)", path.stem, re.IGNORECASE)
    if not match:
        return None, None

    state_code = match.group(1)
    state_name = match.group(2).replace("_and_", " and ").replace("_", " ").title()
    return state_code, state_name


def clean_value(value):
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: pandas. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def row_hash(row_data: dict) -> str:
    payload = json.dumps(row_data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_workbook(path: Path) -> Iterable[tuple[str, list[tuple[int, dict]]]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: pandas. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    engine = "odf" if path.suffix.lower() == ".ods" else None
    workbook = pd.read_excel(path, sheet_name=None, header=None, engine=engine)

    for sheet_name, frame in workbook.items():
        if frame.empty:
            continue

        rows: list[tuple[int, dict]] = []
        for frame_index, values in frame.iterrows():
            row_data = {
                f"column_{index + 1}": clean_value(value)
                for index, value in enumerate(values.tolist())
            }
            if all(value is None or value == "" for value in row_data.values()):
                continue
            rows.append((int(frame_index) + 1, row_data))

        yield str(sheet_name), rows


def upsert_import_file(connection, path: Path, dataset_dir: Path) -> int:
    state_code, state_name = parse_state_from_filename(path)
    relative_path = path.relative_to(dataset_dir.parent).as_posix()

    sql = """
        INSERT INTO import_files
          (file_name, file_path, state_code, state_name, file_extension)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (file_path) DO UPDATE SET
          file_name = EXCLUDED.file_name,
          state_code = EXCLUDED.state_code,
          state_name = EXCLUDED.state_name,
          file_extension = EXCLUDED.file_extension
        RETURNING id
    """
    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (
                path.name,
                relative_path,
                state_code,
                state_name,
                path.suffix.lower().lstrip("."),
            ),
        )
        return int(cursor.fetchone()[0])


def replace_existing_rows(connection, import_file_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM import_rows WHERE import_file_id = %s", (import_file_id,))


def batched(items: list[tuple], batch_size: int) -> Iterable[list[tuple]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def insert_rows(connection, rows: list[tuple], batch_size: int) -> int:
    if not rows:
        return 0

    sql = """
        INSERT INTO import_rows
          (import_file_id, sheet_name, source_row_number, row_hash, row_data)
        VALUES %s
        ON CONFLICT (import_file_id, sheet_name, source_row_number) DO UPDATE SET
          row_hash = EXCLUDED.row_hash,
          row_data = EXCLUDED.row_data
    """
    inserted = 0
    with connection.cursor() as cursor:
        for batch in batched(rows, batch_size):
            execute_values(cursor, sql, batch)
            inserted += len(batch)
    return inserted


def import_file(connection, path: Path, dataset_dir: Path, batch_size: int, replace: bool) -> int:
    import_file_id = upsert_import_file(connection, path, dataset_dir)
    if replace:
        replace_existing_rows(connection, import_file_id)

    postgres_rows = []
    for sheet_name, rows in read_workbook(path):
        for row_number, row_data in rows:
            postgres_rows.append(
                (
                    import_file_id,
                    sheet_name,
                    row_number,
                    row_hash(row_data),
                    json.dumps(row_data, ensure_ascii=False, default=str),
                )
            )

    imported = insert_rows(connection, postgres_rows, batch_size)
    connection.commit()
    return imported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import BlueStock spreadsheets into PostgreSQL.")
    parser.add_argument(
        "--dataset-dir",
        default=None,
        help="Directory containing .xls, .xlsx, and .ods files.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to a dotenv file containing DATABASE_URL.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Number of rows to insert per database batch.",
    )
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="Create required PostgreSQL tables before importing.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing rows for each file before importing it again.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))

    dataset_dir = Path(args.dataset_dir or os.getenv("DATASET_DIR", "dataset")).resolve()
    batch_size = args.batch_size or int(os.getenv("IMPORT_BATCH_SIZE", "1000"))
    if not dataset_dir.exists():
        raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")

    files = dataset_files(dataset_dir)
    if not files:
        raise SystemExit(f"No supported spreadsheet files found in: {dataset_dir}")

    postgres_config = postgres_config_from_env()
    if args.create_schema:
        ensure_database(postgres_config)

    connection = connect_postgres(postgres_config)
    try:
        if args.create_schema:
            ensure_schema(connection)

        total_rows = 0
        for path in files:
            imported = import_file(
                connection=connection,
                path=path,
                dataset_dir=dataset_dir,
                batch_size=batch_size,
                replace=args.replace,
            )
            total_rows += imported
            print(f"{path.name}: {imported} rows")

        print(f"Imported {total_rows} rows from {len(files)} files.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
