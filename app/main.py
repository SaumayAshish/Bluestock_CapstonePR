from __future__ import annotations

import hashlib
import base64
import csv
import hmac
import io
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
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator


load_dotenv()

PLAN_LIMITS = {
    "free": {"daily": 5000, "burst": 100},
    "premium": {"daily": 50000, "burst": 500},
    "pro": {"daily": 300000, "burst": 2000},
    "unlimited": {"daily": 1000000, "burst": 5000},
}
PLAN_LIMITS_PER_MINUTE = {plan: limits["burst"] for plan, limits in PLAN_LIMITS.items()}
FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com"}

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
    business_name: str | None = Field(default=None, min_length=2, max_length=255)
    gst_number: str | None = Field(default=None, max_length=32)
    phone: str | None = Field(default=None, max_length=32)
    plan: str = "free"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email address")
        if value.rsplit("@", 1)[1] in FREE_EMAIL_DOMAINS:
            raise ValueError("Business email required")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one letter and one number")
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
    status: str | None = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="Default", min_length=1, max_length=120)


class ApiKeyRotateRequest(BaseModel):
    key_id: int


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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    value = value or utcnow()
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_reset_timestamp() -> int:
    tomorrow = (utcnow() + timedelta(days=1)).date()
    return int(datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc).timestamp())


def today_reset_iso() -> str:
    return iso_utc(datetime.fromtimestamp(today_reset_timestamp(), timezone.utc))


def request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if existing:
        return existing
    generated = "req_" + secrets.token_hex(12)
    request.state.request_id = generated
    return generated


def plan_limits(plan: str) -> dict[str, int]:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def api_success(request: Request, response: Response, data: Any, count: int | None = None) -> dict[str, Any]:
    rate_limit = getattr(request.state, "rate_limit", None)
    response_time_ms = int((time.perf_counter() - getattr(request.state, "start_time", time.perf_counter())) * 1000)
    response.headers["X-Request-ID"] = request_id(request)
    if rate_limit:
        response.headers["X-RateLimit-Limit"] = str(rate_limit["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_limit["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_limit["reset_epoch"])
    return {
        "success": True,
        "count": count if count is not None else (len(data) if isinstance(data, list) else 1),
        "data": data,
        "meta": {
            "requestId": request_id(request),
            "responseTime": response_time_ms,
            "rateLimit": {
                "remaining": rate_limit["remaining"] if rate_limit else None,
                "limit": rate_limit["limit"] if rate_limit else None,
                "reset": rate_limit["reset"] if rate_limit else None,
            },
        },
    }


def api_error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    payload = {
        "success": False,
        "error": {"code": code, "message": message},
        "meta": {
            "requestId": request_id(request),
            "responseTime": getattr(request.state, "response_time_ms", 0),
        },
    }
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Request-ID": request_id(request)})


def dropdown_village(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": f"village_id_{row['id']}",
        "label": row["name"],
        "fullAddress": row["display_name"],
        "hierarchy": {
            "village": row["name"],
            "subDistrict": row["sub_district_name"],
            "district": row["district_name"],
            "state": row["state_name"],
            "country": "India",
        },
    }


def create_api_credentials(client_id: int, name: str = "Default") -> dict[str, str]:
    api_key = f"ak_{secrets.token_hex(16)}"
    api_secret = f"as_{secrets.token_hex(16)}"
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO api_keys (client_id, name, key_prefix, key_hash, secret_hash)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (client_id, name, api_key[:16], sha256(api_key), sha256(api_secret)),
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
        SELECT id, name, email, business_name, gst_number, phone, plan, status, is_active, created_at
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
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
) -> dict[str, Any]:
    key_hash = sha256(x_api_key)
    require_secret = request.method not in {"GET", "HEAD", "OPTIONS"}
    if require_secret and not x_api_secret:
        raise HTTPException(status_code=401, detail="Missing API secret")

    params: list[Any] = [key_hash]
    secret_clause = ""
    if x_api_secret:
        secret_clause = "AND ak.secret_hash = %s"
        params.append(sha256(x_api_secret))
    client = fetch_one(
        f"""
        SELECT
          ak.id AS api_key_id,
          c.id AS client_id,
          c.name,
          c.email,
          c.plan,
          c.status
        FROM api_keys ak
        JOIN api_clients c ON c.id = ak.client_id
        WHERE ak.key_hash = %s
          {secret_clause}
          AND ak.is_active = TRUE
          AND c.is_active = TRUE
          AND c.status = 'active'
        """,
        tuple(params),
    )
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API credentials")

    enforce_rate_limit(client)
    request.state.rate_limit = client.get("rate_limit")
    request.state.client = client
    return client


