"""Local-only Telugu voice integration. Credentials never leave this process."""

import io
import logging
import os
import re
import socket
import ssl
import wave
from uuid import uuid4
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.audio import playable_wav
from backend.conversation import store
from backend.diagnostics import current_request_id, exception_chain, request_id_context
from backend.gemini import interpret_turn

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

app = FastAPI(title="Voice Companion", version="0.1.0")
logger = logging.getLogger("uvicorn.error")
STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
MAX_WAV_BYTES = 960_044  # 30 seconds of mono 16 kHz, signed 16-bit PCM.


def transport_failure(error: httpx.RequestError) -> tuple[str, str]:
    """Describe transport failures without logging headers or exception text."""
    causes = list(exception_chain(error))
    cause_types = [type(cause).__name__ for cause in causes[:10]]
    for cause in causes:
        if isinstance(cause, ssl.SSLCertVerificationError):
            code = getattr(cause, "verify_code", None)
            reasons = {
                10: "certificate has expired",
                18: "self-signed certificate",
                19: "self-signed certificate in certificate chain",
                20: "unable to get local issuer certificate",
                21: "unable to verify the first certificate",
                62: "certificate hostname mismatch",
            }
            reason = reasons.get(code, "untrusted or invalid certificate chain")
            # Codes are integers from OpenSSL; no raw provider/error text escapes.
            diagnostic = f"tls_certificate_verify_failed (verify_code={code if isinstance(code, int) else 'unknown'})"
            return diagnostic, (
                f"Gnani TLS certificate verification failed: {reason}. "
                "If your network uses HTTPS inspection, obtain its approved CA bundle "
                "from your administrator, set SSL_CERT_FILE in the backend .env, and restart FastAPI. "
                "Alternatively, use a network with a trusted certificate chain."
            )
        if isinstance(cause, socket.gaierror):
            return "dns_resolution_failed", "Could not resolve api.vachana.ai. Check your network DNS connection and try again."
        if isinstance(cause, PermissionError):
            winerror = getattr(cause, "winerror", None)
            suffix = f" (winerror={winerror})" if isinstance(winerror, int) else ""
            return f"outbound_socket_access_denied{suffix}", (
                "The backend runtime is not allowed to open an outbound HTTPS connection to Gnani. "
                "Run FastAPI in an environment permitted to make HTTPS requests, then retry."
            )
    if any(isinstance(cause, httpx.ProxyError) for cause in causes):
        return "proxy_connection_failed", "The backend proxy could not connect to Gnani. Check your proxy configuration."
    chain = ">".join(cause_types[:6]) or type(error).__name__
    return f"network_request_failed (chain={chain})", "Could not reach Gnani. Check the backend internet connection and try again."


def api_key() -> str:
    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Set GNANI_API_KEY in the project-root .env file, then restart FastAPI.")
    return key


async def handle_user_message(session, text: str) -> dict:
    """Shared typed/STT route: interpret, validate, then use one conversation handler."""
    interpretation = await interpret_turn(text, session.details, session.preparation.pending)
    logger.info("request_id=%s conversation_interpretation_path=%s",
                current_request_id(), "gemini" if interpretation is not None else "local_fallback")
    return session.advance(text, interpretation)


def validate_recording(data: bytes) -> dict[str, float | bool]:
    if len(data) <= 44:
        raise HTTPException(400, "The recording is empty. Record a short sentence and try again.")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                raise HTTPException(400, "Please send a mono, 16-bit PCM WAV recording at 16 kHz.")
            frames = wav.getnframes()
            duration = frames / 16000
            if not 0.25 <= duration <= 30:
                raise HTTPException(400, "Record between 0.25 and 30 seconds, then try again.")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2:
                raise HTTPException(400, "The recording is incomplete. Please record again.")
            nonzero_pcm = any(pcm)
            if not nonzero_pcm:
                raise HTTPException(400, "The recording is silent. Check your microphone and try again.")
            return {"duration_seconds": duration, "nonzero_pcm": nonzero_pcm}
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(400, "The recording is not a valid WAV file. Please record again.") from None


