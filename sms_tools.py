import os
from twilio.rest import Client
from loguru import logger
from dotenv import load_dotenv

# Load .env so the Twilio credentials are available no matter
# which file imports this module first.
load_dotenv()

# Read credentials defensively — .get() returns None instead of crashing
# if a value is missing, so a missing SMS credential disables SMS
# rather than taking down the whole server.
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

# Only build the Twilio client if we actually have credentials.
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    _client = None
    logger.warning("Twilio credentials missing — SMS sending is disabled.")


def _normalize_phone(raw: str) -> str:
    """
    Turn whatever the caller said into E.164 format (+1XXXXXXXXXX).
    Strips spaces, dashes, parentheses. Assumes US if 10 digits.
    """
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if raw.startswith("+"):
        return raw  # already formatted
    return f"+{digits}"  # best effort


def send_confirmation_sms(patient_name: str, patient_phone: str, when_human: str, reason: str) -> dict:
    """
    Send an appointment confirmation text.

    Args:
        patient_name: e.g. "Shreya Hathany"
        patient_phone: whatever the caller said, e.g. "(857) 763-9488"
        when_human: human-readable time, e.g. "Friday, May 15 at 10:30 AM"
        reason: e.g. "root canal"

    Returns:
        {"sent": True/False, "detail": str}
    """
    try:
        to_number = _normalize_phone(patient_phone)
        body = (
            f"Hi {patient_name}, your appointment at Reception360 Demo Dental Clinic "
            f"is confirmed for {when_human} ({reason}). "
            f"Reply or call us if you need to reschedule. See you then!"
        )
        message = _client.messages.create(
            body=body,
            from_=TWILIO_NUMBER,
            to=to_number,
        )
        logger.info(f"✉️  Confirmation SMS sent to {to_number}, sid={message.sid}")
        return {"sent": True, "detail": f"Sent to {to_number}"}
    except Exception as e:
        logger.error(f"send_confirmation_sms error: {e}")
        return {"sent": False, "detail": str(e)}