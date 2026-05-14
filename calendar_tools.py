"""
Google Calendar integration for Reception360.

NOTE: The calendar being read and written here belongs to the DOCTOR / CLINIC,
not the patient. The Google account you authorized with authorize_calendar.py
is the clinic's calendar.

In a multi-tenant version, each clinic would have its own token file and
calendar ID, looked up by the Twilio phone number the call came in on.
"""

from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from loguru import logger
from zoneinfo import ZoneInfo

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = "primary"  # The clinic's primary Google Calendar
TIMEZONE = "America/New_York"  # Change to your clinic's timezone
APPOINTMENT_DURATION_MINUTES = 30
BUSINESS_START_HOUR = 9   # 9 AM
BUSINESS_END_HOUR = 17    # 5 PM
TIMEZONE = "America/New_York"  # you already have this line
TZ = ZoneInfo(TIMEZONE)  # add this line right after it

def get_calendar_service():
    """Load the clinic's saved credentials and build a Calendar API client."""
    creds = Credentials.from_authorized_user_file("google_token.json", SCOPES)
    return build("calendar", "v3", credentials=creds)


def _is_business_hours(dt: datetime) -> bool:
    """Check whether the given datetime falls within clinic operating hours."""
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    end_dt = dt + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)
    if dt.hour < BUSINESS_START_HOUR:
        return False
    if end_dt.hour > BUSINESS_END_HOUR or (end_dt.hour == BUSINESS_END_HOUR and end_dt.minute > 0):
        return False
    return True


def _get_busy_intervals(service, start: datetime, end: datetime):
    """
    Return all (start, end) timezone-aware datetime tuples for existing events
    in the window. start and end must be timezone-aware.
    """
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    intervals = []
    for event in events_result.get("items", []):
        if "dateTime" not in event["start"]:
            continue  # skip all-day events
        ev_start = datetime.fromisoformat(event["start"]["dateTime"])
        ev_end = datetime.fromisoformat(event["end"]["dateTime"])
        ev_summary = event.get("summary", "")
        ev_id = event.get("id", "")
        intervals.append((ev_start, ev_end, ev_summary, ev_id))

    logger.info(f"🗓️  Querying {start} to {end} — found {len(intervals)} events: {intervals}")
    return intervals


def check_availability(date: str, time: str) -> dict:
    """
    Check whether a specific slot on the doctor's calendar is free.

    Args:
        date: YYYY-MM-DD format
        time: HH:MM in 24-hour format

    Returns:
        {
          "available": bool,
          "reason": str,
          "suggested_slots": list of {"date": str, "time": str, "human": str}
        }

        suggested_slots is populated only when the requested slot is unavailable.
    """
    try:
        start_dt = datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=TZ)
        end_dt = start_dt + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        if start_dt < datetime.now(TZ):
            return {"available": False, "reason": "That time is in the past.", "suggested_slots": []}

        if not _is_business_hours(start_dt):
            suggestions = find_next_available_slots(start_dt, count=3)
            return {
                "available": False,
                "reason": "That time is outside our hours (Monday-Friday, 9am to 5pm).",
                "suggested_slots": suggestions,
            }

        service = get_calendar_service()
        busy = _get_busy_intervals(service, start_dt, end_dt)

        if busy:
            suggestions = find_next_available_slots(start_dt, count=3)
            return {
                "available": False,
                "reason": "That time slot is already booked on the doctor's calendar.",
                "suggested_slots": suggestions,
            }

        return {"available": True, "reason": "Slot is available.", "suggested_slots": []}

    except Exception as e:
        logger.error(f"check_availability error: {e}")
        return {"available": False, "reason": "I'm having trouble checking the calendar right now.", "suggested_slots": []}


def find_next_available_slots(start_from: datetime, count: int = 3) -> list:
    """
    Find the next `count` available 30-minute slots after start_from on the
    doctor's calendar, within business hours.

    Returns a list like:
      [{"date": "2026-05-13", "time": "10:00", "human": "Tuesday, May 13 at 10:00 AM"}, ...]
    """
    try:
        service = get_calendar_service()
        slots_found = []

        # Walk forward in 30-minute increments, up to 14 days out
        candidate = start_from + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)
        # Round up to nearest half-hour
        candidate = candidate.replace(second=0, microsecond=0)
        if candidate.minute < 30:
            candidate = candidate.replace(minute=30)
        else:
            candidate = candidate.replace(minute=0) + timedelta(hours=1)

        end_search = start_from + timedelta(days=14)

        # Pull all busy intervals in the search window once (faster than per-slot calls)
        busy = _get_busy_intervals(service, start_from, end_search)

        while candidate < end_search and len(slots_found) < count:
            slot_end = candidate + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

            if _is_business_hours(candidate):
                # Check overlap with any busy interval
                conflict = any(
                    not (slot_end <= b_start or candidate >= b_end)
                    for b_start, b_end, *_ in busy
                )
                if not conflict:
                    slots_found.append({
                        "date": candidate.strftime("%Y-%m-%d"),
                        "time": candidate.strftime("%H:%M"),
                        "human": candidate.strftime("%A, %B %d at %I:%M %p"),
                    })

            candidate += timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        return slots_found

    except Exception as e:
        logger.error(f"find_next_available_slots error: {e}")
        return []