async def gnani_request(url: str, **kwargs) -> httpx.Response:
    key = api_key()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.post(url, headers={
                "X-API-Key-ID": key,
                "X-API-Request-ID": current_request_id(),
            }, **kwargs)
    except httpx.TimeoutException:
        logger.warning("request_id=%s Gnani %s request failed: timeout", current_request_id(), "STT" if url == STT_URL else "TTS")
        raise HTTPException(504, "Gnani took too long to respond. Please try again.") from None
    except httpx.RequestError as error:
        diagnostic, message = transport_failure(error)
        logger.warning("request_id=%s Gnani %s request failed: %s", current_request_id(), "STT" if url == STT_URL else "TTS", diagnostic)
        raise HTTPException(502, message) from None

    # Never forward provider bodies, exception strings or request headers: they
    # can include sensitive data. Only return our own actionable messages.
    if response.is_error:
        service = "STT" if url == STT_URL else "TTS"
        provider_code = provider_error_code(response)
        logger.warning("request_id=%s Gnani %s returned HTTP %s%s", current_request_id(), service, response.status_code,
                       f" error_code={provider_code}" if provider_code else "")
        messages = {
            400: "Gnani rejected the audio or speech settings. Check the backend integration configuration.",
            401: "Gnani authentication failed. Check GNANI_API_KEY in .env and restart FastAPI.",
            402: "Gnani credits are unavailable. Check your Gnani account balance.",
            403: "Gnani access was denied. Check the key's STT/TTS permissions and account credits.",
            413: "Gnani rejected the recording size. Try a shorter recording.",
            422: "Gnani could not process the speech request. Try a new short recording.",
            429: "Gnani is busy or rate-limited. Wait a moment, then try again.",
        }
        reason = messages.get(response.status_code, "Gnani is temporarily unavailable. Please try again.")
        code = f", {provider_code}" if provider_code else ""
        raise HTTPException(502, f"Gnani {service} returned HTTP {response.status_code}{code}. {reason}")
    logger.info("request_id=%s provider=gnani stage=%s status=%s content_type=%s body_bytes=%d",
                current_request_id(), "STT" if url == STT_URL else "TTS", response.status_code,
                safe_mime_type(response.headers.get("content-type", "missing")), len(response.content))
    return response


