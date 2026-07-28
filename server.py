import json
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response
from loguru import logger

from bot import run_bot
from db import get_db_connection

app = FastAPI()

@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Twilio calls this URL when a call comes in."""
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