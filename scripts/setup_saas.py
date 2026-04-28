from __future__ import annotations

import os
from pathlib import Path

from create_api_client import sha256
from import_to_postgres import connect_postgres, load_env_file, postgres_config_from_env
from normalize_geography import execute_sql_file


def password_hash(password: str) -> str:
    import base64
    import hashlib
    import secrets

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return "pbkdf2_sha256$120000$" + base64.urlsafe_b64encode(salt).decode("ascii") + "$" + base64.urlsafe_b64encode(digest).decode("ascii")


def column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table, column),
    )
    return cursor.fetchone()[0] > 0


def main() -> None:
    load_env_file(Path(".env"))
    connection = connect_postgres(postgres_config_from_env())
    try:
        execute_sql_file(connection, Path("sql/postgres_schema.sql"))
        with connection.cursor() as cursor:
            api_client_columns = (
                ("business_name", "ALTER TABLE api_clients ADD COLUMN business_name VARCHAR(255)"),
                ("gst_number", "ALTER TABLE api_clients ADD COLUMN gst_number VARCHAR(32)"),
                ("phone", "ALTER TABLE api_clients ADD COLUMN phone VARCHAR(32)"),
                ("password_hash", "ALTER TABLE api_clients ADD COLUMN password_hash VARCHAR(255)"),
                ("status", "ALTER TABLE api_clients ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active'"),
            )
            for column, statement in api_client_columns:
                if not column_exists(cursor, "api_clients", column):
                    cursor.execute(statement)
            if not column_exists(cursor, "api_keys", "name"):
                cursor.execute("ALTER TABLE api_keys ADD COLUMN name VARCHAR(120) NOT NULL DEFAULT 'Default'")
            if not column_exists(cursor, "api_keys", "expires_at"):
                cursor.execute("ALTER TABLE api_keys ADD COLUMN expires_at TIMESTAMPTZ")
            if not column_exists(cursor, "api_usage_events", "ip_address"):
                cursor.execute("ALTER TABLE api_usage_events ADD COLUMN ip_address VARCHAR(64)")
            cursor.execute("UPDATE api_clients SET status = 'active' WHERE status IS NULL OR status = ''")

            admin_email = os.getenv("ADMIN_EMAIL", "admin@bluestock.local")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin12345")
            cursor.execute(
                """
                INSERT INTO admin_users (name, email, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                  password_hash = EXCLUDED.password_hash,
                  is_active = TRUE
                """,
                ("BlueStock Admin", admin_email, password_hash(admin_password)),
            )
        connection.commit()
        print(f"Admin user ready: {os.getenv('ADMIN_EMAIL', 'admin@bluestock.local')}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
