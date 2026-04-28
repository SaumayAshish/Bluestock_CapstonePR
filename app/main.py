from __future__ import annotations

import hashlib
import base64
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator


load_dotenv()

PLAN_LIMITS_PER_MINUTE = {
    "free": 60,
    "premium": 600,
    "pro": 3000,
    "unlimited": 100000,
}

rate_windows: dict[int, deque[float]] = defaultdict(deque)
connection_pool: pooling.MySQLConnectionPool | None = None

app = FastAPI(
    title="BlueStock Geography API",
    version="0.1.0",
    description="Village-level India geography API backed by normalized MySQL data.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    plan: str = "free"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email address")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email address")
        return value


class AdminClientUpdate(BaseModel):
    plan: str | None = None
    is_active: bool | None = None


def mysql_config() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "bluestock"),
    }


@contextmanager
def db_connection():
    global connection_pool
    if connection_pool is None:
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="bluestock_api_pool",
            pool_size=int(os.getenv("MYSQL_POOL_SIZE", "10")),
            **mysql_config(),
        )
    connection = connection_pool.get_connection()
    try:
        yield connection
    finally:
        connection.close()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 120000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def jwt_secret() -> bytes:
    return os.getenv("APP_JWT_SECRET", "local-dev-secret-change-before-production").encode("utf-8")


