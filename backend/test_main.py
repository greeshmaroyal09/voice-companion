import io
import json
import socket
import ssl
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.conversation import store


def wav_bytes(seconds=1, rate=16000, silent=False):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((b"\0\0" if silent else b"\x10\x01") * int(seconds * rate))
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-only-not-a-real-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    store.sessions.clear()
    with TestClient(main.app) as client:
        yield client


def mock_gnani(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def upload(client, content):
    return client.post("/api/transcribe", files={"audio": ("recording.wav", content, "audio/wav")})


def tts(client):
    turn = client.post("/api/conversation", json={"text": "నేను SBI bankలో account తెరవాలి, Anantapur branch"}).json()
    return client.post("/api/reply-audio", json={"session_id": turn["session_id"], "turn_id": turn["turn_id"]})


def test_health_never_exposes_key(client):
    response = client.get("/api/health")
    assert response.json() == {"status": "ok", "gnani_configured": True}
    assert "test-only" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_no_key_is_actionable(client, monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    assert client.get("/api/health").json()["gnani_configured"] is False
    for response in [upload(client, wav_bytes()), tts(client)]:
        assert response.status_code == 503
        assert "project-root .env" in response.json()["detail"]


@pytest.mark.parametrize("audio,status", [
    (b"", 400), (b"not wav" * 10, 400), (wav_bytes(0.1), 400),
    (wav_bytes(silent=True), 400), (wav_bytes(rate=48000), 400),
    (wav_bytes(31), 413), (wav_bytes()[:-100], 400),
], ids=["empty", "not-wav", "too-short", "silent", "wrong-rate", "too-long", "truncated"])
def test_invalid_recordings_never_reach_gnani(client, monkeypatch, audio, status):
    def unexpected(_):
        pytest.fail("Invalid input must not reach Gnani")
    mock_gnani(monkeypatch, unexpected)
    assert upload(client, audio).status_code == status


def test_unsupported_browser_container_is_rejected_before_gnani(client, monkeypatch):
    def unexpected(_):
        pytest.fail("An unsupported browser container must not reach Gnani")
    mock_gnani(monkeypatch, unexpected)
    response = client.post(
        "/api/transcribe",
        files={"audio": ("recording.webm", b"\x1aE\xdf\xa3" + b"webm-audio" * 20, "audio/webm")},
    )
    assert response.status_code == 400
    assert "valid WAV" in response.json()["detail"]


def test_prisma_contract_and_mixed_script_preserved(client, monkeypatch):
    transcript = "నాకు SBI bank లో account తెరవాలి."
    audio = wav_bytes()
    def handler(request):
        assert str(request.url) == main.STT_URL
        assert request.headers["X-API-Key-ID"] == "test-only-not-a-real-key"
        body = request.read()
        for part in [b'name="audio_file"; filename="recording.wav"', b"audio/wav", b"prisma-v3.0", b"te-IN,en-IN", b"codemix", audio]:
            assert part in body
        return httpx.Response(200, json={"success": True, "transcript": transcript, "model": "prisma-v3.0"})
    mock_gnani(monkeypatch, handler)
    response = upload(client, audio)
    assert response.status_code == 200
    assert response.json()["transcript"] == transcript
    assert response.json()["details"]["bank"] == "SBI"
    assert response.json()["details"]["intent"] == "open_account"
    assert response.json()["awaiting"] == ""
    assert "SBI" in response.json()["reply"] and len(response.json()["reply"]) < 200
    assert response.json()["preparation"]["answers"] == {}


def test_valid_telugu_transcript_is_returned_unchanged(client, monkeypatch, caplog):
    caplog.set_level("INFO")
    transcript = "నమస్కారం. నాకు SBI bank లో account తెరవాలి."
    mock_gnani(monkeypatch, lambda _: httpx.Response(200, json={
        "success": True, "transcript": transcript, "model": "prisma-v3.0",
        "detected_language_code": "te-IN",
    }))
    response = upload(client, wav_bytes())
    assert response.status_code == 200
    assert response.json()["transcript"] == transcript
    assert response.json()["transcript"] == response.json()["transcript"].strip()
    assert response.json()["details"]["bank"] == "SBI"
    assert "client_mime=audio/wav" in caplog.text
    assert "container=WAV codec=PCM_S16LE channels=1 sample_rate_hz=16000" in caplog.text
    assert "nonzero_pcm=True" in caplog.text and "transcript_chars=" in caplog.text
    assert transcript not in caplog.text


def test_provider_http_error_exposes_safe_status_and_code(client, monkeypatch, caplog):
    mock_gnani(monkeypatch, lambda _: httpx.Response(400, json={
        "success": False,
        "error": {"type": "INVALID_LANGUAGE_CODE", "message": "private provider detail"},
    }))
    response = upload(client, wav_bytes())
    assert response.status_code == 502
    assert "HTTP 400" in response.json()["detail"]
    assert "INVALID_LANGUAGE_CODE" in response.json()["detail"]
    assert "HTTP 400" in caplog.text and "INVALID_LANGUAGE_CODE" in caplog.text
    assert "private provider detail" not in response.text
    assert "test-only-not-a-real-key" not in caplog.text


def test_provider_validation_response_identifies_missing_field(client, monkeypatch):
    mock_gnani(monkeypatch, lambda _: httpx.Response(422, json={"detail": [
        {"type": "missing", "loc": ["body", "language_code"], "msg": "private validation detail"},
    ]}))
    response = upload(client, wav_bytes())
    assert response.status_code == 502
    assert "HTTP 422" in response.json()["detail"]
    assert "MISSING_LANGUAGE_CODE" in response.json()["detail"]
    assert "private validation detail" not in response.text


def test_timbre_contract_and_binary_playback(client, monkeypatch):
    audio = wav_bytes(rate=24000)
    def handler(request):
        assert str(request.url) == main.TTS_URL
        assert request.headers["X-API-Key-ID"] == "test-only-not-a-real-key"
        payload = json.loads(request.read())
        assert "SBI" in payload["text"]
        assert "ఒక్కొక్కటిగా" in payload["text"] and len(payload["text"]) < 200
        assert payload["voice"] == "Lavanya"
        assert payload["model"] == "timbre-v2.5"
        assert payload["language"] == "te-IN"
        assert payload["audio_config"] == {"sample_rate": 24000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"}
        return httpx.Response(200, content=audio, headers={"Content-Type": "audio/wav"})
    mock_gnani(monkeypatch, handler)
    response = tts(client)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == audio


@pytest.mark.parametrize("status,word", [(400, "rejected"), (401, "authentication"), (402, "credits"), (403, "denied"), (429, "rate-limited"), (500, "unavailable")])
def test_provider_errors_are_safe_and_actionable(client, monkeypatch, status, word):
    mock_gnani(monkeypatch, lambda _: httpx.Response(status, text="sensitive provider body test-only-not-a-real-key"))
    for response in [upload(client, wav_bytes()), tts(client)]:
        assert response.status_code == 502
        assert word in response.json()["detail"]
        assert "test-only" not in response.text
        assert "sensitive" not in response.text


@pytest.mark.parametrize("exception,status", [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
def test_network_failure(client, monkeypatch, exception, status):
    def handler(_):
        raise exception("sensitive request information")
    mock_gnani(monkeypatch, handler)
    response = upload(client, wav_bytes())
    assert response.status_code == status
    assert "sensitive" not in response.text


def test_outbound_socket_denial_is_actionable_without_raw_os_error():
    error = httpx.ConnectError("private transport text")
    denied = PermissionError(13, "private socket details")
    denied.winerror = 10013
    error.__cause__ = denied
    diagnostic, message = main.transport_failure(error)
    assert "outbound_socket_access_denied" in diagnostic
    assert "not allowed to open an outbound HTTPS connection" in message
    assert "private" not in diagnostic + message


def test_tls_failure_has_safe_diagnostic_and_keeps_verification(client, monkeypatch, caplog):
    original = httpx.AsyncClient
    certificate_error = ssl.SSLCertVerificationError(1, "sensitive certificate error test-only-not-a-real-key")
    certificate_error.verify_code = 20
    def handler(_):
        raise httpx.ConnectError("sensitive transport error") from certificate_error
    def factory(**kwargs):
        # No insecure verify=False or custom bypass may be introduced.
        assert kwargs.get("verify", True) is True
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(main.httpx, "AsyncClient", factory)
    response = upload(client, wav_bytes())
    assert response.status_code == 502
    assert "unable to get local issuer certificate" in response.json()["detail"]
    assert "SSL_CERT_FILE" in response.json()["detail"]
    assert "tls_certificate_verify_failed (verify_code=20)" in caplog.text
    for output in (response.text, caplog.text):
        assert "sensitive" not in output
        assert "test-only-not-a-real-key" not in output


def test_tls_failure_inside_exception_group_is_detected_without_raw_error():
    certificate_error = ssl.SSLCertVerificationError(1, "private certificate detail")
    certificate_error.verify_code = 20
    grouped = ExceptionGroup("private grouped failure", [certificate_error])
    error = httpx.ConnectError("private connect error")
    error.__cause__ = grouped
    diagnostic, message = main.transport_failure(error)
    assert "tls_certificate_verify_failed (verify_code=20)" in diagnostic
    assert "unable to get local issuer certificate" in message
    assert "private" not in diagnostic + message


def test_request_id_is_returned_and_logged_safely(client, caplog):
    caplog.set_level("INFO")
    response = client.get("/api/health", headers={"X-Request-ID": "test-trace-123"})
    assert response.headers["x-request-id"] == "test-trace-123"
    assert "request_id=test-trace-123 route=/api/health" in caplog.text


def test_dns_failure_is_distinct(client, monkeypatch):
    def handler(_):
        raise httpx.ConnectError("private diagnostic") from socket.gaierror(11001, "private hostname")
    mock_gnani(monkeypatch, handler)
    response = upload(client, wav_bytes())
    assert response.status_code == 502
    assert "Could not resolve api.vachana.ai" in response.json()["detail"]
    assert "private" not in response.text


def test_proxy_failure_is_distinct(client, monkeypatch):
    def handler(_):
        raise httpx.ProxyError("private proxy credentials")
    mock_gnani(monkeypatch, handler)
    response = upload(client, wav_bytes())
    assert response.status_code == 502
    assert "proxy could not connect" in response.json()["detail"]
    assert "private" not in response.text


@pytest.mark.parametrize("body,status", [({"success": True, "transcript": "  "}, 422), ({"success": False}, 502), ({"success": True, "transcript": 42}, 502), ([], 502)])
def test_empty_or_invalid_transcripts(client, monkeypatch, body, status):
    mock_gnani(monkeypatch, lambda _: httpx.Response(200, json=body))
    assert upload(client, wav_bytes()).status_code == status


def test_unreadable_json(client, monkeypatch):
    mock_gnani(monkeypatch, lambda _: httpx.Response(200, content=b"not json"))
    assert upload(client, wav_bytes()).status_code == 502


@pytest.mark.parametrize("body", [b"", b'{"success":false}', wav_bytes()[:-10]], ids=["empty", "json", "truncated"])
def test_invalid_reply_audio(client, monkeypatch, body):
    mock_gnani(monkeypatch, lambda _: httpx.Response(200, content=body))
    assert tts(client).status_code == 502
