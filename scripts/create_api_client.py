from __future__ import annotations

import argparse
import hashlib
import secrets
from pathlib import Path

from import_to_mysql import connect_mysql, load_env_file, mysql_config_from_env
from normalize_geography import execute_sql_file


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_client(name: str, email: str, plan: str) -> tuple[str, str]:
    api_key = f"ak_{secrets.token_hex(16)}"
    api_secret = f"as_{secrets.token_hex(16)}"
    connection = connect_mysql(mysql_config_from_env())
    try:
        execute_sql_file(connection, Path("sql/geography_schema.sql"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_clients (name, email, business_name, plan, status)
                VALUES (%s, %s, %s, %s, 'active')
                ON DUPLICATE KEY UPDATE
                  name = VALUES(name),
                  business_name = VALUES(business_name),
                  plan = VALUES(plan),
                  status = 'active',
                  is_active = TRUE,
                  id = LAST_INSERT_ID(id)
                """,
                (name, email, name, plan),
            )
            client_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO api_keys (client_id, name, key_prefix, key_hash, secret_hash)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (client_id, "Default", api_key[:16], sha256(api_key), sha256(api_secret)),
            )
        connection.commit()
    finally:
        connection.close()
    return api_key, api_secret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a BlueStock API client and credentials.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--name", default="Local Development Client")
    parser.add_argument("--email", default="dev@example.com")
    parser.add_argument("--plan", choices=["free", "premium", "pro", "unlimited"], default="unlimited")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))
    api_key, api_secret = create_client(args.name, args.email, args.plan)
    print(f"X-API-Key: {api_key}")
    print(f"X-API-Secret: {api_secret}")


if __name__ == "__main__":
    main()
