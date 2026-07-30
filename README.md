# reception_360

An AI-powered voice receptionist that answers phone calls, books appointments, and
handles front-desk questions for a dental clinic - entirely over the phone, in natural
conversation.

A caller dials a Twilio number, and reception_360 picks up: it understands speech,
answers questions about hours, location, services, providers, and insurance, checks for availability, books / reschedules / cancels appointments, and
texts a confirmation — all in a back-and-forth voice conversation. It also follows an
emergency protocol that interrupts everything else if a caller describes a medical
emergency.

## How it works

```
Caller → Twilio → /incoming-call (returns TwiML)
                → /ws  WebSocket  ── streams audio ──┐
                                                     ▼
                          Pipecat pipeline:
                          Deepgram (speech-to-text)
                          → Claude Sonnet 4.5 (conversation + tool use)
                          → ElevenLabs (text-to-speech)
                          → back to caller

          Claude tools: check_availability / book_appointment / cancel_appointment
                        → Google Calendar
                        + SMS confirmation → Twilio
```

## Tech stack

- **Python** 3.12+
- **FastAPI** + **Uvicorn** — web server exposing the Twilio webhook and WebSocket
- **Pipecat** — real-time voice pipeline orchestration
- **Twilio** — inbound phone calls and outbound SMS confirmations
- **Deepgram** — speech-to-text
- **Anthropic Claude (Sonnet 4.5)** — conversation, reasoning, and tool calls
- **ElevenLabs** — text-to-speech
- **Silero VAD** — voice activity detection
- **Google Calendar API** — appointment availability and booking

## Project structure

| File | Purpose |
|------|---------|
| `server.py` | FastAPI app — Twilio `/incoming-call` webhook and `/ws` audio WebSocket |
| `bot.py` | Builds the Pipecat voice pipeline, the system prompt, and Claude's tools |
| `calendar_tools.py` | `check_availability`, `book_appointment`, `cancel_appointment` against Google Calendar |
| `sms_tools.py` | Sends SMS appointment confirmations via Twilio |
| `clinic_config.py` | Clinic details — name, address, hours, providers, services, insurance, pricing |
| `authorize_calendar.py` | One-time script to authorize Google Calendar access |
| `main.py` | Placeholder entry point |
| `pyproject.toml` / `uv.lock` | Dependencies and lockfile (managed with `uv`) |

## Setup

### 1. Prerequisites

- Python 3.12 or newer
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Accounts / API keys for: Anthropic, Deepgram, ElevenLabs, Twilio
- A Google Cloud project with the Calendar API enabled

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your_anthropic_key
DEEPGRAM_API_KEY=your_deepgram_key
ELEVENLABS_API_KEY=your_elevenlabs_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
```

> Check `sms_tools.py` and `calendar_tools.py` for any additional variables they
> expect (e.g. a Twilio "from" number or a calendar ID) and add those too.

### 4. Authorize Google Calendar

Download your OAuth client credentials from Google Cloud and save them as
`google_credentials.json` in the project root, then run:

```bash
uv run python authorize_calendar.py
```

This opens a browser for you to grant access once. On success it writes
`google_token.json`, which the app reuses on every run.

### 5. Run the server

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

### 6. Connect Twilio

Twilio needs a public URL to reach your server. For local development, expose it with
a tunneling tool (e.g. ngrok):

```bash
ngrok http 8000
```

Then in the Twilio console, set your phone number's **A call comes in** webhook to:

```
https://<your-public-url>/incoming-call
```

Call the number and the receptionist will pick up.

## Configuration

All clinic-specific content lives in `clinic_config.py` — clinic name, address, hours,
parking and directions, providers and their schedules, services offered / not offered,
accepted insurance, and price ranges. Edit that file to adapt the receptionist to a
different clinic; the system prompt in `bot.py` is generated from it automatically.

## Notes

- **Secrets:** `.env`, `google_credentials.json`, and `google_token.json` contain
  credentials — keep them out of version control. Make sure they're listed in
  `.gitignore`.
- The bot is instructed never to give medical advice and to escalate anything that
  sounds like a medical emergency before continuing with any other task.
- Prices are always quoted as ranges with a disclaimer; the bot never quotes exact
  prices or calculates what a patient personally owes.

## License

No license file is currently included in this repository. Add one if you intend for
others to use, modify, or distribute this project.
