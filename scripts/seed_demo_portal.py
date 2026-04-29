from __future__ import annotations

import argparse
import random
import secrets
from datetime import date, datetime, time, timedelta
from pathlib import Path

from create_api_client import sha256
from import_to_postgres import connect_postgres, load_env_file, postgres_config_from_env
from normalize_geography import execute_sql_file
from setup_saas import password_hash


DEMO_EMAIL = "demo@bluestock.local"
DEMO_PASSWORD = "Demo12345"


def create_key(cursor, client_id: int, name: str, active: bool = True) -> tuple[int, str, str]:
    api_key = f"ak_{secrets.token_hex(16)}"
    api_secret = f"as_{secrets.token_hex(16)}"
    cursor.execute(
        """
        INSERT INTO api_keys (client_id, name, key_prefix, key_hash, secret_hash, is_active, last_used_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP - INTERVAL '2 hours')
        RETURNING id
        """,
        (client_id, name, api_key[:16], sha256(api_key), sha256(api_secret), active),
    )
    return int(cursor.fetchone()[0]), api_key, api_secret


def seed_usage(cursor, client_id: int, key_id: int) -> None:
    endpoints = [
        ("/v1/search", 42, 86),
        ("/v1/autocomplete", 28, 54),
        ("/v1/villages", 18, 112),
        ("/v1/states", 7, 38),
        ("/v1/districts", 5, 64),
    ]
    today = date.today()
    random.seed(20260429)
    for days_ago in range(13, -1, -1):
        day = today - timedelta(days=days_ago)
        trend = 1 + ((13 - days_ago) * 0.045)
        weekday_boost = 1.12 if day.weekday() < 5 else 0.78
        for endpoint, base_count, base_latency in endpoints:
            count = max(1, int(base_count * trend * weekday_boost + random.randint(-3, 5)))
            for index in range(count):
                created_at = datetime.combine(day, time(hour=9 + (index % 9), minute=(index * 7) % 60))
                latency = max(24, int(base_latency + random.randint(-18, 28)))
                cursor.execute(
                    """
                    INSERT INTO api_usage_events
                      (client_id, api_key_id, endpoint, status_code, latency_ms, ip_address, created_at)
                    VALUES (%s, %s, %s, 200, %s, 'demo-seed', %s)
                    """,
                    (client_id, key_id, endpoint, latency, created_at),
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed an approved demo B2B portal account with usage analytics.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    connection = connect_postgres(postgres_config_from_env())
    try:
        execute_sql_file(connection, Path("sql/postgres_schema.sql"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_clients
                  (name, email, business_name, gst_number, phone, password_hash, plan, status, is_active)
                VALUES
                  (%s, %s, %s, %s, %s, %s, 'unlimited', 'active', TRUE)
                ON CONFLICT (email) DO UPDATE SET
                  name = EXCLUDED.name,
                  business_name = EXCLUDED.business_name,
                  gst_number = EXCLUDED.gst_number,
                  phone = EXCLUDED.phone,
                  password_hash = EXCLUDED.password_hash,
                  plan = 'unlimited',
                  status = 'active',
                  is_active = TRUE
                RETURNING id
                """,
                (
                    "BlueStock Demo Buyer",
                    args.email,
                    "BlueStock Demo Analytics Pvt Ltd",
                    "29ABCDE1234F1Z5",
                    "+91 98765 43210",
                    password_hash(args.password),
                ),
            )
            client_id = int(cursor.fetchone()[0])
            cursor.execute(
                "DELETE FROM api_usage_events WHERE client_id = %s",
                (client_id,),
            )
            cursor.execute("DELETE FROM api_keys WHERE client_id = %s", (client_id,))
            active_key_id, api_key, api_secret = create_key(cursor, client_id, "Production demo key", True)
            create_key(cursor, client_id, "Revoked legacy key", False)
            seed_usage(cursor, client_id, active_key_id)
        connection.commit()
        print(f"Demo portal login: {args.email} / {args.password}")
        print(f"Seeded API key: {api_key}")
        print(f"Seeded API secret: {api_secret}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
