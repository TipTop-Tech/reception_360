import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from loguru import logger

from bot import run_bot

DB_PATH = Path(__file__).with_name("reception360.db")
SESSION_COOKIE = "reception360_session"
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24 hours

app = FastAPI()


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                organization TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "name" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN name TEXT DEFAULT ''")
        conn.execute(
            """
            UPDATE users
            SET name = CASE
                WHEN TRIM(COALESCE(name, '')) = '' THEN
                    TRIM(
                        REPLACE(
                            REPLACE(
                                SUBSTR(email, 1, COALESCE(NULLIF(INSTR(email, '@'), 0), LENGTH(email)) ),
                                '.',
                                ' '
                            ),
                            '_',
                            ' '
                        )
                    )
                ELSE name
            END
            WHERE TRIM(COALESCE(name, '')) = ''
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL,
                caller_name TEXT,
                phone TEXT,
                outcome TEXT,
                duration_seconds INTEGER,
                transcript TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    ).hex()
    return salt, password_hash


def create_user_record(name: str, organization: str, email: str, password: str, role: str) -> dict:
    salt, password_hash = hash_password(password)
    full_name = (name or email).strip()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (name, organization, email, role, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (full_name, organization.strip(), email.strip().lower(), role.strip(), salt, password_hash, int(time.time())),
        )
        conn.commit()
    return {"name": full_name, "organization": organization.strip(), "email": email.strip().lower(), "role": role.strip()}


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with get_db_connection() as conn:
        return conn.execute(
            "SELECT name, organization, email, role, password_salt, password_hash FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    _, candidate_hash = hash_password(password, salt)
    return secrets.compare_digest(candidate_hash, stored_hash)


def create_session(email: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, email, role, expires_at) VALUES (?, ?, ?, ?)",
            (token, email.lower(), role, expires_at),
        )
        conn.commit()
    return token


def log_call_event(direction: str, caller_name: str | None, phone: str | None, outcome: str, duration_seconds: int = 0, transcript: str | None = None) -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO call_logs (direction, caller_name, phone, outcome, duration_seconds, transcript, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                direction,
                caller_name or "Unknown caller",
                phone or "Unknown",
                outcome,
                duration_seconds,
                transcript or "",
                int(time.time()),
            ),
        )
        conn.commit()


def list_call_logs(limit: int = 25):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT direction, caller_name, phone, outcome, duration_seconds, transcript, created_at
            FROM call_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    now = int(time.time())
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT email, role FROM sessions WHERE token = ? AND expires_at > ?",
            (token, now),
        ).fetchone()
        if row is None:
            return None

        user_row = conn.execute(
            "SELECT name, organization, email, role FROM users WHERE email = ?",
            (row["email"],),
        ).fetchone()

    if user_row is None:
        return None

    user = dict(user_row)
    if not user.get("name"):
        email = (user.get("email") or "").strip()
        derived = email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        if derived:
            user["name"] = " ".join(part.capitalize() for part in derived.split())
        else:
            user["name"] = "Reception Staff"
    return user


init_db()


@app.get("/")
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/staff_admin_console_dashboard_3.html")
    return FileResponse("login.html")


@app.get("/login.html")
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/staff_admin_console_dashboard_3.html")
    return FileResponse("login.html")


@app.get("/signup.html")
async def signup_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/staff_admin_console_dashboard_3.html")
    return FileResponse("signup.html")


@app.get("/staff_admin_console_dashboard_3.html")
async def dashboard_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse(url="/login.html")
    return FileResponse("staff_admin_console_dashboard_3.html")


@app.post("/api/signup")
async def signup_api(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    name = (payload.get("name") or "").strip()
    organization = (payload.get("organization") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role = (payload.get("role") or "").strip()

    if not name or not organization or not email or not password or not role:
        raise HTTPException(status_code=400, detail="Please provide your full name, organization, email, password, and role.")

    if "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")

    if len(password) < 7 or not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password) or not any(ch.isupper() for ch in password):
        raise HTTPException(status_code=400, detail="Password does not meet the required format.")

    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    create_user_record(name, organization, email, password, role)
    return JSONResponse({"ok": True, "message": "Account created successfully."})


@app.post("/api/login")
async def login_api(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    organization = (payload.get("organization") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role = (payload.get("role") or "").strip()

    if not organization or not email or not password or not role:
        raise HTTPException(status_code=400, detail="Please provide organization, email, password, and role.")

    user = get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    if user["organization"].lower() != organization.lower():
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    if user["role"] != role:
        raise HTTPException(status_code=401, detail="Invalid role selection.")

    if not verify_password(password, user["password_salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = create_session(email, role)
    response = JSONResponse({"ok": True, "message": "Login successful."})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@app.get("/api/me")
async def current_user_api(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    email = (user.get("email") or "").strip()
    name = (user.get("name") or "").strip() or (
        email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
    )
    if not name:
        name = "Reception Staff"
    else:
        name = " ".join(part.capitalize() for part in name.split())

    return JSONResponse({
        "organization": user.get("organization") or "Reception 360",
        "email": email,
        "role": user.get("role") or "Staff",
        "name": name,
    })


@app.post("/api/logout")
async def logout_api(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()

    response = JSONResponse({"ok": True, "message": "Logged out."})
    response.delete_cookie(key=SESSION_COOKIE)
    return response


@app.get("/api/dashboard/calls")
async def dashboard_calls(request: Request):
    if not get_current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    rows = list_call_logs(limit=50)
    return JSONResponse(rows)


@app.post("/api/calls")
async def create_call_record(request: Request):
    if not get_current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = await request.json()
    direction = (payload.get("direction") or "inbound").lower()
    caller_name = payload.get("caller_name") or "Unknown caller"
    phone = payload.get("phone") or "Unknown"
    outcome = payload.get("outcome") or "completed"
    duration_seconds = int(payload.get("duration_seconds") or 0)
    transcript = payload.get("transcript") or ""

    log_call_event(direction, caller_name, phone, outcome, duration_seconds, transcript)
    return JSONResponse({"ok": True, "message": "Call logged."})


@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Twilio calls this URL when a call comes in."""
    form = await request.form()
    from_number = form.get("From") or "Unknown"
    log_call_event(
        direction="inbound",
        caller_name="Unknown caller",
        phone=str(from_number),
        outcome="connected",
        duration_seconds=0,
        transcript="Inbound call received.",
    )

    host = request.headers.get("host")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/ws"/>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Twilio connects here and streams audio."""
    await websocket.accept()

    # First two messages from Twilio are 'connected' and 'start' events
    start_data = websocket.iter_text()
    await start_data.__anext__()  # 'connected' event
    call_data = json.loads(await start_data.__anext__())
    stream_sid = call_data["start"]["streamSid"]

    logger.info(f"WebSocket connection accepted, stream_sid={stream_sid}")
    await run_bot(websocket, stream_sid)