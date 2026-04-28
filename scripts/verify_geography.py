from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from psycopg2.extras import RealDictCursor

from import_to_postgres import connect_postgres, load_env_file, postgres_config_from_env


def fetch_one(cursor, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    cursor.execute(query, params)
    row = cursor.fetchone()
    return row or {}


def fetch_all(cursor, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return list(cursor.fetchall())


def print_section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def run_checks(connection, fail_on_warnings: bool) -> int:
    exit_code = 0
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    try:
        print_section("Row counts")
        for table in ("countries", "states", "districts", "sub_districts", "villages"):
            count = fetch_one(cursor, f"SELECT COUNT(*) AS count FROM {table}")["count"]
            print(f"{table}: {count}")

        print_section("Orphan checks")
        orphan_queries = {
            "states_without_country": """
                SELECT COUNT(*) AS count
                FROM states s
                LEFT JOIN countries c ON c.id = s.country_id
                WHERE c.id IS NULL
            """,
            "districts_without_state": """
                SELECT COUNT(*) AS count
                FROM districts d
                LEFT JOIN states s ON s.id = d.state_id
                WHERE s.id IS NULL
            """,
            "sub_districts_without_district": """
                SELECT COUNT(*) AS count
                FROM sub_districts sd
                LEFT JOIN districts d ON d.id = sd.district_id
                WHERE d.id IS NULL
            """,
            "villages_without_sub_district": """
                SELECT COUNT(*) AS count
                FROM villages v
                LEFT JOIN sub_districts sd ON sd.id = v.sub_district_id
                WHERE sd.id IS NULL
            """,
        }
        for name, query in orphan_queries.items():
            count = fetch_one(cursor, query)["count"]
            print(f"{name}: {count}")
            if count:
                exit_code = 1

        print_section("Duplicate code checks")
        duplicate_queries = {
            "state_codes": """
                SELECT code, COUNT(*) AS count
                FROM states
                GROUP BY code
                HAVING COUNT(*) > 1
                LIMIT 10
            """,
            "district_codes_within_state": """
                SELECT state_id, code, COUNT(*) AS count
                FROM districts
                GROUP BY state_id, code
                HAVING COUNT(*) > 1
                LIMIT 10
            """,
            "sub_district_codes_within_district": """
                SELECT district_id, code, COUNT(*) AS count
                FROM sub_districts
                GROUP BY district_id, code
                HAVING COUNT(*) > 1
                LIMIT 10
            """,
            "village_codes_within_sub_district": """
                SELECT sub_district_id, code, COUNT(*) AS count
                FROM villages
                GROUP BY sub_district_id, code
                HAVING COUNT(*) > 1
                LIMIT 10
            """,
        }
        for name, query in duplicate_queries.items():
            rows = fetch_all(cursor, query)
            print(f"{name}: {len(rows)}")
            for row in rows:
                print(f"  {row}")
            if rows:
                exit_code = 1

        print_section("Sample hierarchy check")
        sample_rows = fetch_all(
            cursor,
            """
            SELECT
              s.code AS state_code,
              s.name AS state_name,
              d.code AS district_code,
              d.name AS district_name,
              sd.code AS sub_district_code,
              sd.name AS sub_district_name,
              v.code AS village_code,
              v.name AS village_name
            FROM villages v
            JOIN sub_districts sd ON sd.id = v.sub_district_id
            JOIN districts d ON d.id = sd.district_id
            JOIN states s ON s.id = d.state_id
            WHERE s.code = '27'
              AND d.code = '497'
              AND sd.code = '03950'
              AND v.code IN ('525002', '525003', '525004', '525005')
            ORDER BY v.code
            """,
        )
        if sample_rows:
            for row in sample_rows:
                print(
                    f"{row['state_name']} > {row['district_name']} > "
                    f"{row['sub_district_name']} > {row['village_name']} ({row['village_code']})"
                )
        else:
            message = "No rows found for Maharashtra/Nandurbar/Akkalkuwa sample."
            print(message)
            if fail_on_warnings:
                exit_code = 1

        return exit_code
    finally:
        cursor.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify normalized BlueStock geography tables.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return a non-zero exit code when optional sample checks have no matches.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))
    try:
        connection = connect_postgres(postgres_config_from_env())
    except Exception as exc:
        raise SystemExit(
            "Could not connect to PostgreSQL. Start the database with "
            "`docker compose up -d postgres` or update DATABASE_URL in `.env`. "
            f"Original error: {exc}"
        ) from exc
    try:
        raise SystemExit(run_checks(connection, args.fail_on_warnings))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