def create_token(subject: str, role: str, expires_hours: int = 12) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=expires_hours)).timestamp()),
    }
    signing_input = (
        b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    signature = hmac.new(jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + b64url_encode(signature)


def decode_token(token: str, expected_role: str) -> dict[str, Any]:
    try:
        signing_input, signature = token.rsplit(".", 1)
        expected = hmac.new(jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url_decode(signature), expected):
            raise ValueError
        payload = json.loads(b64url_decode(signing_input.split(".", 1)[1]))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("role") != expected_role:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


def fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows


def fetch_one(query: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = fetch_all(query, params)
    return rows[0] if rows else None


def create_api_credentials(client_id: int) -> dict[str, str]:
    api_key = f"bs_{secrets.token_urlsafe(24)}"
    api_secret = secrets.token_urlsafe(40)
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO api_keys (client_id, key_prefix, key_hash, secret_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (client_id, api_key[:16], sha256(api_key), sha256(api_secret)),
        )
        connection.commit()
        cursor.close()
    return {"api_key": api_key, "api_secret": api_secret}


def authenticated_admin(authorization: str | None = Header(default=None, alias="Authorization")) -> dict[str, Any]:
    payload = decode_token(bearer_token(authorization), "admin")
    admin = fetch_one(
        "SELECT id, name, email FROM admin_users WHERE id = %s AND is_active = TRUE",
        (int(payload["sub"]),),
    )
    if not admin:
        raise HTTPException(status_code=401, detail="Admin user is inactive")
    return admin


def authenticated_portal_client(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    payload = decode_token(bearer_token(authorization), "client")
    client = fetch_one(
        """
        SELECT id, name, email, plan, is_active, created_at
        FROM api_clients
        WHERE id = %s AND is_active = TRUE
        """,
        (int(payload["sub"]),),
    )
    if not client:
        raise HTTPException(status_code=401, detail="Client is inactive")
    return client


def authenticated_client(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_api_secret: str = Header(..., alias="X-API-Secret"),
) -> dict[str, Any]:
    key_hash = sha256(x_api_key)
    secret_hash = sha256(x_api_secret)
    client = fetch_one(
        """
        SELECT
          ak.id AS api_key_id,
          c.id AS client_id,
          c.name,
          c.email,
          c.plan
        FROM api_keys ak
        JOIN api_clients c ON c.id = ak.client_id
        WHERE ak.key_hash = %s
          AND ak.secret_hash = %s
          AND ak.is_active = TRUE
          AND c.is_active = TRUE
        """,
        (key_hash, secret_hash),
    )
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API credentials")

    enforce_rate_limit(client)
    request.state.client = client
    return client


def enforce_rate_limit(client: dict[str, Any]) -> None:
    limit = PLAN_LIMITS_PER_MINUTE.get(client["plan"], PLAN_LIMITS_PER_MINUTE["free"])
    now = time.time()
    window = rate_windows[int(client["api_key_id"])]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    window.append(now)


@app.middleware("http")
async def usage_logging(request: Request, call_next):
    start = time.perf_counter()
    response: Response
    try:
        response = await call_next(request)
    except Exception:
        response = Response(status_code=500)
        raise
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        client = getattr(request.state, "client", None)
        if client:
            log_usage(client, request.url.path, locals().get("response"), latency_ms)
    return response


def log_usage(client: dict[str, Any], endpoint: str, response: Response | None, latency_ms: int) -> None:
    status_code = response.status_code if response else 500
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO api_usage_events
              (client_id, api_key_id, endpoint, status_code, latency_ms)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                client["client_id"],
                client["api_key_id"],
                endpoint,
                status_code,
                latency_ms,
            ),
        )
        cursor.execute(
            "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = %s",
            (client["api_key_id"],),
        )
        connection.commit()
        cursor.close()


@app.get("/health")
def health() -> dict[str, Any]:
    row = fetch_one("SELECT COUNT(*) AS villages FROM villages")
    return {"status": "ok", "villages": row["villages"] if row else 0}


@app.post("/auth/register")
def register_client(payload: RegisterRequest) -> dict[str, Any]:
    if payload.plan not in PLAN_LIMITS_PER_MINUTE:
        raise HTTPException(status_code=400, detail="Invalid plan")

    with db_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO api_clients (name, email, password_hash, plan)
                VALUES (%s, %s, %s, %s)
                """,
                (payload.name, payload.email, password_hash(payload.password), payload.plan),
            )
            client_id = int(cursor.lastrowid)
            connection.commit()
        except mysql.connector.IntegrityError:
            connection.rollback()
            raise HTTPException(status_code=409, detail="Client email already exists")
        finally:
            cursor.close()

    credentials = create_api_credentials(client_id)
    return {
        "client_id": client_id,
        "token": create_token(str(client_id), "client"),
        **credentials,
    }


@app.post("/auth/client-login")
def client_login(payload: LoginRequest) -> dict[str, str]:
    client = fetch_one(
        """
        SELECT id, password_hash
        FROM api_clients
        WHERE email = %s AND is_active = TRUE
        """,
        (payload.email,),
    )
    if not client or not verify_password(payload.password, client["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid login")
    return {"token": create_token(str(client["id"]), "client")}


@app.post("/admin/login")
def admin_login(payload: LoginRequest) -> dict[str, str]:
    admin = fetch_one(
        """
        SELECT id, password_hash
        FROM admin_users
        WHERE email = %s AND is_active = TRUE
        """,
        (payload.email,),
    )
    if not admin or not verify_password(payload.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid admin login")
    return {"token": create_token(str(admin["id"]), "admin")}


@app.get("/portal/me")
def portal_me(client: dict[str, Any] = Depends(authenticated_portal_client)) -> dict[str, Any]:
    usage = fetch_one(
        """
        SELECT
          COUNT(*) AS requests_24h,
          COALESCE(ROUND(AVG(latency_ms)), 0) AS avg_latency_ms
        FROM api_usage_events
        WHERE client_id = %s
          AND created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)
        """,
        (client["id"],),
    )
    return {
        "client": client,
        "plan_limit_per_minute": PLAN_LIMITS_PER_MINUTE.get(client["plan"], PLAN_LIMITS_PER_MINUTE["free"]),
        "usage": usage,
    }


@app.get("/portal/api-keys")
def portal_api_keys(client: dict[str, Any] = Depends(authenticated_portal_client)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, key_prefix, is_active, created_at, last_used_at
        FROM api_keys
        WHERE client_id = %s
        ORDER BY created_at DESC
        """,
        (client["id"],),
    )


