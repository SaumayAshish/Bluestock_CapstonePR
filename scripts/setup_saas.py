from __future__ import annotations

import os
from pathlib import Path

from create_api_client import sha256
from import_to_mysql import connect_mysql, load_env_file, mysql_config_from_env
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
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
        """,
        (table, column),
    )
    return cursor.fetchone()[0] > 0


def main() -> None:
    load_env_file(Path(".env"))
    connection = connect_mysql(mysql_config_from_env())
    try:
        execute_sql_file(connection, Path("sql/geography_schema.sql"))
        with connection.cursor() as cursor:
            if not column_exists(cursor, "api_clients", "password_hash"):
                cursor.execute("ALTER TABLE api_clients ADD COLUMN password_hash VARCHAR(255) NULL AFTER email")

            admin_email = os.getenv("ADMIN_EMAIL", "admin@bluestock.local")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin12345")
            cursor.execute(
                """
                INSERT INTO admin_users (name, email, password_hash)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  password_hash = VALUES(password_hash),
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
