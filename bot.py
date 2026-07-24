import os
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger
from clinic_config import CLINIC
from datetime import datetime, timedelta
from sms_tools import send_confirmation_sms
from pipecat.frames.frames import LLMMessagesFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.elevenlabs import ElevenLabsTTSService
import httpx


from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")

from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from calendar_tools import check_availability, book_appointment, cancel_appointment
from db import save_call, save_transcript, update_call_outcome

load_dotenv()

def _format_providers():
    lines = []
    for p in CLINIC["providers"]:
        days = ", ".join(p["days"])
        lines.append(f"  - {p['name']} ({p['role']}) — works {days}")
    return "\n".join(lines)

def _format_services():
    return "\n".join(f"  - {s}" for s in CLINIC["services"])

def _format_not_offered():
    return "\n".join(f"  - {s}" for s in CLINIC["services_not_offered"])

def _format_insurance():
    return ", ".join(CLINIC["insurance_accepted"])

def _format_prices():
    lines = []
    for service, price in CLINIC["price_ranges"].items():
        lines.append(f"  - {service}: {price}")
    return "\n".join(lines)
def _date_reference():
    """Generates a plain calendar list so the LLM never has to compute weekdays itself."""
    today = datetime.now(TZ).date()
    lines = []
    for i in range(0, 21):
        d = today + timedelta(days=i)
        if i == 0:
            label = " <-- TODAY"
        elif i == 1:
            label = " <-- TOMORROW"
        else:
            label = ""
        lines.append(f"  {d.strftime('%A, %B %d, %Y')}{label}")
    return "\n".join(lines)

def build_system_prompt():
    now = datetime.now()
    return f"""You are the receptionist for {CLINIC['name']}.

=== EMERGENCY PROTOCOL — HIGHEST PRIORITY, OVERRIDES EVERYTHING ELSE ===

If at ANY point a caller describes a potential medical emergency, STOP the current task immediately and address it before anything else. Do not continue booking, confirming, or answering other questions until the emergency is addressed.

Emergency signs include: significant or uncontrolled bleeding, severe pain, swelling that affects breathing or swallowing, a knocked-out or broken tooth, facial trauma or injury, signs of serious infection (fever with facial swelling), or any situation the caller describes as urgent or frightening.

When you detect any of these, your immediate and ONLY next response must be, clearly and simply:
- Tell them that for a medical emergency they should hang up and call 911 or go to the nearest emergency room right now.
- For urgent dental issues that are not life-threatening, tell them you will flag this for a clinician to follow up as soon as possible, and offer the soonest available appointment.
- Do NOT bury this message inside other information. Say it first, say it plainly, keep it short.

Current time is {now.strftime('%I:%M %p')}.

=== DATE REFERENCE — use this for ALL day-of-week math, do NOT calculate dates yourself ===
{_date_reference()}

When a caller says a day name like "Monday" or "next Tuesday", find the NEXT matching date in the list above and use that exact date.
Never guess or calculate what weekday a date falls on — only read it from this DATE REFERENCE.
If a caller claims a date is a certain weekday and it conflicts with the DATE REFERENCE, politely tell them what the reference shows instead of just agreeing.

Your job is to help callers with:
- Booking, rescheduling, or cancelling appointments
- Questions about hours, location, parking, and directions
- Questions about what services the clinic offers
- Questions about providers and their schedules
- Whether the clinic accepts a particular insurance
- General cost estimate questions
- Taking a message for staff when you can't help

=== CLINIC INFORMATION ===

Location: {CLINIC['address']}
Parking: {CLINIC['parking']}
Getting in: {CLINIC['directions_note']}

Hours: {CLINIC['hours_text']}

Accepting new patients: {"Yes" if CLINIC['accepting_new_patients'] else "No"}
New patient info: {CLINIC['new_patient_note']}

Providers:
{_format_providers()}

Services we offer:
{_format_services()}

Services we do NOT offer:
{_format_not_offered()}

Insurance accepted (in-network): {_format_insurance()}
Insurance note: {CLINIC['insurance_note']}

Cost estimates (these are RANGES, never exact prices):
{_format_prices()}
Pricing disclaimer you must always include when quoting a price: {CLINIC['pricing_disclaimer']}

=== BOOKING PROCESS ===

1. Ask what day and time they want
2. Use check_availability to confirm the slot is free BEFORE confirming
3. If the slot is NOT available, the response includes suggested_slots — offer the caller the first 1-2 in natural language (e.g., "That time is taken, but I have 10:30 AM or 11:00 AM open. Which works?")
4. Once a free slot is agreed on, collect: full name (confirm spelling), phone number, and reason for visit
5. Use book_appointment to actually create the booking
6. Confirm the booking details back to them
7. If a caller wants to verify their insurance coverage, use verify_insurance. You will need their member ID, payer ID, first name, and last name. Common payer IDs: Aetna = 60054. Before calling verify_insurance, always say something like "Let me check that for you, one moment" — insurance verification can take a few seconds, so let the caller know you're working on it before you call the function.

=== HANDLING INFORMATION QUESTIONS ===

- Hours, location, parking, providers, services, insurance: answer directly from the CLINIC INFORMATION above. Do not make up details that aren't listed.
- If asked about a service and you're not sure: if it's in the "services we offer" list, say yes; if it's in "services we do NOT offer", say no clearly; if it's in neither list, say you're not certain and offer to take a message for staff to confirm.
- If asked whether you accept an insurance: check the in-network list. If it's listed, confirm yes. If it's not listed, say you're not in-network with that plan but you do accept out-of-network patients, and mention coverage varies.
- If asked about cost: give the RANGE from the cost estimates, and ALWAYS follow it with the pricing disclaimer. Never quote an exact price. Never try to calculate what the patient personally owes — that depends on their specific insurance.

=== CRITICAL RULES ===

- Keep responses to 1-2 sentences
- NEVER tell a caller they are booked unless book_appointment returned success
- Always check availability before promising a time
- When a time is unavailable, always offer specific alternative times from suggested_slots
- If you have already successfully called a function and gotten a success result, do NOT call it again for the same request, even if the caller then says something like "hello" or "are you there"
- Never give medical or dental advice — say a clinician will follow up
- If anything sounds like a medical emergency, follow the EMERGENCY PROTOCOL at the top of this prompt before doing anything else
- If you cannot help with something, offer to take a message for staff
"""

