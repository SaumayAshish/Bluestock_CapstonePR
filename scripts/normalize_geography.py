from __future__ import annotations

import argparse
from pathlib import Path

from import_to_postgres import connect_postgres, load_env_file, postgres_config_from_env


GEOGRAPHY_SCHEMA = Path("sql/postgres_schema.sql")


def execute_sql_file(connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    connection.commit()


def normalize_name_sql(expression: str) -> str:
    return f"LOWER(TRIM({expression}))"


def transform(connection, replace: bool) -> None:
    with connection.cursor() as cursor:
        if replace:
            cursor.execute(
                "TRUNCATE TABLE "
                + ", ".join(
                    (
                        "api_usage_events",
                        "user_state_access",
                        "api_keys",
                        "api_clients",
                        "villages",
                        "sub_districts",
                        "districts",
                        "states",
                        "countries",
                    )
                )
                + " RESTART IDENTITY CASCADE"
            )

        cursor.execute(
            """
            INSERT INTO countries (code, name)
            VALUES ('IN', 'India')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            """
        )

        cursor.execute(
            """
            INSERT INTO states (country_id, code, name, search_name)
            SELECT c.id, raw.state_code, raw.state_name, LOWER(raw.state_name)
            FROM (
              SELECT DISTINCT
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) AS state_code,
                TRIM(JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_2'))) AS state_name
              FROM import_rows r
              WHERE JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) REGEXP '^[0-9]+$'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3')) = '000'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5')) = '00000'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7')) = '000000'
            ) raw
            JOIN countries c ON c.code = 'IN'
            WHERE raw.state_code <> '00' AND raw.state_name <> ''
            ON CONFLICT (code) DO UPDATE SET
              name = EXCLUDED.name,
              search_name = EXCLUDED.search_name
            """
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1'))", "r.row_data ->> 'column_1'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_2'))", "r.row_data ->> 'column_2'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3'))", "r.row_data ->> 'column_3'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5'))", "r.row_data ->> 'column_5'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7'))", "r.row_data ->> 'column_7'")
            .replace(" REGEXP ", " ~ ")
        )

        cursor.execute(
            """
            INSERT INTO districts (state_id, code, name, search_name)
            SELECT s.id, raw.district_code, raw.district_name, LOWER(raw.district_name)
            FROM (
              SELECT DISTINCT
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) AS state_code,
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3')) AS district_code,
                TRIM(JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_4'))) AS district_name
              FROM import_rows r
              WHERE JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) REGEXP '^[0-9]+$'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3')) <> '000'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5')) = '00000'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7')) = '000000'
            ) raw
            JOIN states s ON s.code = raw.state_code
            WHERE raw.district_name <> ''
            ON CONFLICT (state_id, code) DO UPDATE SET
              name = EXCLUDED.name,
              search_name = EXCLUDED.search_name
            """
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1'))", "r.row_data ->> 'column_1'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3'))", "r.row_data ->> 'column_3'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_4'))", "r.row_data ->> 'column_4'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5'))", "r.row_data ->> 'column_5'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7'))", "r.row_data ->> 'column_7'")
            .replace(" REGEXP ", " ~ ")
        )

        cursor.execute(
            """
            INSERT INTO sub_districts (district_id, code, name, search_name)
            SELECT d.id, raw.sub_district_code, raw.sub_district_name, LOWER(raw.sub_district_name)
            FROM (
              SELECT DISTINCT
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) AS state_code,
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3')) AS district_code,
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5')) AS sub_district_code,
                TRIM(JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_6'))) AS sub_district_name
              FROM import_rows r
              WHERE JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) REGEXP '^[0-9]+$'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3')) <> '000'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5')) <> '00000'
                AND JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7')) = '000000'
            ) raw
            JOIN states s ON s.code = raw.state_code
            JOIN districts d ON d.state_id = s.id AND d.code = raw.district_code
            WHERE raw.sub_district_name <> ''
            ON CONFLICT (district_id, code) DO UPDATE SET
              name = EXCLUDED.name,
              search_name = EXCLUDED.search_name
            """
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1'))", "r.row_data ->> 'column_1'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3'))", "r.row_data ->> 'column_3'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5'))", "r.row_data ->> 'column_5'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_6'))", "r.row_data ->> 'column_6'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7'))", "r.row_data ->> 'column_7'")
            .replace(" REGEXP ", " ~ ")
        )

        cursor.execute(
            """
            INSERT INTO villages (sub_district_id, code, name, display_name, search_name)
            SELECT
              sd.id,
              raw.village_code,
              raw.village_name,
              CONCAT(raw.village_name, ', ', sd.name, ', ', d.name, ', ', s.name, ', India'),
              LOWER(raw.village_name)
            FROM (
              SELECT DISTINCT
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1')) AS state_code,
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3')) AS district_code,
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5')) AS sub_district_code,
                JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7')) AS village_code,
                TRIM(REGEXP_REPLACE(r.row_data ->> 'column_8', '[[:space:]]*\\([0-9]+\\)[[:space:]]*$', '')) AS village_name
              FROM import_rows r
              WHERE r.row_data ->> 'column_1' ~ '^[0-9]+$'
                AND r.row_data ->> 'column_3' <> '000'
                AND r.row_data ->> 'column_5' <> '00000'
                AND r.row_data ->> 'column_7' <> '000000'
            ) raw
            JOIN states s ON s.code = raw.state_code
            JOIN districts d ON d.state_id = s.id AND d.code = raw.district_code
            JOIN sub_districts sd ON sd.district_id = d.id AND sd.code = raw.sub_district_code
            WHERE raw.village_name <> ''
            ON CONFLICT (sub_district_id, code) DO UPDATE SET
              name = EXCLUDED.name,
              display_name = EXCLUDED.display_name,
              search_name = EXCLUDED.search_name
            """
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_1'))", "r.row_data ->> 'column_1'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_3'))", "r.row_data ->> 'column_3'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_5'))", "r.row_data ->> 'column_5'")
            .replace("JSON_UNQUOTE(JSON_EXTRACT(r.row_data, '$.column_7'))", "r.row_data ->> 'column_7'")
        )
    connection.commit()


def print_counts(connection) -> None:
    with connection.cursor() as cursor:
        for table in ("countries", "states", "districts", "sub_districts", "villages"):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"{table}: {cursor.fetchone()[0]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize imported geography rows into API tables.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))
    connection = connect_postgres(postgres_config_from_env())
    try:
        if args.create_schema:
            execute_sql_file(connection, GEOGRAPHY_SCHEMA)
        transform(connection, replace=args.replace)
        print_counts(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
