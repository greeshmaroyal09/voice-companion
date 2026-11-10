import io
import json
import wave

import httpx
import pytest

from deployment.prepare_preview import check_health, config_for_backend, https_origin
from deployment.verify_preview import journey


@pytest.mark.parametrize('origin', [
    'http://127.0.0.1:8000', 'https://127.0.0.1', 'https://10.0.0.1',
    'https://backend.invalid', 'https://api.example.com', 'https://localhost',
    'https://user:secret@host.onrender.com', 'https://host.onrender.com/api',
    'https://host.onrender.com?key=secret',
])
def test_preview_config_requires_real_https_origin_without_embedded_secrets(origin):
    with pytest.raises(ValueError):
        https_origin(origin)


def test_rewrite_preserves_api_prefix_and_precedes_spa_fallback():
    # This is a mocked configuration fixture, not an asserted hosted service.
    config = config_for_backend('https://unit-backend.onrender.com/')
    assert config['rewrites'][0] == {
        'source': '/api/:path*',
        'destination': 'https://unit-backend.onrender.com/api/:path*',
    }
    assert config['rewrites'][1]['destination'] == '/index.html'
    assert config['headers'][0]['headers'][0]['value'] == 'no-store'
    assert 'GNANI_API_KEY' not in json.dumps(config)
    assert 'GEMINI_API_KEY' not in json.dumps(config)


@pytest.mark.parametrize('content', [b'<html>frontend</html>', b'[]', b'{"status":"ok","gnani_configured":false}'])
def test_health_gate_rejects_spa_and_unconfigured_voice(content):
    with httpx.Client(base_url='https://unit-backend.onrender.com',
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))) as client:
        with pytest.raises(ValueError):
            check_health(client)


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b'\x01\x00' * 240)
    return buffer.getvalue()


@pytest.mark.parametrize('audio_status', [200, 502])
def test_preview_journey_checks_state_and_audio_and_cleans_up(audio_status, capsys):
    paths = []
    turns = []

    def handler(request):
        path = request.url.path
        paths.append(path)
        headers = {'cache-control': 'no-store', 'x-request-id': request.headers.get('x-request-id', '')}
        if path == '/api/health':
            return httpx.Response(200, json={'status': 'ok', 'gnani_configured': True}, headers=headers)
        if path == '/api/preview-route-must-not-exist':
            return httpx.Response(404, json={'detail': 'Not Found'}, headers=headers)
        if path == '/api/conversation':
            body = json.loads(request.content)
            assert body['session_id'] == ('synthetic-session' if turns else None)
            turns.append(body['text'])
            return httpx.Response(200, json={'session_id': 'synthetic-session', 'turn_id': str(len(turns)),
                'details': {'bank': 'SBI'}, 'reply': 'synthetic reply'}, headers=headers)
        if path == '/api/reply-audio':
            assert json.loads(request.content) == {'session_id': 'synthetic-session', 'turn_id': '2'}
            if audio_status != 200:
                return httpx.Response(audio_status, json={'detail': 'sensitive-provider-body'}, headers=headers)
            return httpx.Response(200, content=wav_bytes(), headers={**headers, 'content-type': 'audio/wav'})
        if path == '/api/conversation/restore':
            return httpx.Response(200, json={'turns': turns}, headers=headers)
        if path == '/api/conversation/reset':
            return httpx.Response(200, json={'status': 'cleared'}, headers=headers)
        raise AssertionError('Unexpected route')

    with httpx.Client(base_url='https://unit-preview.vercel.app', transport=httpx.MockTransport(handler)) as client:
        if audio_status == 200:
            journey(client)
        else:
            with pytest.raises(ValueError, match='reply audio: HTTP 502'):
                journey(client)
    assert paths[-1] == '/api/conversation/reset'
    output = capsys.readouterr().out
    assert 'sensitive-provider-body' not in output
    assert ('PASS synthetic preview journey' in output) is (audio_status == 200)