def enforce_rate_limit(client: dict[str, Any]) -> None:
    limits = plan_limits(client["plan"])
    limit = limits["burst"]
    now = time.time()
    window = rate_windows[int(client["api_key_id"])]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    window.append(now)

    daily = fetch_one(
        """
        SELECT COUNT(*) AS used
        FROM api_usage_events
        WHERE api_key_id = %s AND created_at >= UTC_DATE()
        """,
        (client["api_key_id"],),
    )
    used_today = int(daily["used"] if daily else 0)
    daily_limit = limits["daily"]
    if used_today >= daily_limit:
        raise HTTPException(status_code=429, detail="Daily quota exceeded")
    remaining = max(daily_limit - used_today - 1, 0)
    client["rate_limit"] = {
        "limit": daily_limit,
        "remaining": remaining,
        "reset": today_reset_iso(),
        "reset_epoch": today_reset_timestamp(),
    }


@app.middleware("http")
async def usage_logging(request: Request, call_next):
    start = time.perf_counter()
    request.state.start_time = start
    request.state.request_id = request.headers.get("X-Request-ID") or "req_" + secrets.token_hex(12)
    response: Response
    try:
        response = await call_next(request)
    except Exception:
        response = Response(status_code=500)
        raise
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        request.state.response_time_ms = latency_ms
        client = getattr(request.state, "client", None)
        if client:
            ip_address = request.client.host if request.client else None
            log_usage(client, request.url.path, locals().get("response"), latency_ms, ip_address)
    response.headers["X-Request-ID"] = request_id(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    mapping = {
        400: "INVALID_QUERY",
        401: "INVALID_API_KEY",
        403: "ACCESS_DENIED",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
    }
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return api_error(request, exc.status_code, mapping.get(exc.status_code, "INTERNAL_ERROR"), message)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return api_error(request, 400, "INVALID_QUERY", "Invalid request parameters")


def log_usage(
    client: dict[str, Any],
    endpoint: str,
    response: Response | None,
    latency_ms: int,
    ip_address: str | None,
) -> None:
    status_code = response.status_code if response else 500
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO api_usage_events
              (client_id, api_key_id, endpoint, status_code, latency_ms, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                client["client_id"],
                client["api_key_id"],
                endpoint,
                status_code,
                latency_ms,
                ip_address,
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
    if payload.plan not in PLAN_LIMITS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    with db_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO api_clients
                  (name, email, business_name, gst_number, phone, password_hash, plan, status, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending_approval', TRUE)
                """,
                (
                    payload.name,
                    payload.email,
                    payload.business_name or payload.name,
                    payload.gst_number,
                    payload.phone,
                    password_hash(payload.password),
                    payload.plan,
                ),
            )
            client_id = int(cursor.lastrowid)
            connection.commit()
        except mysql.connector.IntegrityError:
            connection.rollback()
            raise HTTPException(status_code=409, detail="Client email already exists")
        finally:
            cursor.close()

    return {
        "client_id": client_id,
        "status": "pending_approval",
        "token": create_token(str(client_id), "client"),
    }


@app.post("/auth/client-login")
def client_login(payload: LoginRequest) -> dict[str, str]:
    client = fetch_one(
        """
        SELECT id, password_hash
        FROM api_clients
        WHERE email = %s AND is_active = TRUE AND status IN ('pending_approval', 'active')
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
        "plan_limits": plan_limits(client["plan"]),
        "usage": usage,
    }


@app.get("/portal/api-keys")
def portal_api_keys(client: dict[str, Any] = Depends(authenticated_portal_client)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, name, key_prefix, is_active, created_at, last_used_at, expires_at
        FROM api_keys
        WHERE client_id = %s
        ORDER BY created_at DESC
        """,
        (client["id"],),
    )


@app.post("/portal/api-keys")
def portal_create_api_key(
    payload: ApiKeyCreateRequest | None = Body(default=None),
    client: dict[str, Any] = Depends(authenticated_portal_client),
) -> dict[str, str]:
    if client.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account requires admin approval before API key creation")
    active_count = fetch_one(
        "SELECT COUNT(*) AS count FROM api_keys WHERE client_id = %s AND is_active = TRUE",
        (client["id"],),
    )
    if int(active_count["count"] if active_count else 0) >= 5:
        raise HTTPException(status_code=403, detail="Maximum active API keys reached")
    return create_api_credentials(int(client["id"]), payload.name if payload else "Default")


@app.post("/portal/api-keys/{key_id}/rotate-secret")
def portal_rotate_api_key_secret(
    key_id: int,
    client: dict[str, Any] = Depends(authenticated_portal_client),
) -> dict[str, str]:
    api_secret = f"as_{secrets.token_hex(16)}"
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE api_keys
            SET secret_hash = %s
            WHERE id = %s AND client_id = %s AND is_active = TRUE
            """,
            (sha256(api_secret), key_id, client["id"]),
        )
        connection.commit()
        changed = cursor.rowcount
        cursor.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"api_secret": api_secret}


@app.delete("/portal/api-keys/{key_id}")
def portal_revoke_api_key(
    key_id: int,
    client: dict[str, Any] = Depends(authenticated_portal_client),
) -> dict[str, bool]:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE id = %s AND client_id = %s",
            (key_id, client["id"]),
        )
        connection.commit()
        changed = cursor.rowcount
        cursor.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"revoked": True}


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
          c.id, c.name, c.email, c.business_name, c.plan, c.status, c.is_active, c.created_at,
          COUNT(DISTINCT ak.id) AS api_keys,
          COUNT(ue.id) AS total_requests,
          COALESCE(ROUND(AVG(ue.latency_ms)), 0) AS avg_latency_ms
        FROM api_clients c
        LEFT JOIN api_keys ak ON ak.client_id = c.id
        LEFT JOIN api_usage_events ue ON ue.client_id = c.id
        GROUP BY c.id, c.name, c.email, c.business_name, c.plan, c.status, c.is_active, c.created_at
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
        if payload.plan not in PLAN_LIMITS:
            raise HTTPException(status_code=400, detail="Invalid plan")
        updates.append("plan = %s")
        params.append(payload.plan)
    if payload.status is not None:
        if payload.status not in {"pending_approval", "active", "suspended", "rejected"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        updates.append("status = %s")
        params.append(payload.status)
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


@app.post("/admin/clients/{client_id}/approve")
def admin_approve_client(
    client_id: int,
    _: dict[str, Any] = Depends(authenticated_admin),
) -> dict[str, Any]:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE api_clients SET status = 'active', is_active = TRUE WHERE id = %s",
            (client_id,),
        )
        connection.commit()
        changed = cursor.rowcount
        cursor.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"approved": True}