@app.post("/portal/api-keys")
def portal_create_api_key(client: dict[str, Any] = Depends(authenticated_portal_client)) -> dict[str, str]:
    return create_api_credentials(int(client["id"]))


@app.get("/portal/usage")
def portal_usage(client: dict[str, Any] = Depends(authenticated_portal_client)) -> dict[str, Any]:
    daily = fetch_all(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS requests, ROUND(AVG(latency_ms)) AS avg_latency_ms
        FROM api_usage_events
        WHERE client_id = %s
          AND created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day DESC
        """,
        (client["id"],),
    )
    endpoints = fetch_all(
        """
        SELECT endpoint, COUNT(*) AS requests, ROUND(AVG(latency_ms)) AS avg_latency_ms
        FROM api_usage_events
        WHERE client_id = %s
        GROUP BY endpoint
        ORDER BY requests DESC
        LIMIT 10
        """,
        (client["id"],),
    )
    return {"daily": daily, "endpoints": endpoints}


@app.get("/admin/summary")
def admin_summary(_: dict[str, Any] = Depends(authenticated_admin)) -> dict[str, Any]:
    counts = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM api_clients) AS clients,
          (SELECT COUNT(*) FROM api_keys) AS api_keys,
          (SELECT COUNT(*) FROM api_usage_events WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)) AS requests_24h,
          (SELECT COALESCE(ROUND(AVG(latency_ms)), 0) FROM api_usage_events WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)) AS avg_latency_ms,
          (SELECT COUNT(*) FROM states) AS states,
          (SELECT COUNT(*) FROM districts) AS districts,
          (SELECT COUNT(*) FROM sub_districts) AS sub_districts,
          (SELECT COUNT(*) FROM villages) AS villages
        """
    )
    plan_rows = fetch_all(
        "SELECT plan, COUNT(*) AS clients FROM api_clients GROUP BY plan ORDER BY clients DESC"
    )
    return {"summary": counts, "plans": plan_rows}


@app.get("/admin/clients")
def admin_clients(_: dict[str, Any] = Depends(authenticated_admin)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
          c.id, c.name, c.email, c.plan, c.is_active, c.created_at,
          COUNT(DISTINCT ak.id) AS api_keys,
          COUNT(ue.id) AS total_requests,
          COALESCE(ROUND(AVG(ue.latency_ms)), 0) AS avg_latency_ms
        FROM api_clients c
        LEFT JOIN api_keys ak ON ak.client_id = c.id
        LEFT JOIN api_usage_events ue ON ue.client_id = c.id
        GROUP BY c.id, c.name, c.email, c.plan, c.is_active, c.created_at
        ORDER BY c.created_at DESC
        """
    )


@app.patch("/admin/clients/{client_id}")
def admin_update_client(
    client_id: int,
    payload: AdminClientUpdate,
    _: dict[str, Any] = Depends(authenticated_admin),
) -> dict[str, Any]:
    updates = []
    params: list[Any] = []
    if payload.plan is not None:
        if payload.plan not in PLAN_LIMITS_PER_MINUTE:
            raise HTTPException(status_code=400, detail="Invalid plan")
        updates.append("plan = %s")
        params.append(payload.plan)
    if payload.is_active is not None:
        updates.append("is_active = %s")
        params.append(payload.is_active)
    if not updates:
        raise HTTPException(status_code=400, detail="No changes supplied")

    params.append(client_id)
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(f"UPDATE api_clients SET {', '.join(updates)} WHERE id = %s", tuple(params))
        connection.commit()
        changed = cursor.rowcount
        cursor.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"updated": True}


@app.get("/admin/usage")
def admin_usage(_: dict[str, Any] = Depends(authenticated_admin)) -> dict[str, Any]:
    daily = fetch_all(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS requests, ROUND(AVG(latency_ms)) AS avg_latency_ms
        FROM api_usage_events
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day DESC
        """
    )
    endpoints = fetch_all(
        """
        SELECT endpoint, COUNT(*) AS requests, ROUND(AVG(latency_ms)) AS avg_latency_ms
        FROM api_usage_events
        GROUP BY endpoint
        ORDER BY requests DESC
        LIMIT 10
        """
    )
    return {"daily": daily, "endpoints": endpoints}


