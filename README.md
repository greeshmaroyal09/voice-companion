# Voice Companion — Context-Aware Telugu Slot Dialogue

**Banking preparation phase:** See [BANKING_PREPARATION.md](BANKING_PREPARATION.md) for architecture, official sources, coverage limits, verification status, and the complete Telugu test journey. The dialogue is a bounded rules-based state machine, not an LLM. Source-backed SBI checklists are now available after scope confirmation.

A mobile-first React + TypeScript + Vite screen backed by FastAPI. Record or type Telugu sentences, see mixed Telugu/English transcripts, and use the speaker button to hear contextual Telugu replies synthesized via Gnani TTS.

The assistant remembers extracted facts (banking intent, institution, town, branch) across turns, asks only for missing information one question at a time, never invents banking requirements/documents, and handles user corrections gracefully.

## Windows PowerShell: run locally

Run commands from `C:\Users\thispc\voice-companion`. Node.js 22.12+ (or 24 LTS) and Python 3.12+ are suitable. Use `npm.cmd` and the virtual environment's Python directly; no PowerShell execution-policy changes or environment activation are needed.

Dependencies have already been installed in this working folder (`node_modules` and `.venv`). A workspace-local Python runtime is in the ignored `.tools` directory because Python was not initially on PATH. Keep `.tools` while using this `.venv`.

For a **fresh checkout**, install Node.js and Python first, then:

```powershell
Set-Location C:\Users\thispc\voice-companion
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd ci
```

If your Python installation provides `python` instead of `py`, use `python -m venv .venv` for the environment creation command.

### 1. Set the backend key

```powershell
Set-Location C:\Users\thispc\voice-companion
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad.exe .env
```

In **`C:\Users\thispc\voice-companion\.env`**, set the existing line to `GNANI_API_KEY=your_actual_key` and save. Use a Gnani key with STT and TTS access and available credits. Do not paste the key into chat, frontend source, a `VITE_` variable, or a command that prints it.

FastAPI loads this root `.env` regardless of the shell's working directory. An existing `GNANI_API_KEY` process environment variable takes precedence. Restart FastAPI after changing it; refreshing the browser alone does not reload the key. `.env` and environment-specific variants are ignored by Git; `.env.example` contains no credential.

### Optional Gemini interpretation

For natural Telugu and Telugu-English intent extraction, set these two lines in the same root `.env` file using Notepad:

```dotenv
GEMINI_API_KEY=<your Gemini API key>
GEMINI_MODEL=gemini-3.8-flash
```

Get the API key from Google AI Studio and enter it directly in `.env`; do not paste it into chat, source code, a `VITE_` variable, or a command that prints it. Restart FastAPI after saving. The backend sends Gemini only the current message after redacting common identifiers (PAN, Aadhaar, phone, email, account numbers, OTP/PIN/password values, and explicit street-address text), plus the confirmed intent/bank, a location-present flag, and the pending onboarding step. It sends no conversation history or stored town/branch name. Gemini returns a schema-checked interpretation; the local SBI/RBI catalog supplies all factual answers. If the key is absent or Gemini fails, the deterministic handler continues and asks for clarification when needed.

### 2. Start FastAPI — terminal 1