@app.post("/admin/clients/{client_id}/suspend")
def admin_suspend_client(
    client_id: int,
    _: dict[str, Any] = Depends(authenticated_admin),
) -> dict[str, Any]:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE api_clients SET status = 'suspended' WHERE id = %s", (client_id,))
        connection.commit()
        changed = cursor.rowcount
        cursor.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"suspended": True}


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


@app.get("/admin/analytics")
def admin_analytics(_: dict[str, Any] = Depends(authenticated_admin)) -> dict[str, Any]:
    top_states = fetch_all(
        """
        SELECT s.name AS state, COUNT(v.id) AS villages
        FROM states s
        JOIN districts d ON d.state_id = s.id
        JOIN sub_districts sd ON sd.district_id = d.id
        JOIN villages v ON v.sub_district_id = sd.id
        GROUP BY s.id, s.name
        ORDER BY villages DESC
        LIMIT 10
        """
    )
    requests_30d = fetch_all(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS requests
        FROM api_usage_events
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day
        """
    )
    plans = fetch_all(
        "SELECT plan, COUNT(*) AS users FROM api_clients GROUP BY plan ORDER BY users DESC"
    )
    endpoints = fetch_all(
        """
        SELECT endpoint, COUNT(*) AS requests
        FROM api_usage_events
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
        GROUP BY endpoint
        ORDER BY requests DESC
        LIMIT 10
        """
    )
    hourly = fetch_all(
        """
        SELECT HOUR(created_at) AS hour, COUNT(*) AS requests
        FROM api_usage_events
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY HOUR(created_at)
        ORDER BY hour
        """
    )
    response_times = fetch_all(
        """
        SELECT DATE(created_at) AS day, ROUND(AVG(latency_ms)) AS avg_ms, MAX(latency_ms) AS max_ms
        FROM api_usage_events
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day
        """
    )
    return {
        "top_states": top_states,
        "requests_30d": requests_30d,
        "plans": plans,
        "endpoints": endpoints,
        "hourly": hourly,
        "response_times": response_times,
    }


@app.get("/admin/villages")
def admin_villages(
    state_id: int,
    district_id: int | None = None,
    sub_district_id: int | None = None,
    q: str | None = Query(default=None, min_length=2),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=500, ge=1, le=10000),
    _: dict[str, Any] = Depends(authenticated_admin),
) -> dict[str, Any]:
    conditions = ["s.id = %s"]
    params: list[Any] = [state_id]
    if district_id:
        conditions.append("d.id = %s")
        params.append(district_id)
    if sub_district_id:
        conditions.append("sd.id = %s")
        params.append(sub_district_id)
    if q:
        conditions.append("v.search_name LIKE %s")
        params.append(f"%{q.lower()}%")
    where = " AND ".join(conditions)
    count = fetch_one(
        f"""
        SELECT COUNT(*) AS count
        FROM villages v
        JOIN sub_districts sd ON sd.id = v.sub_district_id
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        WHERE {where}
        """,
        tuple(params),
    )
    rows = fetch_all(
        f"""
        SELECT
          s.name AS state_name,
          d.name AS district_name,
          sd.name AS sub_district_name,
          v.code AS village_code,
          v.name AS village_name
        FROM villages v
        JOIN sub_districts sd ON sd.id = v.sub_district_id
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        WHERE {where}
        ORDER BY d.name, sd.name, v.name
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, (page - 1) * limit]),
    )
    return {"count": count["count"] if count else 0, "page": page, "limit": limit, "data": rows}