@app.get("/v1/states")
def states(_: dict[str, Any] = Depends(authenticated_client)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, code, name
        FROM states
        ORDER BY name
        """
    )


@app.get("/v1/districts")
def districts(
    state_id: int | None = None,
    state_code: str | None = None,
    _: dict[str, Any] = Depends(authenticated_client),
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    if state_id:
        conditions.append("s.id = %s")
        params.append(state_id)
    if state_code:
        conditions.append("s.code = %s")
        params.append(state_code)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return fetch_all(
        f"""
        SELECT d.id, d.code, d.name, s.id AS state_id, s.code AS state_code, s.name AS state_name
        FROM districts d
        JOIN states s ON s.id = d.state_id
        {where}
        ORDER BY s.name, d.name
        """,
        tuple(params),
    )


@app.get("/v1/sub-districts")
def sub_districts(
    district_id: int | None = None,
    district_code: str | None = None,
    _: dict[str, Any] = Depends(authenticated_client),
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    if district_id:
        conditions.append("d.id = %s")
        params.append(district_id)
    if district_code:
        conditions.append("d.code = %s")
        params.append(district_code)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return fetch_all(
        f"""
        SELECT
          sd.id, sd.code, sd.name,
          d.id AS district_id, d.code AS district_code, d.name AS district_name,
          s.id AS state_id, s.code AS state_code, s.name AS state_name
        FROM sub_districts sd
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        {where}
        ORDER BY s.name, d.name, sd.name
        """,
        tuple(params),
    )


@app.get("/v1/villages")
def villages(
    sub_district_id: int | None = None,
    q: str | None = Query(default=None, min_length=2),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: dict[str, Any] = Depends(authenticated_client),
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    if sub_district_id:
        conditions.append("v.sub_district_id = %s")
        params.append(sub_district_id)
    if q:
        conditions.append("v.search_name LIKE %s")
        params.append(f"{q.lower()}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])
    return fetch_all(
        f"""
        SELECT
          v.id, v.code, v.name, v.display_name,
          sd.id AS sub_district_id, sd.name AS sub_district_name,
          d.id AS district_id, d.name AS district_name,
          s.id AS state_id, s.name AS state_name
        FROM villages v
        JOIN sub_districts sd ON sd.id = v.sub_district_id
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        {where}
        ORDER BY v.name
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )


@app.get("/v1/autocomplete")
def autocomplete(
    q: str = Query(min_length=2),
    state_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    _: dict[str, Any] = Depends(authenticated_client),
) -> list[dict[str, Any]]:
    conditions = ["v.search_name LIKE %s"]
    params: list[Any] = [f"{q.lower()}%"]
    if state_id:
        conditions.append("s.id = %s")
        params.append(state_id)
    params.append(limit)
    return fetch_all(
        f"""
        SELECT
          v.id, v.name, v.display_name,
          sd.name AS sub_district_name,
          d.name AS district_name,
          s.name AS state_name
        FROM villages v
        JOIN sub_districts sd ON sd.id = v.sub_district_id
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        WHERE {' AND '.join(conditions)}
        ORDER BY v.name
        LIMIT %s
        """,
        tuple(params),
    )


@app.get("/v1/search")
def search(
    q: str = Query(min_length=2),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict[str, Any] = Depends(authenticated_client),
) -> list[dict[str, Any]]:
    like = f"%{q.lower()}%"
    return fetch_all(
        """
        SELECT
          v.id, v.name, v.display_name,
          sd.name AS sub_district_name,
          d.name AS district_name,
          s.name AS state_name
        FROM villages v
        JOIN sub_districts sd ON sd.id = v.sub_district_id
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        WHERE v.search_name LIKE %s
        ORDER BY
          CASE WHEN v.search_name LIKE %s THEN 0 ELSE 1 END,
          v.name
        LIMIT %s
        """,
        (like, f"{q.lower()}%", limit),
    )