```powershell
Set-Location C:\Users\thispc\voice-companion
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 3. Start Vite — terminal 2

```powershell
Set-Location C:\Users\thispc\voice-companion
npm.cmd run dev
```

Open **http://127.0.0.1:5173/**. Vite forwards `/api` requests to FastAPI on port 8000. Keep both terminals running; Ctrl+C stops each server. If a port is already occupied by this app, use that server or stop it before starting another one.

Both services bind to this computer only. A physical phone cannot use this computer's `127.0.0.1`. For a later phone deployment, use HTTPS and an appropriate same-origin backend proxy: microphone access generally does not work over a plain HTTP LAN address. You can inspect the mobile layout with your desktop browser's device toolbar.

## Test recording and playback

1. Open http://127.0.0.1:5173/ in a browser supporting Web Audio and AudioWorklet (such as a current Chrome or Edge). After saving the key and restarting FastAPI, refresh this page.
2. Click the large microphone button and allow microphone access when the browser asks.
3. Say a short phrase, for example **“నాకు SBI bank లో account తెరవాలి.”** Speak for roughly 2–5 seconds.
4. Click the same button to stop. It automatically stops at 25 seconds. The app releases the microphone and uploads a WAV to FastAPI.
5. Wait for **You said** to show the transcript. The companion remembers SBI and account opening, then asks **“మీరు ఏ పట్టణం లేదా బ్రాంచ్‌కు వెళ్లాలనుకుంటున్నారు?”** English words should remain in Latin letters while Telugu remains in Telugu script. Recognition accuracy still depends on the audio and provider.
6. When the status says **Reply ready to listen**, click **Listen to reply**. You should hear the Telugu reply. Click again after it finishes to replay the same audio without another TTS call. While playing, the button stops playback.
7. If TTS fails after transcription, the transcript and reply remain visible. Click **Retry reply audio**, wait, then click **Listen to reply**. Playback deliberately requires a tap, which also works with browser autoplay restrictions.

Additional manual checks:

- Deny microphone permission: the app explains how to enable it in the browser's site settings.
- Stop immediately or record silence: the app asks for a longer recording or a working microphone.
- Record for 25 seconds: capture stops automatically and the submitted WAV stays within Gnani's 30-second REST limit.
- Stop FastAPI: the app should show a backend connection message.
- With no key: `/api/health` reports `gnani_configured: false` and speech calls explain where to set it. No placeholder transcript or synthetic success is shown.

## Audio and Gnani contract

Official docs were checked on November 7, 2026, before implementing recording.

| Item | Implementation | Official source |
| --- | --- | --- |
| REST STT | `POST https://api.vachana.ai/stt/v3`; multipart field `audio_file` | [REST transcription](https://docs.gnani.ai/api/STT/speech-to-text) |
| Authentication | Backend sends `X-API-Key-ID` on both provider requests | [REST transcription](https://docs.gnani.ai/api/STT/speech-to-text) |
| STT model and script | `model=prisma-v3.0`, `language_code=te-IN,en-IN`, `format=codemix` | [Prisma v3.0](https://docs.gnani.ai/api/STT/models/prisma-v3) |
| Accepted REST audio | WAV, MP3, OGG, FLAC, AAC, M4A; maximum 30 seconds | [STT limits](https://docs.gnani.ai/api/STT/limits) |
| REST TTS | `POST https://api.vachana.ai/api/v1/tts/inference`; JSON; returns binary audio | [TTS REST](https://docs.gnani.ai/api/TTS/tts-inference) |
| TTS model and voice | `model=timbre-v2.5`, `voice=Lavanya`, `language=te-IN` | [Voice catalog](https://docs.gnani.ai/api/TTS/available-voices) |
| Reply audio | `audio_config`: WAV, `linear_pcm`, 24,000 Hz, one channel, two-byte samples | [TTS REST](https://docs.gnani.ai/api/TTS/tts-inference) |

The `/stt/v3` URL does **not** by itself select Prisma v3.0: the explicit model field does. `codemix` retains English words in Latin script. The backend returns the transcript as received, without translation, transliteration, or Unicode rewriting.

Browser recording uses `getUserMedia` → AudioWorklet PCM capture → OfflineAudioContext resampling to 16 kHz → signed 16-bit mono WAV encoding. The upload has a real RIFF/WAVE header and the filename `recording.wav`. It does not rename a WebM recording to `.wav`; WebM is not listed in the official REST formats. There is no FFmpeg dependency.

## Local API and files

- `GET /api/health`: service status and a Boolean indicating whether a key is configured.
- `POST /api/transcribe`: multipart `audio` and optional `session_id`; validates WAV recording, transcribes with Gnani STT, updates dialogue state, and returns `{ turn_id, session_id, transcript, reply, details, awaiting }`.
- `POST /api/conversation`: JSON `{ text, session_id }`; processes text turn or correction and returns updated dialogue state.
- `POST /api/conversation/restore`: JSON `{ session_id }`; restores active conversation session state and turn history.
- `POST /api/conversation/reset`: JSON `{ session_id }`; clears session state.
- `POST /api/reply-audio`: JSON `{ session_id, turn_id }`; synthesizes contextual reply via Gnani TTS and returns playable 24 kHz mono `audio/wav`.
- `backend/conversation.py`: conservative slot dialogue tracking, negation/correction handling, and response generation without invented banking requirements.
- `backend/audio.py`: WAV header validation and streaming unknown-length (`0xFFFFFFFF`) chunk repair.
- `src/App.tsx`: recording, text entry, corrections, live status, remembered details chips, and audio playback.
- `src/audio.ts` and `public/recorder-worklet.js`: capture, resampling, cleanup and WAV encoding.
- `backend/main.py`: FastAPI endpoints and backend-only Gnani calls.

The app holds the last 50 turns and extracted details in backend memory for up to one hour of inactivity; restarting the backend clears them. The browser keeps a session ID in sessionStorage for refresh recovery. New conversation clears that session. Gnani receives recordings for STT and the contextual reply text for TTS. Provider error bodies, credentials and transcripts are not logged by the application. Responses use `Cache-Control: no-store`; replay audio stays in the browser until a new turn or page exit. Fonts may load from Google Fonts, with local system-font fallbacks.

Audio generation runs independently of text/voice input. A pending or failed TTS request preserves the conversation and permits the next turn; outdated audio responses cannot replace the latest turn's audio. The speaker button retries synthesis for the saved reply without repeating the conversation turn.

## Checks

```powershell
Set-Location C:\Users\thispc\voice-companion
npm.cmd run build
npm.cmd test
.\.venv\Scripts\python.exe -m pytest backend -q
```

The build checks TypeScript and creates `dist`. Tests use fake provider responses and never call Gnani or require a real key. They cover the PCM WAV header and sample values, microphone error guidance, backend connectivity errors, exact STT/TTS request contracts, mixed-script preservation, invalid/empty/truncated audio, missing credentials, timeouts, rate limits, and safe provider errors.

Backend regression tests cover multi-turn Telugu, bank/town/branch/intent corrections, details in the first sentence, and normalized streaming WAV headers. One upstream Starlette/AnyIO deprecation warning is non-failing.

**Current verification status:** 56 backend tests, 9 frontend tests and the production build pass. The Vite-proxy synthetic conversation smoke check passes. Live TTS using only “నమస్కారం. మీకు ఎలా సహాయం చేయగలను?” returned HTTP 200 and a validated non-silent 2.72-second WAV with certificate verification enabled. `verify_live.py` uses only that fixed generic greeting, never conversation history or extracted details, and saves measurements under `artifacts/live-tts/`. Browser verification was blocked because computer use could not reliably identify Chrome's URL; audible playback and live microphone STT were not verified in this phase. See [BANKING_PREPARATION.md](BANKING_PREPARATION.md) for the detailed test journey and limitations.

### Troubleshooting: untrusted HTTPS inspection certificate

The configured STT endpoint (`https://api.vachana.ai/stt/v3`) and authentication header (`X-API-Key-ID`) match the official Gnani docs. During diagnosis, DNS resolved, but both Python and Windows curl rejected the TLS certificate chain. A credential-free inspection of the presented certificate showed the issuer `Sophos SSL CA_VhzBRw6FuQre1Q4`, indicating HTTPS inspection on the network path. No Sophos certificates were found in the Windows current-user or local-machine Root/CA stores checked.

The app now identifies TLS, DNS, and proxy failures separately. Backend logs contain controlled diagnostic codes (for example `tls_certificate_verify_failed (verify_code=20)`), never raw exception strings, headers, or credentials.

To resolve this network-specific TLS failure, obtain the approved PEM CA bundle for this network from your administrator and verify its provenance with them. Then add its absolute path to the backend's root `.env`, alongside the existing key:

```dotenv
SSL_CERT_FILE=C:/certificates/approved-ca-bundle.pem
```

This is a placeholder path: it must point to the real administrator-approved bundle. HTTPX supports `SSL_CERT_FILE` while retaining certificate and hostname verification; see its [official SSL documentation](https://www.python-httpx.org/advanced/ssl/). Restart FastAPI after setting it. Alternatively, use a network that presents a trusted certificate chain and retry recording. Do not copy an unverified certificate from the failed connection into a trust store, disable TLS verification, or send the key over HTTP. The application does not change Windows trust settings.

`npm.cmd run preview` previews the built frontend only; use `npm.cmd run dev` for the complete local voice loop and its `/api` proxy. This Phase 1 app is intended for local development, with no public hosting or production authentication configured.