# Function definitions Claude will see
TOOLS = [
    {
        "name": "check_availability",
        "description": "Check if a specific date and time is available for booking. Always call this BEFORE telling a caller a slot is available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format, e.g., 2026-05-15"},
                "time": {"type": "string", "description": "Time in 24-hour HH:MM format, e.g., 14:30"},
            },
            "required": ["date", "time"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Create a confirmed appointment in the calendar. Only call this after check_availability confirms the slot is free AND you have collected the patient's name, phone, and reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string", "description": "Patient's full name"},
                "patient_phone": {"type": "string", "description": "Patient's phone number"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Time in 24-hour HH:MM format"},
                "reason": {"type": "string", "description": "Reason for the visit, e.g., cleaning, checkup, consultation"},
            },
            "required": ["patient_name", "patient_phone", "date", "time", "reason"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment by date, time, and patient name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Time in 24-hour HH:MM format"},
                "patient_name": {"type": "string", "description": "Patient's full name"},
            },
            "required": ["date", "time", "patient_name"],
        },
    },

    {
    "name": "verify_insurance",
    "description": "Verify live insurance eligibility status via Stedi. Use this when a patient asks to check if their insurance is accepted or coverage is active.",
    "input_schema": {
        "type": "object",
        "properties": {
            "member_id": {"type": "string", "description": "The subscriber's insurance member or policy ID number."},
            "payer_id": {"type": "string", "description": "The unique electronic Payer ID (e.g., '60054' for Aetna)."},
            "first_name": {"type": "string", "description": "Subscriber's first name."},
            "last_name": {"type": "string", "description": "Subscriber's last name."}
        },
        "required": ["member_id", "payer_id", "first_name", "last_name"],
    },
},
]