DASHBOARD_CSS = """
body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#f6f8fb;color:#172033}
header{background:#101828;color:white;padding:18px 28px;display:flex;justify-content:space-between;align-items:center}
main{max-width:1180px;margin:0 auto;padding:24px}
section{background:white;border:1px solid #e4e7ec;border-radius:8px;padding:18px;margin-bottom:18px}
h1,h2{margin:0 0 14px}label{display:block;font-size:13px;font-weight:600;margin:10px 0 4px}
input,select{width:100%;box-sizing:border-box;padding:10px;border:1px solid #ccd3df;border-radius:6px}
button{background:#155eef;color:white;border:0;border-radius:6px;padding:10px 14px;font-weight:700;cursor:pointer}
button.secondary{background:#344054}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.metric{border:1px solid #e4e7ec;border-radius:8px;padding:14px;background:#fcfcfd}.metric b{display:block;font-size:24px;margin-top:4px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #eaecf0;padding:10px;font-size:14px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.muted{color:#667085}.secret{font-family:Consolas,monospace;background:#f2f4f7;padding:8px;border-radius:6px;overflow:auto}
"""


@app.get("/", response_class=HTMLResponse)
def home_page() -> str:
    return f"""
    <!doctype html><html><head><title>BlueStock API</title><style>{DASHBOARD_CSS}</style></head>
    <body><header><h1>BlueStock Geography API</h1><nav><a style="color:white" href="/admin">Admin</a> &nbsp; <a style="color:white" href="/portal">Client Portal</a> &nbsp; <a style="color:white" href="/docs">API Docs</a></nav></header>
    <main><section><h2>Local SaaS Backend</h2><p class="muted">MySQL-backed village-level geography API with API-key authentication, client management, and usage analytics.</p>
    <div class="grid" id="health"></div></section></main>
    <script>
    fetch('/health').then(r=>r.json()).then(d=>health.innerHTML=`<div class="metric">Status<b>${{d.status}}</b></div><div class="metric">Villages<b>${{d.villages.toLocaleString()}}</b></div>`);
    </script></body></html>
    """


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> str:
    return f"""
    <!doctype html><html><head><title>BlueStock Admin</title><style>{DASHBOARD_CSS}</style></head>
    <body><header><h1>Admin Dashboard</h1><a style="color:white" href="/docs">API Docs</a></header><main>
    <section id="login"><h2>Admin Login</h2><div class="row"><div><label>Email</label><input id="email" value="{os.getenv('ADMIN_EMAIL','admin@bluestock.local')}"></div><div><label>Password</label><input id="password" type="password"></div></div><br><button onclick="login()">Login</button></section>
    <section><h2>Platform Summary</h2><div class="grid" id="summary"></div></section>
    <section><h2>Clients</h2><table><thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Plan</th><th>Active</th><th>Keys</th><th>Requests</th></tr></thead><tbody id="clients"></tbody></table></section>
    </main><script>
    let token=localStorage.getItem('adminToken')||'';
    async function api(path,opts={{}}){{opts.headers={{...(opts.headers||{{}}),Authorization:'Bearer '+token,'Content-Type':'application/json'}};let r=await fetch(path,opts);if(!r.ok)throw new Error(await r.text());return r.json();}}
    async function login(){{let r=await fetch('/admin/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email.value,password:password.value}})}});let d=await r.json();if(!r.ok){{alert(d.detail||'Login failed');return}}token=d.token;localStorage.setItem('adminToken',token);load();}}
    async function load(){{let s=await api('/admin/summary');summary.innerHTML=Object.entries(s.summary).map(([k,v])=>`<div class="metric">${{k.replaceAll('_',' ')}}<b>${{Number(v).toLocaleString()}}</b></div>`).join('');let c=await api('/admin/clients');clients.innerHTML=c.map(x=>`<tr><td>${{x.id}}</td><td>${{x.name}}</td><td>${{x.email}}</td><td>${{x.plan}}</td><td>${{x.is_active}}</td><td>${{x.api_keys}}</td><td>${{x.total_requests}}</td></tr>`).join('');}}
    if(token)load().catch(()=>{{}});
    </script></body></html>
    """