def provider_error_code(response: httpx.Response) -> str | None:
    """Extract only a bounded machine code; never log or return provider text."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    code = error.get("type") if isinstance(error, dict) else None
    if not code and isinstance(body.get("detail"), dict):
        code = body["detail"].get("error_code")
    if not code and isinstance(body.get("detail"), list):
        for issue in body["detail"]:
            if not isinstance(issue, dict):
                continue
            location = issue.get("loc")
            field_name = location[-1] if isinstance(location, list) and location else None
            issue_type = issue.get("type")
            if issue_type == "missing" and field_name in {"audio_file", "language_code"}:
                code = f"MISSING_{field_name.upper()}"
                break
    if not code and isinstance(body.get("code"), str):
        code = body["code"]
    return code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code) else None


def safe_log_label(value: object) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value) else "unknown"


def safe_mime_type(value: object) -> str:
    return value.split(";", 1)[0].strip().lower() if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+(?:\s*;[^\r\n]{0,80})?", value) else "unknown"


@app.middleware("http")
async def private_responses(request, call_next):
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied_id) else uuid4().hex
    token = request_id_context.set(request_id)
    try:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        logger.info("request_id=%s route=%s method=%s status=%s", request_id, request.url.path, request.method, response.status_code)
        return response
    finally:
        request_id_context.reset(token)


@app.get("/api/health")
async def health():
    return {"status": "ok", "gnani_configured": bool(os.getenv("GNANI_API_KEY", "").strip())}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), session_id: str | None = Form(None, max_length=36)):
    if session_id:
        store.get(session_id)  # Reject expired sessions before a billable STT call.
    try:
        data = await audio.read(MAX_WAV_BYTES + 1)
    finally:
        await audio.close()
    if len(data) > MAX_WAV_BYTES:
        raise HTTPException(413, "The recording is too large. Keep it under 30 seconds.")
    metadata = validate_recording(data)
    client_mime = audio.content_type or "(missing)"
    if not re.fullmatch(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+", client_mime):
        client_mime = "(invalid)"
    logger.info(
        "request_id=%s STT audio accepted: client_mime=%s bytes=%d container=WAV codec=PCM_S16LE "
        "channels=1 sample_rate_hz=16000 duration_seconds=%.3f nonzero_pcm=%s",
        current_request_id(), client_mime, len(data), metadata["duration_seconds"], metadata["nonzero_pcm"],
    )
    response = await gnani_request(
        STT_URL,
        files={"audio_file": ("recording.wav", data, "audio/wav")},
        data={"model": "prisma-v3.0", "language_code": "te-IN,en-IN", "format": "codemix"},
    )
    try:
        result = response.json()
    except ValueError:
        logger.warning("request_id=%s Gnani STT response_shape=invalid_json", current_request_id())
        raise HTTPException(502, "Gnani returned an unreadable transcript. Please try again.") from None
    if isinstance(result, dict) and result.get("success") is False:
        code = provider_error_code(response)
        logger.warning("request_id=%s Gnani STT response_shape=success_false%s", current_request_id(),
                       f" error_code={code}" if code else "")
        suffix = f" ({code})" if code else ""
        raise HTTPException(502, f"Gnani STT reported a transcription error{suffix}. Check the speech settings and retry.")
    if not isinstance(result, dict) or result.get("success") is not True or not isinstance(result.get("transcript"), str):
        logger.warning("request_id=%s Gnani STT response_shape=invalid", current_request_id())
        raise HTTPException(502, "Gnani did not return a valid transcript. Please try again.")
    if not result["transcript"].strip():
        logger.info("request_id=%s Gnani STT returned empty transcript model=%s", current_request_id(), safe_log_label(result.get("model")))
        raise HTTPException(422, "No speech was detected. Move closer to the microphone and try again.")
    logger.info("request_id=%s Gnani STT transcript received: model=%s detected_language=%s transcript_chars=%d",
                current_request_id(), safe_log_label(result.get("model")), safe_log_label(result.get("detected_language_code")), len(result["transcript"]))
    # Preserve the provider's mixed-script Unicode string without normalization.
    turn = await handle_user_message(store.get(session_id), result["transcript"])
    return {**turn, "transcript": result["transcript"]}


class TextTurn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=36)


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)


class AudioRequest(SessionRequest):
    turn_id: str = Field(min_length=36, max_length=36)


@app.post("/api/conversation")
async def conversation_turn(body: TextTurn):
    if not body.text.strip():
        raise HTTPException(400, "Type a message before sending.")
    return await handle_user_message(store.get(body.session_id), body.text)


@app.post("/api/conversation/restore")
async def restore_conversation(body: SessionRequest):
    session = store.get(body.session_id)
    return {"session_id": session.id, "details": session.details, "awaiting": session.awaiting, "turns": session.turns, 'preparation': session.preparation.view(session.details)}


@app.post("/api/conversation/reset")
async def reset_conversation(body: SessionRequest):
    store.sessions.pop(body.session_id, None)
    return {"status": "cleared"}


@app.post("/api/reply-audio")
async def reply_audio(body: AudioRequest):
    session = store.get(body.session_id)
    turn = next((turn for turn in session.turns if turn["turn_id"] == body.turn_id), None)
    if turn is None:
        raise HTTPException(404, "This reply is no longer available. Start a new conversation.")
    response = await gnani_request(
        TTS_URL,
        json={
            "text": turn["reply"],
            "model": "timbre-v2.5",
            "voice": "Lavanya",
            "language": "te-IN",
            "speed": 1.0,
            "audio_config": {
                "sample_rate": 24000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        },
    )
    try:
        audio = playable_wav(response.content)
    except ValueError:
        logger.warning("request_id=%s Gnani TTS response_shape=invalid_wav content_type=%s body_bytes=%d",
                       current_request_id(), safe_mime_type(response.headers.get("content-type", "missing")), len(response.content))
        raise HTTPException(502, "Gnani returned invalid reply audio. Tap the speaker button to try again.") from None
    logger.info("request_id=%s Gnani TTS audio=playable_wav rate_hz=24000 channels=1 bits=16 body_bytes=%d",
                current_request_id(), len(audio))
    return Response(content=audio, media_type="audio/wav")
