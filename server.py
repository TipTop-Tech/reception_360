import json
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from loguru import logger
import csv
import io
from fastapi.responses import StreamingResponse

from bot import run_bot
from db import get_db_connection

app = FastAPI()

@app.get("/")
async def root():
    return FileResponse("login.html")

@app.get("/login.html")
async def login_page():
    return FileResponse("login.html")

@app.get("/signup.html")
async def signup_page():
    return FileResponse("signup.html")

@app.get("/staff_admin_console_dashboard_3.html")
async def dashboard_page():
    return FileResponse("staff_admin_console_dashboard_3.html")

@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Twilio calls this URL when a call comes in."""
    form_data = await request.form()
    caller_phone = form_data.get("From", "unknown")
    host = request.headers.get("host")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/ws">
            <Parameter name="callerPhone" value="{caller_phone}" />
        </Stream>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/ws")
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Twilio connects here and streams audio."""
    await websocket.accept()

    start_data = websocket.iter_text()
    await start_data.__anext__()  # 'connected' event
    call_data = json.loads(await start_data.__anext__())
    stream_sid = call_data["start"]["streamSid"]
    caller_phone = call_data["start"].get("customParameters", {}).get("callerPhone", "unknown")

    logger.info(f"WebSocket connection accepted, stream_sid={stream_sid}, caller={caller_phone}")
    await run_bot(websocket, stream_sid, caller_phone)

@app.get("/api/calls")
async def get_calls():
    """Returns recent calls from Supabase."""
    conn = await get_db_connection()
    if not conn:
        return {"calls": []}
    try:
        rows = await conn.fetch(
            """
            SELECT id, caller_phone, direction, started_at, 
                   duration_seconds, outcome
            FROM call
            ORDER BY started_at DESC
            LIMIT 20
            """
        )
        return {"calls": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"Error fetching calls: {e}")
        return {"calls": []}
    finally:
        await conn.close()

@app.get("/api/stats")
async def get_stats():
    """Returns dashboard KPI numbers."""
    conn = await get_db_connection()
    if not conn:
        return {}
    try:
        calls_today = await conn.fetchval(
            "SELECT COUNT(*) FROM call WHERE started_at::date = CURRENT_DATE"
        )
        appointments_today = await conn.fetchval(
            "SELECT COUNT(*) FROM appointment WHERE start_at::date = CURRENT_DATE"
        )
        return {
            "calls_today": calls_today or 0,
            "appointments_today": appointments_today or 0,
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {}
    finally:
        await conn.close()

@app.get("/api/export/calls")
async def export_calls():
    """Export all call logs as a CSV file."""
    conn = await get_db_connection()
    if not conn:
        return {"error": "Database connection failed"}
    try:
        rows = await conn.fetch(
            """
            SELECT id, caller_phone, direction, started_at, 
                   duration_seconds, outcome, created_at
            FROM call
            ORDER BY started_at DESC
            """
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Call ID","Phone", "Direction", "Started At", "Duration (seconds)", "Outcome", "Created At"])
        for row in rows:
            writer.writerow([row["id"], row["caller_phone"], row["direction"], row["started_at"], row["duration_seconds"], row["outcome"], row["created_at"]])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=call_logs.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting calls: {e}")
        return {"error": str(e)}
    finally:
        await conn.close()

@app.get("/api/calls/{call_id}/transcript")
async def get_call_transcript(call_id: str):
    """Returns the full transcript for a single call."""
    conn = await get_db_connection()
    if not conn:
        return {"error": "Database connection failed"}
    try:
        row = await conn.fetchrow(
            "SELECT content FROM transcript WHERE call_id = $1",
            call_id
        )
        if not row:
            return {"error": "No transcript found for this call"}
        return {"call_id": call_id, "transcript": json.loads(row["content"])}
    except Exception as e:
        logger.error(f"Error fetching transcript: {e}")
        return {"error": str(e)}
    finally:
        await conn.close()