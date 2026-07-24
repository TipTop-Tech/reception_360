import asyncpg
import os
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_db_connection():
    """Create a connection to the Supabase database."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

async def save_call(caller_phone: str, direction: str = "inbound") -> str | None:
    """Save a new call record when a call starts. Returns the call ID."""
    conn = await get_db_connection()
    if not conn:
        return None
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO call (caller_phone, direction, started_at)
            VALUES ($1, $2, NOW())
            RETURNING id
            """,
            caller_phone, direction
        )
        call_id = str(row["id"])
        logger.info(f"📞 Call saved to database with ID: {call_id}")
        return call_id
    except Exception as e:
        logger.error(f"Error saving call: {e}")
        return None
    finally:
        await conn.close()

async def save_transcript(call_id: str, messages: list) -> None:
    """Save the transcript of a call after it ends."""
    conn = await get_db_connection()
    if not conn:
        return
    try:
        import json
        await conn.execute(
            """
            INSERT INTO transcript (call_id, content)
            VALUES ($1, $2)
            ON CONFLICT (call_id) DO UPDATE SET content = $2
            """,
            call_id, json.dumps(messages)
        )
        logger.info(f"📝 Transcript saved for call {call_id}")
    except Exception as e:
        logger.error(f"Error saving transcript: {e}")
    finally:
        await conn.close()

async def update_call_outcome(call_id: str, outcome: str, duration_seconds: int) -> None:
    """Update the call record when a call ends."""
    conn = await get_db_connection()
    if not conn:
        return
    try:
        await conn.execute(
            """
            UPDATE call
            SET outcome = $1, duration_seconds = $2
            WHERE id = $3
            """,
            outcome, duration_seconds, call_id
        )
        logger.info(f"✅ Call {call_id} updated with outcome: {outcome}")
    except Exception as e:
        logger.error(f"Error updating call outcome: {e}")
    finally:
        await conn.close()