def book_appointment(patient_name: str, patient_phone: str, date: str, time: str, reason: str) -> dict:
    """
    Create an event on the doctor's calendar for this appointment.
    """
    try:
        start_dt = datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=TZ)
        end_dt = start_dt + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        availability = check_availability(date, time)
        if not availability["available"]:
            # IDEMPOTENCY CHECK — before trusting this "unavailable" result,
            # find out WHO is in the slot. If it's THIS SAME patient, then this
            # is a duplicate call (e.g. caused by interruption-jumbling) and the
            # booking already succeeded. Treat that as success, not a conflict.
            service = get_calendar_service()
            existing = _get_busy_intervals(service, start_dt, end_dt)
            wanted_name = patient_name.strip().lower()
            for b_start, b_end, b_summary, b_id in existing:
                if wanted_name and wanted_name in b_summary.strip().lower():
                    logger.info(
                        f"♻️  Idempotent hit — '{patient_name}' is already booked "
                        f"in this slot (event {b_id}). Returning existing booking as success."
                    )
                    return {
                        "success": True,
                        "event_id": b_id,
                        "confirmation": (
                            f"You're all set — {patient_name} is booked for "
                            f"{start_dt.strftime('%A, %B %d at %I:%M %p')}."
                        ),
                        "suggested_slots": [],
                    }
            # Not this patient — it's a genuine conflict with someone else.
            return {
                "success": False,
                "event_id": None,
                "confirmation": availability["reason"],
                "suggested_slots": availability.get("suggested_slots", []),
            }

        event_body = {
            "summary": f"{patient_name} - {reason}",
            "description": (
                f"Patient: {patient_name}\n"
                f"Phone: {patient_phone}\n"
                f"Reason: {reason}\n"
                f"Booked by Reception360 AI"
            ),
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
        }

        service = get_calendar_service()
        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event_body,
        ).execute()

        confirmation = f"Booked {patient_name} for {start_dt.strftime('%A, %B %d at %I:%M %p')}."
        logger.info(f"Appointment booked: {confirmation}")

        # Send confirmation SMS (non-blocking — if it fails, booking still succeeded)
        from sms_tools import send_confirmation_sms
        sms_result = send_confirmation_sms(
            patient_name=patient_name,
            patient_phone=patient_phone,
            when_human=start_dt.strftime("%A, %B %d at %I:%M %p"),
            reason=reason,
        )
        logger.info(f"   SMS result: {sms_result}")

        return {
            "success": True,
            "event_id": created_event["id"],
            "confirmation": confirmation,
            "suggested_slots": [],
        }

    except Exception as e:
        logger.error(f"book_appointment error: {e}")
        return {
            "success": False,
            "event_id": None,
            "confirmation": "I had trouble saving that booking.",
            "suggested_slots": [],
        }


def cancel_appointment(date: str, time: str, patient_name: str) -> dict:
    """Cancel an existing appointment on the doctor's calendar."""
    try:
        start_dt = datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=TZ)
        end_dt = start_dt + timedelta(minutes=APPOINTMENT_DURATION_MINUTES)

        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
        ).execute()

        events = events_result.get("items", [])
        matching = [e for e in events if patient_name.lower() in e.get("summary", "").lower()]

        if not matching:
            return {"success": False, "message": "There's no active appointment under that name at that time — it may have already been cancelled, or the details might be slightly different."}

        for event in matching:
            service.events().delete(calendarId=CALENDAR_ID, eventId=event["id"]).execute()

        return {"success": True, "message": f"Cancelled appointment for {patient_name} on {start_dt.strftime('%A, %B %d at %I:%M %p')}."}

    except Exception as e:
        logger.error(f"cancel_appointment error: {e}")
        return {"success": False, "message": "I had trouble cancelling that appointment."}