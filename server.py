import json
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from loguru import logger

from bot import run_bot

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