@app.get("/admin/api-logs")
def admin_api_logs(
    status_class: str | None = Query(default=None, pattern="^(2xx|4xx|5xx)$"),
    endpoint: str | None = None,
    client_id: int | None = None,
    min_response_time: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    _: dict[str, Any] = Depends(authenticated_admin),
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    if status_class:
        conditions.append("ue.status_code BETWEEN %s AND %s")
        start = int(status_class[0]) * 100
        params.extend([start, start + 99])
    if endpoint:
        conditions.append("ue.endpoint = %s")
        params.append(endpoint)
    if client_id:
        conditions.append("ue.client_id = %s")
        params.append(client_id)
    if min_response_time is not None:
        conditions.append("ue.latency_ms >= %s")
        params.append(min_response_time)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = fetch_all(
        f"""
        SELECT
          ue.created_at,
          ak.key_prefix,
          c.name AS client_name,
          c.business_name,
          ue.endpoint,
          ue.latency_ms AS response_time_ms,
          ue.status_code,
          CONCAT(SUBSTRING(COALESCE(ue.ip_address, ''), 1, 7), '***') AS masked_ip
        FROM api_usage_events ue
        JOIN api_clients c ON c.id = ue.client_id
        JOIN api_keys ak ON ak.id = ue.api_key_id
        {where}
        ORDER BY ue.created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    for row in rows:
        row["api_key"] = row.pop("key_prefix") + "****"
    return rows


@app.get("/admin/api-logs/export.csv")
def admin_api_logs_csv(_: dict[str, Any] = Depends(authenticated_admin)) -> Response:
    rows = fetch_all(
        """
        SELECT
          ue.created_at,
          CONCAT(ak.key_prefix, '****') AS api_key,
          c.name AS client_name,
          c.business_name,
          ue.endpoint,
          ue.latency_ms AS response_time_ms,
          ue.status_code,
          CONCAT(SUBSTRING(COALESCE(ue.ip_address, ''), 1, 7), '***') AS masked_ip
        FROM api_usage_events ue
        JOIN api_clients c ON c.id = ue.client_id
        JOIN api_keys ak ON ak.id = ue.api_key_id
        ORDER BY ue.created_at DESC
        LIMIT 1000
        """
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()) if rows else ["created_at"])
    writer.writeheader()
    writer.writerows(rows)
    return Response(content=buffer.getvalue(), media_type="text/csv")


@app.get("/v1/states")
def states(
    request: Request,
    response: Response,
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT id, code, name
        FROM states
        ORDER BY name
        """
    )
    return api_success(request, response, rows)


@app.get("/v1/districts")
def districts(
    request: Request,
    response: Response,
    state_id: int | None = None,
    state_code: str | None = None,
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if state_id:
        conditions.append("s.id = %s")
        params.append(state_id)
    if state_code:
        conditions.append("s.code = %s")
        params.append(state_code)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = fetch_all(
        f"""
        SELECT d.id, d.code, d.name, s.id AS state_id, s.code AS state_code, s.name AS state_name
        FROM districts d
        JOIN states s ON s.id = d.state_id
        {where}
        ORDER BY s.name, d.name
        """,
        tuple(params),
    )
    return api_success(request, response, rows)


@app.get("/v1/states/{state_id}/districts")
def districts_by_state(
    state_id: int,
    request: Request,
    response: Response,
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT d.id, d.code, d.name, s.id AS state_id, s.code AS state_code, s.name AS state_name
        FROM districts d
        JOIN states s ON s.id = d.state_id
        WHERE s.id = %s
        ORDER BY d.name
        """,
        (state_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="State or districts not found")
    return api_success(request, response, rows)


@app.get("/v1/sub-districts")
def sub_districts(
    request: Request,
    response: Response,
    district_id: int | None = None,
    district_code: str | None = None,
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if district_id:
        conditions.append("d.id = %s")
        params.append(district_id)
    if district_code:
        conditions.append("d.code = %s")
        params.append(district_code)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = fetch_all(
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
    return api_success(request, response, rows)


@app.get("/v1/districts/{district_id}/subdistricts")
def subdistricts_by_district(
    district_id: int,
    request: Request,
    response: Response,
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
          sd.id, sd.code, sd.name,
          d.id AS district_id, d.code AS district_code, d.name AS district_name,
          s.id AS state_id, s.code AS state_code, s.name AS state_name
        FROM sub_districts sd
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        WHERE d.id = %s
        ORDER BY sd.name
        """,
        (district_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="District or sub-districts not found")
    return api_success(request, response, rows)


@app.get("/v1/villages")
def villages(
    request: Request,
    response: Response,
    sub_district_id: int | None = None,
    q: str | None = Query(default=None, min_length=2),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
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
    rows = fetch_all(
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
    return api_success(request, response, [dropdown_village(row) for row in rows])


@app.get("/v1/subdistricts/{sub_district_id}/villages")
def villages_by_subdistrict(
    sub_district_id: int,
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=10000),
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    offset = (page - 1) * limit
    rows = fetch_all(
        """
        SELECT
          v.id, v.code, v.name, v.display_name,
          sd.id AS sub_district_id, sd.name AS sub_district_name,
          d.id AS district_id, d.name AS district_name,
          s.id AS state_id, s.name AS state_name
        FROM villages v
        JOIN sub_districts sd ON sd.id = v.sub_district_id
        JOIN districts d ON d.id = sd.district_id
        JOIN states s ON s.id = d.state_id
        WHERE v.sub_district_id = %s
        ORDER BY v.name
        LIMIT %s OFFSET %s
        """,
        (sub_district_id, limit, offset),
    )
    return api_success(request, response, [dropdown_village(row) for row in rows])


@app.get("/v1/autocomplete")
def autocomplete(
    request: Request,
    response: Response,
    q: str = Query(min_length=2),
    hierarchyLevel: str = "village",
    state_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    if hierarchyLevel != "village":
        raise HTTPException(status_code=400, detail="Only village autocomplete is currently supported")
    conditions = ["v.search_name LIKE %s"]
    params: list[Any] = [f"{q.lower()}%"]
    if state_id:
        conditions.append("s.id = %s")
        params.append(state_id)
    params.append(limit)
    rows = fetch_all(
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
    return api_success(request, response, [dropdown_village(row) for row in rows])


@app.get("/v1/search")
def search(
    request: Request,
    response: Response,
    q: str = Query(min_length=2),
    state: str | None = None,
    district: str | None = None,
    subDistrict: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    _: dict[str, Any] = Depends(authenticated_client),
) -> dict[str, Any]:
    like = f"%{q.lower()}%"
    conditions = ["v.search_name LIKE %s"]
    params: list[Any] = [like]
    if state:
        conditions.append("(s.code = %s OR s.search_name = %s)")
        params.extend([state, state.lower()])
    if district:
        conditions.append("(d.code = %s OR d.search_name = %s)")
        params.extend([district, district.lower()])
    if subDistrict:
        conditions.append("(sd.code = %s OR sd.search_name = %s)")
        params.extend([subDistrict, subDistrict.lower()])
    params.extend([f"{q.lower()}%", limit])
    rows = fetch_all(
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
        ORDER BY
          CASE WHEN v.search_name LIKE %s THEN 0 ELSE 1 END,
          v.name
        LIMIT %s
        """,
        tuple(params),
    )
    return api_success(request, response, [dropdown_village(row) for row in rows])


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
    async function register(){{let body={{name:rname.value,email:remail.value,business_name:rname.value,password:rpass.value,plan:rplan.value}};let r=await fetch('/auth/register',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});let d=await r.json();if(!r.ok){{alert(d.detail||'Registration failed');return}}token=d.token;localStorage.setItem('clientToken',token);newkey.innerHTML=`<p>Account status: ${{d.status}}. API keys are available after admin approval.</p>`;load();}}
    async function login(){{let r=await fetch('/auth/client-login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:lemail.value,password:lpass.value}})}});let d=await r.json();if(!r.ok){{alert(d.detail||'Login failed');return}}token=d.token;localStorage.setItem('clientToken',token);load();}}
    async function newKey(){{let d=await authed('/portal/api-keys',{{method:'POST'}});newkey.innerHTML=`<p>New credentials:</p><div class="secret">X-API-Key: ${{d.api_key}}<br>X-API-Secret: ${{d.api_secret}}</div>`;load();}}
    async function load(){{let me=await authed('/portal/me');account.innerHTML=`<div class="metric">Client<b>${{me.client.name}}</b></div><div class="metric">Status<b>${{me.client.status}}</b></div><div class="metric">Daily Limit<b>${{me.plan_limits.daily}}</b></div><div class="metric">24h Requests<b>${{me.usage.requests_24h}}</b></div>`;let k=await authed('/portal/api-keys');keys.innerHTML=k.map(x=>`<tr><td>${{x.id}}</td><td>${{x.key_prefix}}</td><td>${{x.is_active}}</td><td>${{x.last_used_at||''}}</td></tr>`).join('');let u=await authed('/portal/usage');usage.innerHTML=u.endpoints.map(x=>`<tr><td>${{x.endpoint}}</td><td>${{x.requests}}</td><td>${{x.avg_latency_ms}} ms</td></tr>`).join('');}}
    if(token)load().catch(()=>{{}});
    </script></body></html>
    """