@app.get("/portal", response_class=HTMLResponse)
def portal_page() -> str:
    return f"""
    <!doctype html><html><head><title>BlueStock Portal</title><style>{DASHBOARD_CSS}</style></head>
    <body><header><h1>Client Portal</h1><a style="color:white" href="/docs">API Docs</a></header><main>
    <section><h2>Register</h2><div class="row"><div><label>Name</label><input id="rname"></div><div><label>Email</label><input id="remail"></div><div><label>Password</label><input id="rpass" type="password"></div><div><label>Plan</label><select id="rplan"><option>free</option><option>premium</option><option>pro</option><option>unlimited</option></select></div></div><br><button onclick="register()">Register</button></section>
    <section><h2>Login</h2><div class="row"><div><label>Email</label><input id="lemail"></div><div><label>Password</label><input id="lpass" type="password"></div></div><br><button onclick="login()">Login</button></section>
    <section><h2>Account</h2><div class="grid" id="account"></div><br><button class="secondary" onclick="newKey()">Create API Key</button><div id="newkey"></div></section>
    <section><h2>API Keys</h2><table><thead><tr><th>ID</th><th>Prefix</th><th>Active</th><th>Last Used</th></tr></thead><tbody id="keys"></tbody></table></section>
    <section><h2>Usage</h2><table><thead><tr><th>Endpoint</th><th>Requests</th><th>Avg Latency</th></tr></thead><tbody id="usage"></tbody></table></section>
    </main><script>
    let token=localStorage.getItem('clientToken')||'';
    async function authed(path,opts={{}}){{opts.headers={{...(opts.headers||{{}}),Authorization:'Bearer '+token,'Content-Type':'application/json'}};let r=await fetch(path,opts);if(!r.ok)throw new Error(await r.text());return r.json();}}
    async function register(){{let body={{name:rname.value,email:remail.value,password:rpass.value,plan:rplan.value}};let r=await fetch('/auth/register',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});let d=await r.json();if(!r.ok){{alert(d.detail||'Registration failed');return}}token=d.token;localStorage.setItem('clientToken',token);newkey.innerHTML=`<p>New credentials:</p><div class="secret">X-API-Key: ${{d.api_key}}<br>X-API-Secret: ${{d.api_secret}}</div>`;load();}}
    async function login(){{let r=await fetch('/auth/client-login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:lemail.value,password:lpass.value}})}});let d=await r.json();if(!r.ok){{alert(d.detail||'Login failed');return}}token=d.token;localStorage.setItem('clientToken',token);load();}}
    async function newKey(){{let d=await authed('/portal/api-keys',{{method:'POST'}});newkey.innerHTML=`<p>New credentials:</p><div class="secret">X-API-Key: ${{d.api_key}}<br>X-API-Secret: ${{d.api_secret}}</div>`;load();}}
    async function load(){{let me=await authed('/portal/me');account.innerHTML=`<div class="metric">Client<b>${{me.client.name}}</b></div><div class="metric">Plan<b>${{me.client.plan}}</b></div><div class="metric">Limit/min<b>${{me.plan_limit_per_minute}}</b></div><div class="metric">24h Requests<b>${{me.usage.requests_24h}}</b></div>`;let k=await authed('/portal/api-keys');keys.innerHTML=k.map(x=>`<tr><td>${{x.id}}</td><td>${{x.key_prefix}}</td><td>${{x.is_active}}</td><td>${{x.last_used_at||''}}</td></tr>`).join('');let u=await authed('/portal/usage');usage.innerHTML=u.endpoints.map(x=>`<tr><td>${{x.endpoint}}</td><td>${{x.requests}}</td><td>${{x.avg_latency_ms}} ms</td></tr>`).join('');}}
    if(token)load().catch(()=>{{}});
    </script></body></html>
    """
