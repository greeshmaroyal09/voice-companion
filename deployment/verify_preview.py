"""Synthetic health/text/session/audio checks through a Vercel preview."""
import argparse
import io
import os
import wave
from uuid import uuid4
from urllib.parse import urlsplit

import httpx

from deployment.prepare_preview import check_health, https_origin

PRODUCTION_HOST = 'voice-companion-khaki.vercel.app'


def checked(response, stage, *, json_response=True):
    if response.status_code != 200:
        raise ValueError(f'{stage}: HTTP {response.status_code}; check preview protection, rewrite, and backend logs.')
    if 'no-store' not in response.headers.get('cache-control', '').lower():
        raise ValueError(f'{stage}: expected Cache-Control: no-store.')
    request_id = response.request.headers.get('x-request-id')
    if response.headers.get('x-request-id') != request_id:
        raise ValueError(f'{stage}: FastAPI request ID did not survive the rewrite.')
    print(f'PASS {stage}: HTTP 200; request_id={request_id}')
    if json_response:
        try:
            return response.json()
        except ValueError:
            raise ValueError(f'{stage}: non-JSON response; possible SPA fallback.') from None


def journey(client):
    session = None
    try:
        check_health(client)
        health = client.get('/api/health', headers={'X-Request-ID': f'preview-health-{uuid4().hex}'})
        checked(health, 'health')
        unknown = client.get('/api/preview-route-must-not-exist')
        if unknown.status_code != 404 or unknown.json().get('detail') != 'Not Found':
            raise ValueError('Unknown /api route was swallowed by a frontend fallback.')
        print('PASS API 404 reaches FastAPI, not the SPA catch-all')
        first = checked(client.post('/api/conversation',
            json={'text': 'నేను SBIలో ఖాతా తెరవాలనుకుంటున్నా.', 'session_id': None},
            headers={'X-Request-ID': f'preview-text-{uuid4().hex}'}), 'text')
        session = first.get('session_id')
        if not session or first.get('details', {}).get('bank') != 'SBI' or not first.get('reply'):
            raise ValueError('Text response did not contain the expected conversation state.')
        followup = checked(client.post('/api/conversation',
            json={'text': 'అవును', 'session_id': session},
            headers={'X-Request-ID': f'preview-next-{uuid4().hex}'}), 'follow-up')
        if followup.get('session_id') != session or followup.get('details', {}).get('bank') != 'SBI':
            raise ValueError('Follow-up lost the session or SBI; verify one worker on one instance.')
        audio = client.post('/api/reply-audio', json={'session_id': session, 'turn_id': followup['turn_id']},
            headers={'X-Request-ID': f'preview-audio-{uuid4().hex}'})
        checked(audio, 'reply audio', json_response=False)
        if audio.headers.get('content-type', '').split(';')[0] != 'audio/wav':
            raise ValueError('Reply audio did not return audio/wav.')
        with wave.open(io.BytesIO(audio.content), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000) or not wav.getnframes():
                raise ValueError('Reply audio is not a nonempty 24 kHz mono 16-bit WAV.')
        restored = checked(client.post('/api/conversation/restore', json={'session_id': session},
            headers={'X-Request-ID': f'preview-restore-{uuid4().hex}'}), 'restore')
        if len(restored.get('turns', [])) != 2:
            raise ValueError('Restored conversation did not retain both synthetic turns.')
    finally:
        if session:
            response = client.post('/api/conversation/reset', json={'session_id': session})
            if response.status_code != 200:
                raise ValueError('Could not clear the synthetic test session.')
    print('PASS synthetic preview journey; test session cleared. No production promotion performed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preview_url', help='Vercel preview HTTPS origin, not the production domain')
    args = parser.parse_args()
    try:
        origin = https_origin(args.preview_url)
        if urlsplit(origin).hostname == PRODUCTION_HOST:
            raise ValueError('Use the preview deployment URL, not the production domain.')
        headers = {}
        bypass = os.getenv('VERCEL_AUTOMATION_BYPASS_SECRET')
        if bypass:
            headers['x-vercel-protection-bypass'] = bypass
        with httpx.Client(base_url=origin, headers=headers, timeout=90, follow_redirects=False, trust_env=False) as client:
            journey(client)
    except (ValueError, KeyError, wave.Error, EOFError, httpx.RequestError) as error:
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(1, f'Preview check failed: {detail}\n')


if __name__ == '__main__':
    main()