async def run_bot(websocket_client, stream_sid):
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
            params=VADParams(
            stop_secs=1.1,
            start_secs=0.2,
            confidence=0.7,
            min_volume=0.6,
        )
),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
        ),
    )

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    tts = ElevenLabsTTSService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        voice_id="EXAVITQu4vr4xnSDxMaL",
    )

    llm = AnthropicLLMService(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model="claude-sonnet-4-5",
    )

    # Register the calendar functions so Claude can call them
    async def handle_check_availability(function_name, tool_call_id, args, llm, context, result_callback):
        logger.info(f"🔍 Claude is calling check_availability with: {args}")
        result = check_availability(args["date"], args["time"])
        logger.info(f"   → result: {result}")
        await result_callback(result)

    async def handle_book_appointment(function_name, tool_call_id, args, llm, context, result_callback):
        logger.info(f"📅 Claude is calling book_appointment with: {args}")
        result = book_appointment(
            patient_name=args["patient_name"],
            patient_phone=args["patient_phone"],
            date=args["date"],
            time=args["time"],
            reason=args["reason"],
        )
        logger.info(f"   → result: {result}")
        await result_callback(result)

    async def handle_cancel_appointment(function_name, tool_call_id, args, llm, context, result_callback):
        logger.info(f"❌ Claude is calling cancel_appointment with: {args}")
        result = cancel_appointment(args["date"], args["time"], args["patient_name"])
        logger.info(f"   → result: {result}")
        await result_callback(result)

    async def handle_verify_insurance(function_name, tool_call_id, args, llm, context, result_callback):
        logger.info(f"Claude is calling verify_insurance with: {args}")
        result = await verify_insurance_with_stedi(
            member_id=args["member_id"],
            payer_id=args["payer_id"],
            first_name=args["first_name"],
            last_name=args["last_name"]
        )
        logger.info(f"   → Stedi response: {result}")
        await result_callback(result)

    
    llm.register_function("check_availability", handle_check_availability)
    llm.register_function("book_appointment", handle_book_appointment)
    llm.register_function("cancel_appointment", handle_cancel_appointment)
    llm.register_function("verify_insurance", handle_verify_insurance)

    messages = [{"role": "system", "content": build_system_prompt()}]
    context = OpenAILLMContext(messages, tools=TOOLS)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
    )

    call_id = None
    call_start_time = None

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal call_id, call_start_time
        call_start_time = datetime.now()
        call_id = await save_call(
            caller_phone=stream_sid,
            direction="inbound"
        )
        messages.append({"role": "user", "content": "Say hello and introduce yourself briefly."})
        await task.queue_frames([LLMMessagesFrame(messages)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        if call_id:
            duration = int((datetime.now() - call_start_time).total_seconds()) if call_start_time else 0
            await save_transcript(call_id, messages)
            await update_call_outcome(call_id, "info_only", duration)
            logger.info(f"📊 Call {call_id} saved to database")
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)

PAYER_ID_MAP = {
    "delta dental": "DDPA",
    "cigna": "62308",
    "metlife": "37602",
    "aetna": "60054",
    "guardian": "GARD1",
    "united healthcare": "87726",
}

async def verify_insurance_with_stedi(
    member_id: str, 
    payer_id: str, 
    first_name: str, 
    last_name: str
) -> str:
    """
    Verifies insurance eligibility via Stedi's real-time API.
    Uses sandbox mode when a test API key is provided.
    """
    accepted_lower = [name.lower() for name in CLINIC["insurance_accepted"]]
    
    payer_name = next((k for k, v in PAYER_ID_MAP.items() if v == payer_id), None)

    if payer_name not in accepted_lower:
        return "I'm sorry, we are not in-network with that insurance. We do accept out-of-network patients, but coverage and costs will vary."
        
    url = "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"
    stedi_key = os.environ.get("STEDI_API_KEY", "")

    if not stedi_key:
        logger.error("STEDI_API_KEY missing from environment variables!")
        return "Insurance verification is currently offline."

    headers = {
        "Authorization": f"Key {stedi_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "tradingPartnerServiceId": payer_id,
        "provider": {
            "organizationName": CLINIC["name"],
            "npi": "1999999984"  # Test NPI 
        },
        "subscriber": {
            "memberId": member_id,
            "firstName": first_name,
            "lastName": last_name
        },
        "encounter": {
            "serviceTypeCodes": ["30","35"]  
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                benefits = data.get("benefitsInformation", [])

                if benefits:
                    copay = "not listed"
                    deductible = "not listed"
                    is_inactive = False
                    DENTAL_STCS = {"35", "30"}

                    for item in benefits:
                        code = item.get("code")  # "1" Active, "6" Inactive, "B" Copay, "C" Deductible
                        network = item.get("inPlanNetworkIndicatorCode")  # Y / N / U / W
                        amount = item.get("benefitAmount") 
                        stcs = set(item.get("serviceTypeCodes", []))

                        if code == "6":
                            is_inactive = True

                        if code == "B" and amount is not None and network in ("Y", "W") and stcs & DENTAL_STCS:
                            copay = f"${amount}"

                        if code == "C" and amount is not None and network in ("Y", "W") and stcs & DENTAL_STCS:
                            deductible = f"${amount}"

                    if is_inactive:
                        return "Insurance verification complete. Unfortunately, this coverage appears to be inactive. You may want to double-check the member ID."

                    return f"Insurance verification complete. Your coverage is active. I see a general co-pay of {copay} and your individual deductible is {deductible}."

                else:
                    return "Insurance verification complete. Unfortunately, the system shows that this coverage is currently inactive or could not be found. You may want to double-check the member ID."

            else:
                logger.error(f"Stedi returned status {response.status_code}: {response.text}")
                return "I wasn't able to verify insurance right now. Let me take a message for staff to follow up."

    except Exception as e:
        logger.error(f"Stedi connection error: {e}")
        return "Error connecting to the insurance verification service."